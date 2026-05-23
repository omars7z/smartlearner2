"""
SmartLearner — Analytics Agent (merged v1 + v2)
Adaptive DKT · Multi-stage pipeline · Learning velocity · Frontend-compatible output
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.services.agents.base import AgentPair
from app.services.llm_client import LLMClient

ANALYTICS_AGENT_SYSTEM_PROMPT = """You are the Analytics Agent for SmartLearner — an adaptive AI learning platform.

ROLE: Translate deterministic analytics into concise, motivating, per-student insights.

YOUR ONLY JOB (LLM layer):
1. Write a 2-sentence personal summary (encouraging, specific to this student's data).
2. Refine next_action to exactly one of: continue | review | slow_down | take_break
3. Add up to 3 short motivating recommendation strings.

RULES:
- NEVER change any numeric value (mastery, progress %, scores).
- NEVER invent topics not in the student's syllabus.
- ALWAYS return valid JSON, no extra text, no markdown.
- If data is insufficient, return the deterministic output unchanged.

OUTPUT FORMAT:
{
  "personal_summary": "...",
  "next_action": "continue|review|slow_down|take_break",
  "motivating_recommendations": ["...", "...", "..."]
}
"""


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class StudentProfile:
    student_id: str
    learning_speed: float = 1.0
    consistency_score: float = 0.5
    avg_quiz_score: float = 0.5
    total_interactions: int = 0
    mastery_gain_correct: float = 0.10
    mastery_loss_wrong: float = 0.15
    passive_gain: float = 0.05
    mastered_threshold: float = 0.75
    review_threshold: float = 0.40
    inactivity_days: int = 3


@dataclass
class TopicVelocity:
    topic: str
    score_history: list[float] = field(default_factory=list)
    timestamp_history: list[str] = field(default_factory=list)
    velocity: float = 0.0
    momentum: float = 0.0
    sessions_count: int = 0
    last_seen: str = ""
    trend: str = "stable"


@dataclass
class WeaknessFlag:
    topic: str
    reason: str
    severity: str
    signal_count: int = 1


# ── Syllabus helpers ──────────────────────────────────────────────────────────


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, round(float(value), 4)))


def _normalize_topic(value: object) -> str:
    return str(value or "").replace("_", " ").strip()


def _ordered_topics(syllabus: list[dict]) -> list[str]:
    rows = [r for r in syllabus if isinstance(r, dict) and _normalize_topic(r.get("topic"))]
    rows.sort(key=lambda r: int(r.get("order") or 0))
    return [_normalize_topic(r["topic"]) for r in rows]


def _map_to_syllabus_topic(raw_topic: object, syllabus: list[dict]) -> str | None:
    needle = _normalize_topic(raw_topic).lower()
    if not needle:
        return None
    for row in syllabus:
        if not isinstance(row, dict):
            continue
        topic = _normalize_topic(row.get("topic"))
        if topic.lower() == needle:
            return topic
        for sub in row.get("subtopics") or []:
            if _normalize_topic(sub).lower() == needle:
                return topic
    for row in syllabus:
        if not isinstance(row, dict):
            continue
        topic = _normalize_topic(row.get("topic"))
        if needle in topic.lower() or topic.lower() in needle:
            return topic
    return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_timestamp(raw: object) -> datetime | None:
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except ValueError:
        return None


# ── Stage 1: Student profile ──────────────────────────────────────────────────


class StudentProfileBuilder:
    @staticmethod
    def build(student_id: str, interaction_logs: list[dict], mastery_state: dict) -> StudentProfile:
        profile = StudentProfile(student_id=student_id)
        if not interaction_logs:
            return profile

        profile.total_interactions = len(interaction_logs)
        quiz_scores = [
            float(e["score"])
            for e in interaction_logs
            if isinstance(e, dict)
            and str(e.get("type", "")).lower() in {"quiz", "exam"}
            and isinstance(e.get("score"), (int, float))
        ]
        if quiz_scores:
            profile.avg_quiz_score = sum(quiz_scores) / len(quiz_scores)

        if len(quiz_scores) >= 4:
            half = len(quiz_scores) // 2
            early_avg = sum(quiz_scores[:half]) / half
            late_avg = sum(quiz_scores[half:]) / (len(quiz_scores) - half)
            profile.learning_speed = max(0.5, min(2.0, 1.0 + (late_avg - early_avg) * 2.0))

        timestamps = [_parse_timestamp(e.get("timestamp")) for e in interaction_logs if isinstance(e, dict)]
        timestamps = [t for t in timestamps if t is not None]
        if len(timestamps) >= 2:
            timestamps.sort()
            gaps = [(timestamps[i + 1] - timestamps[i]).days for i in range(len(timestamps) - 1)]
            avg_gap = sum(gaps) / len(gaps)
            profile.consistency_score = max(0.0, min(1.0, 1.0 - (avg_gap / 7.0)))

        profile.mastery_gain_correct = round(min(0.20, 0.10 * profile.learning_speed), 4)
        profile.mastery_loss_wrong = round(max(0.05, 0.15 * (1.0 - profile.consistency_score * 0.5)), 4)
        profile.passive_gain = round(min(0.10, 0.05 * (0.5 + profile.consistency_score)), 4)
        profile.inactivity_days = max(2, round(3 + (1.0 - profile.consistency_score) * 4))

        if profile.avg_quiz_score > 0.8:
            profile.mastered_threshold = 0.80
        elif profile.avg_quiz_score < 0.4:
            profile.mastered_threshold = 0.65
        else:
            profile.mastered_threshold = 0.75
        profile.review_threshold = profile.mastered_threshold - 0.35
        return profile


# ── Stage 2: Mastery engine ───────────────────────────────────────────────────


class MasteryEngine:
    def __init__(self, profile: StudentProfile):
        self.profile = profile

    def seed(self, syllabus: list[dict], existing: dict | None) -> dict[str, float]:
        mastery: dict[str, float] = {}
        if isinstance(existing, dict):
            for key, val in existing.items():
                topic = _normalize_topic(key)
                if topic:
                    try:
                        mastery[topic] = _clamp(float(val))
                    except (TypeError, ValueError):
                        pass
        for topic in _ordered_topics(syllabus):
            mastery.setdefault(topic, 0.5)
        return mastery

    def replay_logs(self, mastery: dict[str, float], logs: list[dict], syllabus: list[dict]) -> dict[str, float]:
        p = self.profile
        for entry in logs:
            if not isinstance(entry, dict):
                continue
            topic = _map_to_syllabus_topic(entry.get("topic"), syllabus)
            if not topic:
                continue
            mastery.setdefault(topic, 0.5)
            entry_type = str(entry.get("type") or "").lower()
            score = entry.get("score")

            if entry_type in {"quiz", "exam"} and isinstance(score, (int, float)):
                s = float(score)
                if s >= p.mastered_threshold:
                    mastery[topic] = _clamp(mastery[topic] + p.mastery_gain_correct)
                elif s < p.review_threshold:
                    mastery[topic] = _clamp(mastery[topic] - p.mastery_loss_wrong)
                else:
                    mid = (p.mastered_threshold + p.review_threshold) / 2
                    mastery[topic] = _clamp(mastery[topic] + (s - mid) * p.mastery_gain_correct)
            elif entry_type == "lesson_done":
                mastery[topic] = _clamp(mastery[topic] + p.passive_gain)
            elif entry_type == "question_asked":
                mastery[topic] = _clamp(mastery[topic] + 0.02)
        return mastery

    def apply_event(self, mastery: dict[str, float], event: dict | None, syllabus: list[dict]) -> dict[str, float]:
        if not isinstance(event, dict):
            return mastery
        p = self.profile
        event_type = str(event.get("type") or "").lower()
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}

        if event_type in {"quiz", "exam"}:
            topic = _map_to_syllabus_topic(payload.get("topic"), syllabus)
            if not topic:
                return mastery
            mastery.setdefault(topic, 0.5)

            questions = payload.get("questions") if isinstance(payload.get("questions"), list) else []
            results = payload.get("results") if isinstance(payload.get("results"), list) else []

            if questions:
                for q in questions:
                    if not isinstance(q, dict):
                        continue
                    difficulty = str(q.get("difficulty") or "medium").lower()
                    weight = {"easy": 0.7, "medium": 1.0, "hard": 1.4}.get(difficulty, 1.0)
                    if bool(q.get("correct")):
                        mastery[topic] = _clamp(mastery[topic] + p.mastery_gain_correct * weight)
                    else:
                        mastery[topic] = _clamp(mastery[topic] - p.mastery_loss_wrong * weight)
            elif results:
                for row in results:
                    if not isinstance(row, dict):
                        continue
                    difficulty = str(row.get("difficulty") or "medium").lower()
                    weight = {"easy": 0.7, "medium": 1.0, "hard": 1.4}.get(difficulty, 1.0)
                    if bool(row.get("correct")):
                        mastery[topic] = _clamp(mastery[topic] + p.mastery_gain_correct * weight)
                    else:
                        mastery[topic] = _clamp(mastery[topic] - p.mastery_loss_wrong * weight)

        elif event_type == "lesson_done":
            topic = _map_to_syllabus_topic(payload.get("topic"), syllabus)
            if topic:
                mastery.setdefault(topic, 0.5)
                if payload.get("passed") is True or payload.get("quiz_taken") is True:
                    score_ratio = payload.get("score_ratio")
                    if isinstance(score_ratio, (int, float)):
                        s = float(score_ratio)
                        if s >= p.review_threshold:
                            mastery[topic] = _clamp(mastery[topic] + p.mastery_gain_correct * s)
                        else:
                            mastery[topic] = _clamp(mastery[topic] - p.mastery_loss_wrong)
                    else:
                        mastery[topic] = _clamp(mastery[topic] + p.mastery_gain_correct)
                else:
                    mastery[topic] = _clamp(mastery[topic] + p.passive_gain)

        elif event_type == "question_asked":
            topic = _map_to_syllabus_topic(payload.get("topic"), syllabus)
            if topic:
                mastery.setdefault(topic, 0.5)
                mastery[topic] = _clamp(mastery[topic] + 0.02)

        return mastery


# ── Stage 3: Velocity tracker ─────────────────────────────────────────────────


class VelocityTracker:
    EMA_ALPHA = 0.3

    @classmethod
    def compute(cls, syllabus: list[dict], logs: list[dict]) -> dict[str, TopicVelocity]:
        topic_scores: dict[str, list[tuple[str, float]]] = {}
        for entry in logs:
            if not isinstance(entry, dict):
                continue
            topic = _map_to_syllabus_topic(entry.get("topic"), syllabus)
            score = entry.get("score")
            ts = str(entry.get("timestamp") or "")
            if topic and isinstance(score, (int, float)):
                topic_scores.setdefault(topic, []).append((ts, float(score)))

        velocity_map: dict[str, TopicVelocity] = {}
        for row in syllabus:
            if not isinstance(row, dict):
                continue
            topic = _normalize_topic(row.get("topic"))
            if not topic:
                continue
            tv = TopicVelocity(topic=topic)
            entries = sorted(topic_scores.get(topic, []), key=lambda x: x[0])
            if entries:
                tv.score_history = [s for _, s in entries]
                tv.timestamp_history = [t for t, _ in entries]
                tv.sessions_count = len(entries)
                tv.last_seen = entries[-1][0]
                if len(tv.score_history) >= 2:
                    deltas = [tv.score_history[i + 1] - tv.score_history[i] for i in range(len(tv.score_history) - 1)]
                    tv.velocity = round(sum(deltas) / len(deltas), 4)
                    ema = deltas[0]
                    for d in deltas[1:]:
                        ema = cls.EMA_ALPHA * d + (1 - cls.EMA_ALPHA) * ema
                    tv.momentum = round(ema, 4)
                if tv.sessions_count == 0:
                    tv.trend = "stalled"
                elif tv.momentum > 0.05:
                    tv.trend = "improving"
                elif tv.momentum < -0.05:
                    tv.trend = "declining"
                else:
                    tv.trend = "stable"
            else:
                tv.trend = "stalled"
            velocity_map[topic] = tv
        return velocity_map


# ── Stage 4: Weakness analyzer ────────────────────────────────────────────────


class WeaknessAnalyzer:
    SEVERITY_ORDER = ["low", "medium", "high", "critical"]

    def __init__(self, profile: StudentProfile):
        self.profile = profile

    def analyze(
        self,
        mastery: dict[str, float],
        velocity_map: dict[str, TopicVelocity],
        logs: list[dict],
        syllabus: list[dict],
    ) -> list[WeaknessFlag]:
        p = self.profile
        topic_signals: dict[str, list[tuple[str, str]]] = {}

        for topic, score in mastery.items():
            if score < p.review_threshold:
                sev = "critical" if score < 0.20 else ("high" if score < p.review_threshold else "medium")
                topic_signals.setdefault(topic, []).append(
                    (f"Mastery {score:.2f} below review threshold ({p.review_threshold:.2f})", sev)
                )

        for topic, tv in velocity_map.items():
            if tv.trend == "declining" and tv.sessions_count >= 2:
                topic_signals.setdefault(topic, []).append(
                    (f"Declining over {tv.sessions_count} sessions (velocity {tv.velocity:+.3f})", "medium")
                )
            elif tv.trend == "stalled" and mastery.get(topic, 0.5) < p.mastered_threshold:
                topic_signals.setdefault(topic, []).append(("No recent activity on this topic", "low"))

        topic_scores: dict[str, list[float]] = {}
        fail_counts: dict[str, int] = {}
        for entry in logs:
            if not isinstance(entry, dict):
                continue
            topic = _map_to_syllabus_topic(entry.get("topic"), syllabus)
            if not topic:
                continue
            score = entry.get("score")
            entry_type = str(entry.get("type") or "").lower()
            if entry_type in {"quiz", "exam"} and isinstance(score, (int, float)):
                topic_scores.setdefault(topic, []).append(float(score))
                if float(score) < p.review_threshold:
                    fail_counts[topic] = fail_counts.get(topic, 0) + 1

        for topic, scores in topic_scores.items():
            if len(scores) >= 2 and scores[-1] < scores[-2]:
                topic_signals.setdefault(topic, []).append(("Score dropped in most recent session", "medium"))
            if len(scores) >= 3 and scores[-1] < scores[-2] < scores[-3]:
                topic_signals.setdefault(topic, []).append(("Three consecutive score drops", "high"))

        for topic, count in fail_counts.items():
            if count > 2:
                topic_signals.setdefault(topic, []).append(
                    (f"Failed concept {count} times below threshold", "high" if count > 4 else "medium")
                )

        for topic, tv in velocity_map.items():
            if tv.momentum < -0.10 and tv.sessions_count >= 3:
                topic_signals.setdefault(topic, []).append(
                    (f"Strong negative momentum ({tv.momentum:+.3f})", "high")
                )

        flags: list[WeaknessFlag] = []
        for topic, signals in topic_signals.items():
            if not signals:
                continue
            max_sev = max(signals, key=lambda s: self.SEVERITY_ORDER.index(s[1]))[1]
            if len(signals) >= 3 and max_sev != "critical":
                idx = self.SEVERITY_ORDER.index(max_sev)
                max_sev = self.SEVERITY_ORDER[min(idx + 1, len(self.SEVERITY_ORDER) - 1)]
            seen: set[str] = set()
            reasons = [r for r, _ in signals if r not in seen and not seen.add(r)]
            flags.append(
                WeaknessFlag(
                    topic=topic,
                    reason=" | ".join(reasons[:3]),
                    severity=max_sev,
                    signal_count=len(signals),
                )
            )
        flags.sort(key=lambda f: (-self.SEVERITY_ORDER.index(f.severity), -f.signal_count))
        return flags[:15]


# ── Stage 5: Progress builder ─────────────────────────────────────────────────


class ProgressBuilder:
    def __init__(self, profile: StudentProfile):
        self.profile = profile

    def build(
        self,
        syllabus: list[dict],
        mastery: dict[str, float],
        velocity_map: dict[str, TopicVelocity],
    ) -> dict:
        p = self.profile
        topics = _ordered_topics(syllabus)
        completed = [t for t in topics if mastery.get(t, 0.0) >= p.mastered_threshold]
        weak = [t for t in topics if mastery.get(t, 0.0) < p.review_threshold]
        in_progress = [t for t in topics if t not in completed and t not in weak]

        n = len(topics)
        if n > 0:
            total_weight = weighted_sum = 0.0
            for i, topic in enumerate(topics):
                weight = 1.0 + (i / n)
                weighted_sum += mastery.get(topic, 0.0) * weight
                total_weight += weight
            overall_pct = round((weighted_sum / total_weight) * 100.0, 2) if total_weight else 0.0
        else:
            overall_pct = 0.0

        next_topic = next((t for t in topics if mastery.get(t, 0.0) < p.mastered_threshold), topics[-1] if topics else "")
        recommendation = self._recommend(overall_pct, weak, velocity_map, p)

        return {
            "completed_topics": completed,
            "in_progress_topics": in_progress,
            "weak_topics": weak,
            "mastery_summary": {t: round(mastery.get(t, 0.0), 4) for t in topics},
            "overall_progress_percent": overall_pct,
            "recommendation": recommendation,
            "next_topic": next_topic,
            "topic_trends": {t: velocity_map[t].trend for t in topics if t in velocity_map},
        }

    @staticmethod
    def _recommend(
        overall_pct: float,
        weak: list[str],
        velocity_map: dict[str, TopicVelocity],
        profile: StudentProfile,
    ) -> str:
        declining = sum(1 for tv in velocity_map.values() if tv.trend == "declining")
        if len(weak) >= 3 or declining >= 3:
            return "review"
        if overall_pct >= 80 and not weak:
            return "continue"
        if overall_pct < 30 or profile.learning_speed < 0.7:
            return "slow_down"
        return "continue"


# ── Stage 6: Risk assessor ────────────────────────────────────────────────────


class RiskAssessor:
    def __init__(self, profile: StudentProfile):
        self.profile = profile

    def assess(
        self,
        logs: list[dict],
        progress_report: dict,
        velocity_map: dict[str, TopicVelocity],
    ) -> tuple[bool, list[str]]:
        factors: list[str] = []
        p = self.profile

        timestamps = [t for e in logs if isinstance(e, dict) for t in [_parse_timestamp(e.get("timestamp"))] if t]
        if timestamps:
            inactive_days = (datetime.now(timezone.utc) - max(timestamps)).days
            if inactive_days >= p.inactivity_days:
                factors.append(f"No activity for {inactive_days} days (threshold: {p.inactivity_days})")

        weak_topics = progress_report.get("weak_topics") or []
        if len(weak_topics) >= 3:
            factors.append(f"{len(weak_topics)} topics below review threshold")

        streak = 0
        for entry in reversed(logs):
            if not isinstance(entry, dict):
                continue
            if str(entry.get("type") or "").lower() not in {"quiz", "exam"}:
                continue
            score = entry.get("score")
            if not isinstance(score, (int, float)):
                continue
            if float(score) < p.review_threshold:
                streak += 1
            else:
                break
        if streak >= 3:
            factors.append(f"{streak} consecutive quiz scores below {p.review_threshold:.0%}")

        declining = [t for t, tv in velocity_map.items() if tv.trend == "declining"]
        if len(declining) >= 3:
            factors.append(f"{len(declining)} topics in declining trend")

        overall_pct = float(progress_report.get("overall_progress_percent") or 0.0)
        if overall_pct < 20.0 and len(logs) > 5:
            factors.append(f"Overall mastery critically low at {overall_pct:.0f}%")

        neg_momentum = [t for t, tv in velocity_map.items() if tv.momentum < -0.10 and tv.sessions_count >= 2]
        if len(neg_momentum) >= 2:
            factors.append(f"Negative momentum on {len(neg_momentum)} topics")

        return bool(factors), factors


# ── Stage 7: LLM insights (narrative only) ────────────────────────────────────


class InsightsGenerator:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def enrich(self, agent: AnalyticsAgent, deterministic: dict) -> dict:
        profile = deterministic.get("student_profile") or {}
        progress = deterministic.get("progress_report") or {}
        context = {
            "student_id": deterministic.get("student_id"),
            "overall_progress": progress.get("overall_progress_percent"),
            "next_topic": progress.get("next_topic"),
            "weak_topics": progress.get("weak_topics"),
            "completed_topics": progress.get("completed_topics"),
            "recommendation": progress.get("recommendation"),
            "risk_flag": deterministic.get("risk_flag"),
            "risk_factors": deterministic.get("risk_factors"),
            "learning_speed": profile.get("learning_speed"),
            "consistency_score": profile.get("consistency_score"),
        }
        prompt = (
            "Student analytics context:\n"
            f"{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
            "Write a personal summary and motivating recommendations for this student."
        )
        personal_summary = ""
        motivating: list[str] = []
        next_action = str(deterministic.get("next_action") or "continue")
        try:
            result = agent._generate_with_retries(
                model=agent.settings.fast_model,
                system_prompt=ANALYTICS_AGENT_SYSTEM_PROMPT,
                user_prompt=prompt,
            )
            if isinstance(result, dict) and not result.get("error"):
                personal_summary = str(result.get("personal_summary") or "").strip()
                na = str(result.get("next_action") or "")
                if na in {"continue", "review", "slow_down", "take_break"}:
                    next_action = na
                recs = result.get("motivating_recommendations")
                if isinstance(recs, list):
                    motivating = [str(r) for r in recs[:3]]
        except Exception:
            pass
        return {
            "personal_summary": personal_summary,
            "next_action": next_action,
            "motivating_recommendations": motivating,
        }


# ── Main agent ────────────────────────────────────────────────────────────────


class AnalyticsAgent(AgentPair):
    """
    Merged pipeline:
      1 StudentProfile  2 MasteryEngine  3 VelocityTracker
      4 WeaknessAnalyzer  5 ProgressBuilder  6 RiskAssessor  7 InsightsGenerator (generate only)
    """

    def __init__(self, llm: LLMClient):
        super().__init__("analytics-agent", llm)

    @staticmethod
    def _validate_state(state: dict) -> dict | None:
        required = ("student_id", "personal_syllabus", "mastery_state", "interaction_logs")
        for field_name in required:
            if field_name not in state:
                return {"error": "missing_field", "field": field_name}
        if not isinstance(state.get("personal_syllabus"), list):
            return {"error": "missing_field", "field": "personal_syllabus"}
        if not isinstance(state.get("mastery_state"), dict):
            return {"error": "missing_field", "field": "mastery_state"}
        if not isinstance(state.get("interaction_logs"), list):
            return {"error": "missing_field", "field": "interaction_logs"}
        return None

    @staticmethod
    def _profile_to_dict(profile: StudentProfile) -> dict:
        return {
            "learning_speed": profile.learning_speed,
            "consistency_score": profile.consistency_score,
            "avg_quiz_score": profile.avg_quiz_score,
            "total_interactions": profile.total_interactions,
            "adaptive_params": {
                "mastery_gain_correct": profile.mastery_gain_correct,
                "mastery_loss_wrong": profile.mastery_loss_wrong,
                "passive_gain": profile.passive_gain,
                "mastered_threshold": profile.mastered_threshold,
                "review_threshold": profile.review_threshold,
                "inactivity_days": profile.inactivity_days,
            },
        }

    @staticmethod
    def _velocity_to_dict(velocity_map: dict[str, TopicVelocity]) -> dict:
        return {
            t: {
                "velocity": tv.velocity,
                "momentum": tv.momentum,
                "trend": tv.trend,
                "sessions_count": tv.sessions_count,
                "last_seen": tv.last_seen,
            }
            for t, tv in velocity_map.items()
        }

    @staticmethod
    def _next_action(progress_report: dict, risk_flag: bool) -> str:
        if risk_flag:
            return "review"
        rec = str(progress_report.get("recommendation") or "continue")
        return rec if rec in {"continue", "review", "slow_down", "take_break"} else "continue"

    def _run_pipeline(self, state: dict) -> tuple[StudentProfile, dict[str, float], dict[str, TopicVelocity], dict]:
        syllabus = state["personal_syllabus"]
        logs = state.get("interaction_logs") or []
        event = state.get("current_event")

        profile = StudentProfileBuilder.build(
            student_id=str(state.get("student_id")),
            interaction_logs=logs,
            mastery_state=state.get("mastery_state") or {},
        )
        engine = MasteryEngine(profile)
        mastery = engine.seed(syllabus, state.get("mastery_state"))
        mastery = engine.replay_logs(mastery, logs, syllabus)
        mastery = engine.apply_event(mastery, event if isinstance(event, dict) else None, syllabus)

        velocity_map = VelocityTracker.compute(syllabus, logs)
        weakness_flags = WeaknessAnalyzer(profile).analyze(mastery, velocity_map, logs, syllabus)
        progress_report = ProgressBuilder(profile).build(syllabus, mastery, velocity_map)
        risk_flag, risk_factors = RiskAssessor(profile).assess(logs, progress_report, velocity_map)

        output = {
            "student_id": str(state.get("student_id")),
            "timestamp": _utc_now_iso(),
            "student_profile": self._profile_to_dict(profile),
            "mastery_state": mastery,
            "velocity_map": self._velocity_to_dict(velocity_map),
            "weakness_flags": [
                {
                    "topic": f.topic,
                    "reason": f.reason,
                    "severity": f.severity,
                    "signal_count": f.signal_count,
                }
                for f in weakness_flags
            ],
            "progress_report": progress_report,
            "risk_flag": risk_flag,
            "risk_factors": risk_factors,
            "next_action": self._next_action(progress_report, risk_flag),
        }
        return profile, mastery, velocity_map, output

    def process(self, state: dict) -> dict:
        """Deterministic pipeline — used after exams/quizzes and internally by generate()."""
        error = self._validate_state(state)
        if error:
            return error
        _, _, _, output = self._run_pipeline(state)
        return output

    def generate(self, metrics: dict) -> dict:
        """Full pipeline + optional LLM narrative for GET /analytics/summary."""
        state = {
            "student_id": str(metrics.get("student_id") or ""),
            "personal_syllabus": metrics.get("personal_syllabus") or [],
            "mastery_state": metrics.get("mastery_state") or {},
            "interaction_logs": metrics.get("interaction_logs") or [],
            "current_event": metrics.get("current_event") or {"type": "summary", "payload": {}},
        }
        if self._validate_state(state):
            insights = self._build_insights_response({}, metrics)
            insights["agent_output"] = {}
            return insights

        profile, _, _, deterministic = self._run_pipeline(state)
        llm_layer = InsightsGenerator(self.llm).enrich(self, deterministic)
        if llm_layer.get("personal_summary"):
            deterministic = {**deterministic, **llm_layer}

        insights = self._build_insights_response(deterministic, metrics, profile)
        insights["agent_output"] = deterministic
        return insights

    def to_analytics_payload(self, output: dict) -> dict:
        """Map agent output to frontend AnalyticsPayload shape."""
        progress = output.get("progress_report") or {}
        mastery = output.get("mastery_state") or {}
        velocity_map = output.get("velocity_map") or {}
        profile = output.get("student_profile") or {}
        next_topic = str(progress.get("next_topic") or "")
        overall = float(progress.get("overall_progress_percent") or 0.0) / 100.0
        risk_flag = bool(output.get("risk_flag"))
        risk_factors = output.get("risk_factors") or []
        risk_level = "high" if risk_flag else ("medium" if progress.get("weak_topics") else "low")

        motivating = output.get("motivating_recommendations") or []
        recommendations = [
            {"type": "focus", "message": f"Next topic: {next_topic}", "priority": "high"}
        ] if next_topic else []
        for msg in motivating[:2]:
            recommendations.append({"type": "motivation", "message": str(msg), "priority": "medium"})

        return {
            "status": "ok",
            "student_id": str(output.get("student_id") or ""),
            "student_profile": profile,
            "mastery_update": {
                "topic": next_topic,
                "new_score": float(mastery.get(next_topic, 0.5)) if next_topic else overall,
                "overall_mastery": overall,
            },
            "knowledge_map": {k: float(v) for k, v in mastery.items()},
            "velocity_map": velocity_map,
            "overall_mastery": overall,
            "risk_score": 0.85 if risk_level == "high" else (0.5 if risk_level == "medium" else 0.15),
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "next_action": str(output.get("next_action") or "continue"),
            "recommendations": recommendations,
            "milestones": [
                {
                    "type": "progress",
                    "message": f"Overall progress: {overall * 100:.0f}%",
                    "topic": next_topic or None,
                }
            ],
            "mastery_state": {
                "overall_accuracy": overall,
                "topics": {k: float(v) for k, v in mastery.items()},
                "topic_trends": progress.get("topic_trends") or {},
            },
        }

    def _build_insights_response(
        self,
        output: dict,
        metrics: dict | None = None,
        profile: StudentProfile | None = None,
    ) -> dict:
        metrics = metrics or {}
        progress = output.get("progress_report") or {}
        mastery = output.get("mastery_state") or {}
        weakness_flags = output.get("weakness_flags") or []
        student_profile = output.get("student_profile") or {}

        completed = progress.get("completed_topics") or []
        weak = progress.get("weak_topics") or []
        next_topic = str(progress.get("next_topic") or "").strip()
        overall_pct = float(progress.get("overall_progress_percent") or 0.0)

        strengths = [
            {"concept": t, "evidence": f"Mastery {float(mastery.get(t, 0)):.0%} — topic mastered."}
            for t in completed[:4]
        ]
        weaknesses = [
            {
                "concept": str(f.get("topic") or ""),
                "evidence": str(f.get("reason") or "Needs review."),
                "severity": str(f.get("severity") or "medium"),
            }
            for f in weakness_flags[:4]
        ]
        if not weaknesses and weak:
            weaknesses = [
                {
                    "concept": t,
                    "evidence": f"Mastery {float(mastery.get(t, 0)):.0%} is below review threshold.",
                    "severity": "high",
                }
                for t in weak[:4]
            ]

        risk_level = "high" if output.get("risk_flag") else ("medium" if weak else "low")
        recommendation = str(progress.get("recommendation") or "continue")
        learning_speed = student_profile.get("learning_speed") or (profile.learning_speed if profile else 1.0)
        consistency = student_profile.get("consistency_score") or (profile.consistency_score if profile else 0.5)

        patterns = [
            f"Overall syllabus progress: {overall_pct:.0f}%.",
            f"Completed: {len(completed)} topics · Weak: {len(weak)} topics.",
            f"Learning speed: {float(learning_speed):.2f} · Consistency: {float(consistency):.0%}.",
        ]
        if metrics.get("lesson_completion_rate") is not None:
            patterns.append(f"Lesson completion rate: {float(metrics['lesson_completion_rate']) * 100:.0f}%.")

        default_summary = (
            f"Progress at {overall_pct:.0f}% across your personal syllabus. "
            f"Next focus: {next_topic or 'syllabus start'}. "
            f"Recommendation: {recommendation.replace('_', ' ')}."
        )

        return {
            "summary": str(output.get("personal_summary") or default_summary),
            "strengths": strengths,
            "weaknesses": weaknesses,
            "patterns": patterns,
            "motivating_recommendations": output.get("motivating_recommendations") or [],
            "recommendations": [
                {
                    "priority": 1,
                    "action": f"Work on: {next_topic}." if next_topic else "Continue with the next syllabus topic.",
                    "target_concept": next_topic,
                },
                {
                    "priority": 2,
                    "action": "Review weak topics before advancing.",
                    "target_concept": weak[0] if weak else next_topic,
                },
            ],
            "next_best_lesson": {
                "topic": next_topic or "syllabus start",
                "reason": "Selected by syllabus order and adaptive mastery threshold.",
            },
            "risk_level": risk_level,
            "risk_factors": output.get("risk_factors") or [],
            "confidence": "high" if completed else ("medium" if mastery else "low"),
        }
