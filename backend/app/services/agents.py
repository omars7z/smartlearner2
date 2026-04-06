import json
import random

from app.core.config import get_settings
from app.core.placement_rubric import concepts_for_level, normalize_level
from app.services.guardrails import (
    has_python3_hallucinations,
    safe_json_loads,
    sanitize_prompt,
    validate_content_scope,
)
from app.services.llm_client import LLMClient
from app.services.rag_service import RAGService


class AgentValidationError(Exception):
    pass


def _qa_source_grounding_suffix() -> str:
    s = get_settings()
    return (
        f"\n\n(Source grounding: {s.source_resource}; {s.source_scope}. "
        "Concepts: expressions, values, data types, string replication.)"
    )


class AgentPair:
    def __init__(self, name: str, llm: LLMClient):
        self.name = name
        self.llm = llm
        self.settings = get_settings()

    def _generate_with_retries(self, model: str, system_prompt: str, user_prompt: str) -> dict:
        last_error = "Unknown error"
        for _ in range(3):
            raw = self.llm.generate_json(model=model, system_prompt=system_prompt, user_prompt=user_prompt)
            try:
                return safe_json_loads(raw)
            except json.JSONDecodeError as exc:
                last_error = str(exc)
        raise AgentValidationError(f"JSON parsing failed after 3 retries: {last_error}")


def _extract_question_obj(payload: dict) -> dict | None:
    q = payload.get("question") if isinstance(payload.get("question"), dict) else payload
    if isinstance(q, dict) and "question" in q and "choices" in q:
        return q
    if isinstance(payload.get("questions"), list) and payload["questions"]:
        first = payload["questions"][0]
        if isinstance(first, dict):
            return first
    return None


class PlacementGeneratorAgent(AgentPair):
    """LLM + RAG: MCQs aligned to the placement rubric (Python for Everybody scope)."""

    def __init__(self, llm: LLMClient, rag: RAGService):
        super().__init__("placement-generator", llm)
        self.rag = rag

    def generate(self, level: str, question_count: int) -> dict:
        lvl = normalize_level(level)
        forced_concepts = concepts_for_level(lvl)
        if question_count != len(forced_concepts):
            raise AgentValidationError(
                f"Placement expects exactly {len(forced_concepts)} questions per level; got {question_count}."
            )

        all_chunks = self.rag.retrieve_python_basics_context(
            f"python for everybody {lvl} placement diagnostic {forced_concepts[0]}",
            k=24,
        )
        if not all_chunks:
            raise AgentValidationError("No context chunks available for placement generation.")

        selected_chunks = random.sample(all_chunks, min(max(question_count * 2, 10), len(all_chunks)))
        questions: list[dict] = []

        for idx in range(question_count):
            rubric_concept = forced_concepts[idx]
            chunk = selected_chunks[idx % len(selected_chunks)]
            chunk_text = str(chunk).strip()
            for _ in range(5):
                payload = self._generate_with_retries(
                    model=self.settings.smart_model,
                    system_prompt=(
                        "Placement MCQ generator for Python for Everybody (University of Michigan) material. "
                        "Return JSON with one question object only: "
                        "question (string), choices (array of exactly 4 distinct strings), correct_answer "
                        "(must equal one of choices), concept (ignored — set to empty string). "
                        "Questions must test understanding, not trivia, and match the rubric objective."
                    ),
                    user_prompt=(
                        f"Placement level: {lvl}. RAG context:\n{chunk_text}\n\n"
                        f"Rubric objective (must be the skill tested): {rubric_concept}\n"
                        f"Question slot {idx + 1} of {question_count} for this level.\n"
                        "Write ONE multiple-choice question that assesses this objective using ideas from the context. "
                        "Do not repeat wording from other slots. "
                        "Keep difficulty appropriate for this placement stage."
                    ),
                )
                question_obj = _extract_question_obj(payload)
                if not question_obj or not isinstance(question_obj, dict):
                    continue
                text = str(question_obj.get("question", "")).strip()
                choices = question_obj.get("choices", [])
                correct = question_obj.get("correct_answer")
                if not text or not isinstance(choices, list) or len(choices) != 4 or correct is None:
                    continue
                questions.append(
                    {
                        "question": text,
                        "choices": list(choices),
                        "correct_answer": str(correct),
                        "concept": rubric_concept,
                    }
                )
                break
            else:
                raise AgentValidationError(
                    f"Placement generator could not produce a well-formed MCQ for slot {idx + 1}."
                )

        return {"questions": questions}


