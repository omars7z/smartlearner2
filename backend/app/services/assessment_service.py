import random
import re
from typing import Any

from app.services.guardrails import safe_json_loads
from app.services.llm_client import LLMClient


class AssessmentService:
    QUESTION_COUNT = 5

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def _normalize_questions(self, raw: Any, *, topic: str, level: str) -> list[dict]:
        payload = raw
        if isinstance(raw, dict):
            if isinstance(raw.get("questions"), list):
                payload = raw.get("questions")
            elif isinstance(raw.get("assessment"), list):
                payload = raw.get("assessment")
            else:
                payload = [raw]
        if not isinstance(payload, list):
            payload = []

        out: list[dict] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or "").strip()
            choices = item.get("choices")
            if not isinstance(choices, list):
                choices = []
            # Ensure exactly 4 distinct choices (case-insensitive), preserve order where possible.
            norm_choices: list[str] = []
            seen_choices: set[str] = set()
            for c in choices:
                t = str(c).strip()
                if not t:
                    continue
                key = t.lower()
                if key in seen_choices:
                    continue
                seen_choices.add(key)
                norm_choices.append(t)
            correct = str(item.get("correct_answer") or "").strip()
            concept = str(item.get("concept") or topic).strip() or topic
            if not question:
                continue
            if correct and correct.lower() not in {c.lower() for c in norm_choices}:
                norm_choices.append(correct)
            while len(norm_choices) < 4:
                idx = len(norm_choices) + 1
                filler = f"Common misconception about {topic} ({idx})"
                if filler.lower() not in {c.lower() for c in norm_choices}:
                    norm_choices.append(filler)
            norm_choices = norm_choices[:4]
            if not correct or correct.lower() not in {c.lower() for c in norm_choices}:
                correct = norm_choices[0]
            out.append(
                {
                    "question": question,
                    "choices": norm_choices,
                    "correct_answer": correct,
                    "concept": concept,
                    "topic": topic,
                    "difficulty": level,
                }
            )
            if len(out) >= self.QUESTION_COUNT:
                break

        while len(out) < self.QUESTION_COUNT:
            n = len(out) + 1
            correct = f"Concept-focused answer about {topic} ({n})"
            wrongs = [
                f"Incorrect option A for {topic} ({n})",
                f"Incorrect option B for {topic} ({n})",
                f"Incorrect option C for {topic} ({n})",
            ]
            choices = wrongs + [correct]
            random.shuffle(choices)
            out.append(
                {
                    "question": f"Q{n}: Which statement best matches {topic}?",
                    "choices": choices,
                    "correct_answer": correct,
                    "concept": topic,
                    "topic": topic,
                    "difficulty": level,
                }
            )
        return out

    def _extract_concepts(self, lesson_title: str, lesson_markdown: str, topic: str) -> list[str]:
        text = lesson_markdown or ""
        concepts: list[str] = []

        # Prefer markdown headings as they usually represent core lesson concepts.
        for m in re.finditer(r"^\s{0,3}#{2,3}\s+(.+)$", text, flags=re.MULTILINE):
            c = m.group(1).strip()
            if c and len(c) <= 80:
                concepts.append(c)

        # Fall back to Python-like identifiers from content.
        if len(concepts) < self.QUESTION_COUNT:
            for m in re.finditer(r"\b[a-zA-Z_][a-zA-Z0-9_]{3,}\b", text):
                t = m.group(0)
                lo = t.lower()
                if lo in {"python", "print", "input", "while", "for", "return", "true", "false"}:
                    continue
                concepts.append(t.replace("_", " "))
                if len(concepts) >= self.QUESTION_COUNT * 3:
                    break

        seed_items = [lesson_title.strip(), topic.strip(), "lesson basics", "core idea", "practice"]
        concepts.extend(seed_items)

        out: list[str] = []
        seen: set[str] = set()
        for c in concepts:
            key = c.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(c.strip())
            if len(out) >= self.QUESTION_COUNT:
                break
        return out

    def _fallback_questions(
        self,
        *,
        topic: str,
        level: str,
        lesson_title: str,
        lesson_markdown: str,
        attempt_number: int,
    ) -> list[dict]:
        concepts = self._extract_concepts(lesson_title, lesson_markdown, topic)
        templates = [
            "Which statement best explains {concept} in this lesson?",
            "What is the most accurate description of {concept}?",
            "In the context of this lesson, what does {concept} mainly mean?",
            "Which option correctly applies {concept}?",
            "If you were solving exercises here, how should {concept} be used?",
        ]
        start = (attempt_number - 1) % len(templates)
        questions: list[dict] = []
        for i in range(self.QUESTION_COUNT):
            concept = concepts[i] if i < len(concepts) else topic
            stem = templates[(start + i) % len(templates)].format(concept=concept)
            correct = f"It focuses on {concept} as taught in this lesson and applies it correctly in Python practice."
            wrongs = [
                f"It is unrelated to {topic} and only appears in advanced unrelated chapters.",
                f"It means code using {concept} never needs testing or debugging.",
                f"It can only be used in one very specific framework, not general Python learning.",
            ]
            choices = wrongs + [correct]
            random.shuffle(choices)
            questions.append(
                {
                    "question": stem,
                    "choices": choices,
                    "correct_answer": correct,
                    "concept": concept,
                    "topic": topic,
                    "difficulty": level,
                }
            )
        return questions

    async def generate_assessment(
        self,
        *,
        topic: str,
        level: str,
        lesson_title: str,
        lesson_markdown: str,
        attempt_number: int,
        previous_questions: list[dict] | None = None,
    ) -> list[dict]:
        previous_stems = {
            str(q.get("question") or "").strip().lower()
            for q in (previous_questions or [])
            if isinstance(q, dict)
        }

        seed = random.randint(1000, 99999)
        system_prompt = (
            "You generate quick lesson assessments in JSON only. "
            "Return exactly 5 MCQ questions under key `questions`. "
            "Each question must include: question, choices (4 distinct strings), "
            "correct_answer (must match one choice exactly), concept."
        )
        user_prompt = (
            f"Lesson title: {lesson_title}\n"
            f"Topic: {topic}\n"
            f"Difficulty: {level}\n"
            f"Attempt number: {attempt_number}\n"
            f"Variation seed: {seed}\n"
            "Generate NEW questions for this attempt, but keep same topic and similar difficulty.\n"
            f"Lesson context:\n{lesson_markdown[:2500]}"
        )
        best: list[dict] = []
        for _ in range(3):
            try:
                raw_json = self.llm.generate_json(
                    model=self.llm.settings.smart_model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
                parsed = safe_json_loads(raw_json)
            except Exception:
                parsed = {"questions": []}
            candidate = self._normalize_questions(parsed, topic=topic, level=level)
            if not candidate:
                candidate = self._fallback_questions(
                    topic=topic,
                    level=level,
                    lesson_title=lesson_title,
                    lesson_markdown=lesson_markdown,
                    attempt_number=attempt_number,
                )
            if not previous_stems:
                return candidate
            overlap = 0
            for q in candidate:
                stem = str(q.get("question") or "").strip().lower()
                if stem in previous_stems:
                    overlap += 1
            if overlap <= 1:
                return candidate
            best = candidate
            seed = random.randint(1000, 99999)
            user_prompt = (
                f"Lesson title: {lesson_title}\n"
                f"Topic: {topic}\n"
                f"Difficulty: {level}\n"
                f"Attempt number: {attempt_number}\n"
                f"Variation seed: {seed}\n"
                "Generate NEW questions for this attempt, but keep same topic and similar difficulty.\n"
                f"Lesson context:\n{lesson_markdown[:2500]}"
            )
        if best:
            return best
        return self._fallback_questions(
            topic=topic,
            level=level,
            lesson_title=lesson_title,
            lesson_markdown=lesson_markdown,
            attempt_number=attempt_number,
        )

