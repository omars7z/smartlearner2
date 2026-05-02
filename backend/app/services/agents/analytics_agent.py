from __future__ import annotations


class AnalyticsAgent:
    """Deterministic analytics agent: derives insight text from computed metrics."""

    name = "analytics-agent"

    def generate(self, metrics: dict) -> dict:
        placement_pct = float(metrics.get("placement_percentage") or 0.0)
        completion_rate = float(metrics.get("lesson_completion_rate") or 0.0)
        strong_topics = [str(x).strip() for x in (metrics.get("strong_topics") or []) if str(x).strip()]
        weak_topics = [str(x).strip() for x in (metrics.get("weak_topics") or []) if str(x).strip()]
        recommended_start = str(metrics.get("recommended_start_topic") or "").strip()

        blended_score = (0.65 * placement_pct) + (0.35 * (completion_rate * 100.0))
        if blended_score >= 75:
            risk_level = "low"
        elif blended_score >= 45:
            risk_level = "medium"
        else:
            risk_level = "high"

        evidence_prefix = (
            f"Placement {placement_pct:.0f}% and lesson completion {completion_rate * 100:.0f}%."
            if metrics.get("has_placement")
            else f"No placement yet; lesson completion {completion_rate * 100:.0f}%."
        )

        strengths = [
            {"concept": topic, "evidence": f"{evidence_prefix} Concept appears in strong topics list."}
            for topic in strong_topics[:4]
        ]
        weaknesses = [
            {
                "concept": topic,
                "evidence": "Detected as weak topic from placement/learning signals.",
                "severity": "high" if i < 2 else "medium",
            }
            for i, topic in enumerate(weak_topics[:4])
        ]

        patterns: list[str] = []
        if metrics.get("total_answered", 0) == 0:
            patterns.append("No answered placement/assessment items yet, so confidence is limited.")
        else:
            patterns.append(
                f"Answered items: {int(metrics.get('total_answered') or 0)}; signal quality improves with more attempts."
            )
        if completion_rate < 0.35:
            patterns.append("Low lesson completion suggests consistency is the main bottleneck.")
        elif completion_rate < 0.7:
            patterns.append("Moderate completion; student benefits from stronger weekly study cadence.")
        else:
            patterns.append("High completion consistency indicates good learning momentum.")

        target = recommended_start or (weak_topics[0] if weak_topics else (strong_topics[0] if strong_topics else "core fundamentals"))
        recommendations = [
            {"priority": 1, "action": f"Start next lesson focus on: {target}.", "target_concept": target},
            {
                "priority": 2,
                "action": "After each lesson, complete the quick assessment and review wrong answers immediately.",
                "target_concept": weak_topics[0] if weak_topics else target,
            },
            {
                "priority": 3,
                "action": "Keep strengths warm by doing one short recap exercise before moving to new topics.",
                "target_concept": strong_topics[0] if strong_topics else target,
            },
        ]

        if placement_pct >= 80 and completion_rate >= 0.7:
            confidence = "high"
        elif metrics.get("has_placement") or completion_rate > 0:
            confidence = "medium"
        else:
            confidence = "low"

        summary = (
            f"Current estimated mastery is {blended_score:.0f}% based on placement and lesson progression. "
            f"Primary next focus is {target}, with risk currently {risk_level}."
        )

        return {
            "summary": summary,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "patterns": patterns,
            "recommendations": recommendations,
            "next_best_lesson": {
                "topic": target,
                "reason": "Chosen from weak/recommended concepts with highest expected learning gain.",
            },
            "risk_level": risk_level,
            "confidence": confidence,
        }

