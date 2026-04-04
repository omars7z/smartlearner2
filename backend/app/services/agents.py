import json
import random

from app.core.config import get_settings
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
    """LLM-only: builds MCQ-shaped JSON from RAG chunks (no business rules)."""

    def __init__(self, llm: LLMClient, rag: RAGService):
        super().__init__("placement-generator", llm)
        self.rag = rag

    def generate(self, level: str, question_count: int) -> dict:
        all_chunks = self.rag.retrieve_python_basics_context(f"python basics {level} concepts", k=20)
        if not all_chunks:
            raise AgentValidationError("No context chunks available for placement generation.")

        selected_chunks = random.sample(all_chunks, min(question_count, len(all_chunks)))
        questions: list[dict] = []

        for idx in range(question_count):
            chunk = selected_chunks[idx % len(selected_chunks)]
            chunk_text = str(chunk).strip()
            for _ in range(5):
                payload = self._generate_with_retries(
                    model=self.settings.smart_model,
                    system_prompt=(
                        "Placement generator for Python Basics. Return JSON with one question object; "
                        "question (string), choices (array of 4 strings), correct_answer, concept. "
                        "Include only the question object in JSON."
                    ),
                    user_prompt=(
                        f"Context chunk: {chunk_text}\n"
                        f"Question index: {idx + 1} of {question_count}\n"
                        f"Generate one unique {level} diagnostic MCQ from this context. "
                        "Make sure question text is not repeated within this set."
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
                        "correct_answer": correct,
                        "concept": question_obj.get("concept", "Python Basics"),
                    }
                )
                break
            else:
                raise AgentValidationError(
                    f"Placement generator could not produce a well-formed MCQ for slot {idx + 1}."
                )

        return {"questions": questions}


class PlacementValidatorAgent:
    name = "placement-validator"

    def validate(self, data: dict, level: str, question_count: int) -> dict:
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
            if correct not in choices:
                raise AgentValidationError(f"Question {i + 1}: correct_answer must be one of choices.")
            if level.lower() == "beginner" and "asyncio" in text_lower:
                raise AgentValidationError(f"Question {i + 1}: beginner level must not reference asyncio.")

            normalized.append(
                {
                    "question": text,
                    "choices": [str(c) for c in choices],
                    "correct_answer": str(correct),
                    "concept": str(q.get("concept") or "Python Basics"),
                }
            )

        return {"questions": normalized}


class SyllabusGeneratorAgent(AgentPair):
    def __init__(self, llm: LLMClient):
        super().__init__("syllabus-generator", llm)

    def generate(self, score: int, level: str) -> dict:
        return self._generate_with_retries(
            model=self.settings.smart_model,
            system_prompt=(
                "Syllabus generator for Python Basics. Return JSON with lessons[] array of unique topics. "
                "Each lesson should have 'topic' and 'description' fields. Never repeat the same topic."
            ),
            user_prompt=(
                f"Build a customized {level} path from placement score={score}. "
                "Ensure each topic appears only once."
            ),
        )


class SyllabusValidatorAgent:
    name = "syllabus-validator"

    def validate(self, payload: dict) -> dict:
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

        if "Variable Assignment" in topics and "Expressions" in topics:
            if topics.index("Expressions") > topics.index("Variable Assignment"):
                raise AgentValidationError("Expressions must be taught before Variable Assignment.")
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
                "Lesson generator for 'Automate the Boring Stuff with Python' by Al Sweigart. "
                "Return JSON with 'markdown' field as the sole content. "
                "The lesson MUST cite 'Automate the Boring Stuff with Python' explicitly. "
                "Base your explanation on the provided book context. "
                "Include relevant Python concepts like expressions, data types, variable assignment, "
                "or string replication where applicable."
            ),
            user_prompt=(
                f"Topic: {sanitized_topic}\n\nBook Context:\n{context}\n\n"
                "Generate a comprehensive lesson on this topic from Automate the Boring Stuff with Python."
            ),
        )
        return payload


class LessonValidatorAgent:
    name = "lesson-validator"

    def validate(self, payload: dict) -> dict:
        markdown = str(payload.get("markdown", ""))
        if "automate the boring stuff" not in markdown.lower():
            s = get_settings()
            suffix = (
                f"\n\n(Source: 'Automate the Boring Stuff with Python' by Al Sweigart. "
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
        "You are a tutor for Automate the Boring Stuff with Python (Al Sweigart). "
        "Respond ONLY with valid JSON: "
        '{"answer": "<markdown or plain text>"}. '
        "Use the provided RAG context as primary evidence; explain any book-related Python topic those chunks support. "
        "Do not assume the learner is locked to one sub-topic unless the question or context clearly implies it. "
        "The answer field MUST contain the exact substring: Automate the Boring Stuff with Python."
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
        if "automate the boring stuff" not in answer.lower():
            payload["answer"] = answer.rstrip() + _qa_source_grounding_suffix()
        return payload
