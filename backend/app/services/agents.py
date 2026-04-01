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


class PlacementAgent(AgentPair):
    def __init__(self, name: str, llm: LLMClient, rag: RAGService):
        super().__init__(name, llm)
        self.rag = rag

    def generate_and_validate(self, level: str, question_count: int) -> dict:
        all_chunks = self.rag.retrieve_python_basics_context(f"python basics {level} concepts", k=20)
        if not all_chunks:
            raise AgentValidationError("No context chunks available for placement generation.")

        selected_chunks = random.sample(all_chunks, min(question_count, len(all_chunks)))

        questions: list[dict] = []
        seen_question_texts = set()

        for idx in range(question_count):
            chunk = selected_chunks[idx % len(selected_chunks)]
            chunk_text = str(chunk).strip()
            for attempt in range(5):
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

                q = payload.get("question") if isinstance(payload.get("question"), dict) else payload
                # Normalize for compatibility with expected bulk schema
                if isinstance(q, dict) and "question" in q and "choices" in q:
                    question_obj = q
                else:
                    question_obj = payload.get("questions", [{}])[0] if isinstance(payload.get("questions"), list) else None

                if not question_obj or not isinstance(question_obj, dict):
                    continue

                text = str(question_obj.get("question", "")).strip()
                if not text:
                    continue
                text_lower = text.lower()
                if text_lower in seen_question_texts:
                    continue

                choices = question_obj.get("choices", [])
                correct = question_obj.get("correct_answer")

                if len(choices) != 4:
                    continue
                if correct not in choices:
                    continue
                if level.lower() == "beginner" and "asyncio" in text_lower:
                    continue

                seen_question_texts.add(text_lower)
                questions.append(
                    {
                        "question": text,
                        "choices": choices,
                        "correct_answer": correct,
                        "concept": question_obj.get("concept", "Python Basics"),
                    }
                )
                break

                raise AgentValidationError(
                    "Placement generator failed to produce unique questions after retries."
                )

        if len(questions) != question_count:
            raise AgentValidationError(f"Placement generator must produce exactly {question_count} questions.")

        return {"questions": questions}



class SyllabusAgent(AgentPair):
    def generate_and_validate(self, score: int, level: str) -> dict:
        payload = self._generate_with_retries(
            model=self.settings.smart_model,
            system_prompt="Syllabus generator for Python Basics. Return JSON with lessons[] array of unique topics. Each lesson should have 'topic' and 'description' fields. Never repeat the same topic.",
            user_prompt=f"Build a customized {level} path from placement score={score}. Ensure each topic appears only once.",
        )
        lessons = payload.get("lessons", [])
        
        # Deduplicate lessons by topic while preserving order
        seen_topics = set()
        unique_lessons = []
        for lesson in lessons:
            topic = lesson.get("topic", "")
            if topic and topic not in seen_topics:
                seen_topics.add(topic)
                unique_lessons.append(lesson)
        
        # Update payload with deduplicated lessons
        payload["lessons"] = unique_lessons
        lessons = unique_lessons
        topics = [lesson.get("topic", "") for lesson in lessons]
        
        if "Variable Assignment" in topics and "Expressions" in topics:
            if topics.index("Expressions") > topics.index("Variable Assignment"):
                raise AgentValidationError("Expressions must be taught before Variable Assignment.")
        
        return payload


class LessonAgent(AgentPair):
    def __init__(self, llm: LLMClient, rag: RAGService):
        super().__init__("lesson", llm)
        self.rag = rag

    def generate_and_validate(self, topic: str) -> dict:
        context = self.rag.retrieve_python_basics_context(topic, k=5)
        sanitized_topic = sanitize_prompt(topic)
        payload = self._generate_with_retries(
            model=self.settings.smart_model,
            system_prompt=(
                "Lesson generator for 'Automate the Boring Stuff with Python' by Al Sweigart. "
                "Return JSON with 'markdown' field as the sole content. "
                "The lesson MUST cite 'Automate the Boring Stuff with Python' explicitly. "
                "Base your explanation on the provided book context. "
                "Include relevant Python concepts like expressions, data types, variable assignment, or string replication where applicable."
            ),
            user_prompt=f"Topic: {sanitized_topic}\n\nBook Context:\n{context}\n\nGenerate a comprehensive lesson on this topic from Automate the Boring Stuff with Python.",
        )
        markdown = payload.get("markdown", "")
        
        # Append source grounding if not already present
        if "automate the boring stuff" not in markdown.lower():
            markdown = self._append_source_grounding(markdown)
            payload["markdown"] = markdown
        
        ok, reason = validate_content_scope(markdown)
        if not ok:
            raise AgentValidationError(reason)
        return payload

    def _append_source_grounding(self, answer: str) -> str:
        resource = self.settings.source_resource
        scope = self.settings.source_scope
        suffix = (
            f"\n\n(Source: 'Automate the Boring Stuff with Python' by Al Sweigart. "
            f"Resource: {resource}; Scope: {scope}. "
            "Covers core Python concepts: expressions, data types, variable assignment, string operations.)"
        )
        return answer.rstrip() + suffix


class QAAgent(AgentPair):
    _QA_SYSTEM = (
        "You are a tutor for Automate the Boring Stuff with Python (Al Sweigart). "
        "Respond ONLY with valid JSON: "
        '{"answer": "<markdown or plain text>"}. '
        "Use the provided RAG context as primary evidence; explain any book-related Python topic those chunks support. "
        "Do not assume the learner is locked to one sub-topic unless the question or context clearly implies it. "
        "The answer field MUST contain the exact substring: Automate the Boring Stuff with Python."
    )

    def __init__(self, llm: LLMClient, rag: RAGService):
        super().__init__("qa", llm)
        self.rag = rag

    def _append_source_grounding(self, answer: str) -> str:
        resource = self.settings.source_resource
        scope = self.settings.source_scope
        suffix = (
            f"\n\n(Source grounding: {resource}; {scope}. "
            "Concepts: expressions, values, data types, string replication.)"
        )
        return answer.rstrip() + suffix

    def generate_and_validate(self, question: str, lesson_markdown: str) -> dict:
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
        answer = str(payload.get("answer", ""))
        if has_python3_hallucinations(answer):
            raise AgentValidationError("Hallucinated Python 2-only functions detected.")
        if "automate the boring stuff" not in answer.lower():
            payload["answer"] = self._append_source_grounding(answer)
        payload["rag"] = {
            "chunks_used": len(context),
            "selected_chunks": [
                {"text": chunk, "source": self.settings.source_resource} for chunk in context
            ],
        }
        return payload
