import json

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
        context = self.rag.retrieve_python_basics_context(f"python basics {level} concepts", k=5)
        payload = self._generate_with_retries(
            model=self.settings.smart_model,
            system_prompt=(
                "Placement generator for Python Basics. Return JSON with questions list; "
                "each question has question, choices (exactly 4 options), correct_answer, concept. "
                "Create questions based on the provided context from the resource."
            ),
            user_prompt=f"Context: {context}\nCreate {question_count} {level} diagnostic questions with 4 multiple choice options each.",
        )
        questions = payload.get("questions", [])
        if len(questions) != question_count:
            raise AgentValidationError(f"Placement generator must produce exactly {question_count} questions.")

        for q in questions:
            choices = q.get("choices", [])
            if len(choices) != 4:
                raise AgentValidationError("Each question must have exactly 4 choices.")
            if q.get("correct_answer") not in choices:
                raise AgentValidationError("Question must include exactly one valid correct answer.")
            if level.lower() == "beginner" and "asyncio" in q.get("question", "").lower():
                raise AgentValidationError("Beginner placement includes advanced topic.")
        return payload


class SyllabusAgent(AgentPair):
    def generate_and_validate(self, score: int) -> dict:
        payload = self._generate_with_retries(
            model=self.settings.smart_model,
            system_prompt="Syllabus generator for Python Basics. Return JSON with lessons[].",
            user_prompt=f"Build a customized beginner path from placement score={score}.",
        )
        lessons = payload.get("lessons", [])
        topics = [lesson.get("topic", "") for lesson in lessons]
        if "Variable Assignment" in topics and "Expressions" in topics:
            if topics.index("Expressions") > topics.index("Variable Assignment"):
                raise AgentValidationError("Expressions must be taught before Variable Assignment.")
        if len(set(topics)) != len(topics):
            raise AgentValidationError("Syllabus contains circular/duplicate dependencies.")
        return payload


class LessonAgent(AgentPair):
    def __init__(self, llm: LLMClient, rag: RAGService):
        super().__init__("lesson", llm)
        self.rag = rag

    def generate_and_validate(self, topic: str) -> dict:
        context = self.rag.retrieve_python_basics_context(topic, k=3)
        sanitized_topic = sanitize_prompt(topic)
        payload = self._generate_with_retries(
            model=self.settings.smart_model,
            system_prompt=(
                "Lesson generator. Return JSON with markdown only. "
                "Lesson must cite Automate the Boring Stuff with Python and Python Basics concepts."
            ),
            user_prompt=f"Topic={sanitized_topic}\nContext={context}",
        )
        markdown = payload.get("markdown", "")
        ok, reason = validate_content_scope(markdown)
        if not ok:
            raise AgentValidationError(reason)
        return payload


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