def _validate_placement_deterministic(data: dict, level: str, question_count: int) -> dict:
    """Rule-based validation and normalization (authoritative rubric enforcement)."""
    from app.core.placement_rubric import concepts_for_level, validate_question_concepts_for_level

    lvl = normalize_level(level)
    questions = data.get("questions") or []
    if len(questions) != question_count:
        raise AgentValidationError(
            f"Placement validator expected {question_count} questions, got {len(questions)}."
        )

    seen_texts: set[str] = set()
    normalized: list[dict] = []

    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            raise AgentValidationError(f"Question {i + 1} is not an object.")
        text = str(q.get("question", "")).strip()
        if not text:
            raise AgentValidationError(f"Question {i + 1} has empty text.")
        text_lower = text.lower()
        if text_lower in seen_texts:
            raise AgentValidationError(f"Duplicate question text at index {i + 1}.")
        seen_texts.add(text_lower)

        choices = q.get("choices", [])
        if not isinstance(choices, list) or len(choices) != 4:
            raise AgentValidationError(f"Question {i + 1} must have exactly 4 choices.")
        correct = q.get("correct_answer")
        norm_choices = [str(c).strip() for c in choices]
        correct_str = str(correct).strip()
        if correct_str not in norm_choices:
            raise AgentValidationError(f"Question {i + 1}: correct_answer must be one of choices.")
        if lvl == "beginner" and "asyncio" in text_lower:
            raise AgentValidationError(f"Question {i + 1}: beginner level must not reference asyncio.")

        normalized.append(
            {
                "question": text,
                "choices": norm_choices,
                "correct_answer": correct_str,
                "concept": str(q.get("concept") or "").strip(),
            }
        )

    expected = list(concepts_for_level(lvl))
    for i, row in enumerate(normalized):
        if row["concept"] != expected[i]:
            raise AgentValidationError(
                f"Question {i + 1}: concept must match rubric slot {expected[i]!r}; got {row['concept']!r}."
            )

    try:
        validate_question_concepts_for_level(normalized, lvl)
    except ValueError as exc:
        raise AgentValidationError(str(exc)) from exc

    return {"questions": normalized}


_PLACEMENT_VALIDATOR_SYSTEM = """You are PlacementValidatorAgent. Validate placement MCQs for Python for Everybody.
You receive JSON with:
- placement_level (string)
- expected_question_count (int)
- rubric_concepts_in_order (array of exact concept strings, one per slot)
- candidate_questions (array)

Check: each question has non-empty stem, exactly 4 distinct choices (strings), correct_answer must equal one choice after trim,
no duplicate stems (case-insensitive), for beginner level stems must not mention asyncio,
and for each index i concept must EXACTLY equal rubric_concepts_in_order[i].
Return JSON only:
{"valid": true, "questions": [ ... normalized objects with question, choices, correct_answer, concept ... ]}
or {"valid": false, "error": "brief reason"}.
If valid, echo normalized questions with correct_answer and choices as trimmed strings."""


class PlacementValidatorAgent(AgentPair):
    """LLM-assisted validation (validator API key) with deterministic rubric enforcement as fallback."""

    name = "placement-validator"

    def __init__(self, llm: LLMClient):
        super().__init__("placement-validator", llm)

    def validate(self, data: dict, level: str, question_count: int) -> dict:
        lvl = normalize_level(level)
        expected = list(concepts_for_level(lvl))
        payload = {
            "placement_level": lvl,
            "expected_question_count": question_count,
            "rubric_concepts_in_order": expected,
            "candidate_questions": data.get("questions") or [],
        }
        user_prompt = json.dumps(payload, ensure_ascii=False)
        try:
            out = self._generate_with_retries(
                model=self.settings.fast_model,
                system_prompt=_PLACEMENT_VALIDATOR_SYSTEM,
                user_prompt=user_prompt,
            )
            if not isinstance(out, dict) or not out.get("valid"):
                raise AgentValidationError(str(out.get("error") or "PlacementValidatorAgent rejected input"))
            merged = {"questions": out.get("questions") or []}
            return _validate_placement_deterministic(merged, level, question_count)
        except AgentValidationError:
            return _validate_placement_deterministic(data, level, question_count)


class SyllabusGeneratorAgent(AgentPair):
    def __init__(self, llm: LLMClient):
        super().__init__("syllabus-generator", llm)

    def generate(self, score: int, level: str) -> dict:
        from app.core.placement_rubric import SYLLABUS_TOPIC_ALLOWLIST_BY_LEVEL, normalize_level

        lvl = normalize_level(level)
        allowed = sorted(SYLLABUS_TOPIC_ALLOWLIST_BY_LEVEL.get(lvl, frozenset()))
        allowed_txt = ", ".join(allowed) if allowed else "(choose standard Python foundations topics)"
        return self._generate_with_retries(
            model=self.settings.smart_model,
            system_prompt=(
                "Syllabus generator for Python for Everybody (University of Michigan) scope. "
                "Return JSON with lessons[] array of unique items. "
                "Each lesson MUST have 'topic' and 'description' fields. "
                "The 'topic' value must be copied exactly from the allowed list in the user message. "
                "Never repeat the same topic. Order lessons from foundational to more advanced within this band."
            ),
            user_prompt=(
                f"Placement level: {lvl}. Score index: {score}. "
                f"Allowed lesson topic strings (use each at most once, pick a subset that fits the learner): {allowed_txt}. "
                "Ensure each topic appears only once."
            ),
        )


class SyllabusValidatorAgent:
    name = "syllabus-validator"

    def validate(self, payload: dict, placement_level: str | None = None) -> dict:
        from app.core.placement_rubric import validate_syllabus_topics_for_level

        lessons = payload.get("lessons", [])
        if not isinstance(lessons, list) or not lessons:
            raise AgentValidationError("Syllabus must contain a non-empty lessons array.")

        seen_topics: set[str] = set()
        unique_lessons: list[dict] = []
        for lesson in lessons:
            if not isinstance(lesson, dict):
                continue
            topic = lesson.get("topic", "")
            if topic and topic not in seen_topics:
                seen_topics.add(topic)
                unique_lessons.append(lesson)

        out = {**payload, "lessons": unique_lessons}
        topics = [lesson.get("topic", "") for lesson in unique_lessons]

        if placement_level:
            try:
                validate_syllabus_topics_for_level(unique_lessons, placement_level)
            except ValueError as exc:
                raise AgentValidationError(str(exc)) from exc

        if "Variable Assignment" in topics and "Expressions" in topics:
            i_exp = next(i for i, l in enumerate(unique_lessons) if l.get("topic") == "Expressions")
            i_var = next(i for i, l in enumerate(unique_lessons) if l.get("topic") == "Variable Assignment")
            if i_exp > i_var:
                exp_lesson = unique_lessons.pop(i_exp)
                i_var = next(i for i, l in enumerate(unique_lessons) if l.get("topic") == "Variable Assignment")
                unique_lessons.insert(i_var, exp_lesson)
                topics = [lesson.get("topic", "") for lesson in unique_lessons]

        if len(set(topics)) != len(topics):
            raise AgentValidationError("Syllabus contains circular/duplicate dependencies.")

        return out


class LessonGeneratorAgent(AgentPair):
    def __init__(self, llm: LLMClient, rag: RAGService):
        super().__init__("lesson-generator", llm)
        self.rag = rag

    def generate(self, topic: str) -> dict:
        context = self.rag.retrieve_python_basics_context(topic, k=5)
        sanitized_topic = sanitize_prompt(topic)
        payload = self._generate_with_retries(
            model=self.settings.smart_model,
            system_prompt=(
                "Lesson generator for Python for Everybody (Charles Severance, University of Michigan), "
                "the open materials used in the Coursera Python specialization. "
                "Return JSON with 'markdown' field as the sole content. "
                "The lesson MUST cite 'Python for Everybody' explicitly. "
                "Base your explanation on the provided course-text context. "
                "Include relevant Python concepts like expressions, data types, variable assignment, "
                "or string replication where applicable."
            ),
            user_prompt=(
                f"Topic: {sanitized_topic}\n\nCourse text context:\n{context}\n\n"
                "Generate a comprehensive lesson on this topic aligned with Python for Everybody."
            ),
        )
        return payload


class LessonValidatorAgent:
    name = "lesson-validator"

    def validate(self, payload: dict) -> dict:
        markdown = str(payload.get("markdown", ""))
        if "python for everybody" not in markdown.lower():
            s = get_settings()
            suffix = (
                f"\n\n(Source: Python for Everybody (Charles Severance, University of Michigan). "
                f"Resource: {s.source_resource}; Scope: {s.source_scope}. "
                "Covers core Python concepts: expressions, data types, variable assignment, string operations.)"
            )
            markdown = markdown.rstrip() + suffix
            payload["markdown"] = markdown
        ok, reason = validate_content_scope(markdown)
        if not ok:
            raise AgentValidationError(reason)
        return payload


class QAGeneratorAgent(AgentPair):
    _QA_SYSTEM = (
        "You are a tutor for Python for Everybody (Charles Severance, University of Michigan; Coursera). "
        "Respond ONLY with valid JSON: "
        '{"answer": "<markdown or plain text>"}. '
        "Use the provided RAG context as primary evidence; explain Python topics those chunks support. "
        "Do not assume the learner is locked to one sub-topic unless the question or context clearly implies it. "
        "The answer field MUST contain the exact substring: Python for Everybody."
    )

    def __init__(self, llm: LLMClient, rag: RAGService):
        super().__init__("qa-generator", llm)
        self.rag = rag

    def generate(self, question: str, lesson_markdown: str) -> dict:
        safe_question = sanitize_prompt(question)
        context = self.rag.retrieve_python_basics_context(safe_question, k=4)
        payload = self._generate_with_retries(
            model=self.settings.smart_model,
            system_prompt=self._QA_SYSTEM,
            user_prompt=(
                f"Optional app context (may be generic): {lesson_markdown}\n"
                f"Question: {safe_question}\n"
                f"RAG context: {context}"
            ),
        )
        payload["rag"] = {
            "chunks_used": len(context),
            "selected_chunks": [
                {"text": chunk, "source": self.settings.source_resource} for chunk in context
            ],
        }
        return payload


class QAValidatorAgent:
    name = "qa-validator"

    def validate(self, payload: dict) -> dict:
        answer = str(payload.get("answer", ""))
        if has_python3_hallucinations(answer):
            raise AgentValidationError("Hallucinated Python 2-only functions detected.")
        if "python for everybody" not in answer.lower():
            payload["answer"] = answer.rstrip() + _qa_source_grounding_suffix()
        return payload
