from app.services.agents.base import AgentPair
from app.services.guardrails import sanitize_prompt
from app.services.llm_client import LLMClient
from app.services.rag_service import RAGService


class QAGeneratorAgent(AgentPair):
    def __init__(self, llm: LLMClient, rag: RAGService):
        super().__init__("qa-generator", llm)
        self.rag = rag

    def generate(self, question: str, lesson_markdown: str, track: str = "python") -> dict:
        safe_question = sanitize_prompt(question)
        track_key = (track or "python").strip().lower().replace("-", "_")
        if track_key in {"deep_learning", "dl"}:
            source_label = "Deep Learning (Goodfellow, Bengio, Courville; MIT Press)"
        else:
            source_label = "Python for Everybody (Charles Severance, University of Michigan; Coursera)"
        qa_system = (
            f"You are a tutor for {source_label}. "
            "Respond ONLY with valid JSON: "
            '{"answer": "<markdown or plain text>"}. '
            "Use the provided RAG context as primary evidence; explain only topics those chunks support. "
            "Stay within the scope of the provided RAG context and lesson topic. "
            "Do not introduce concepts beyond what the context covers. "
            f'The answer field MUST contain the exact substring: {source_label.split(" (")[0]}.'
        )
        context = self.rag.retrieve_python_basics_context(safe_question, k=4)
        payload = self._generate_with_retries(
            model=self.settings.smart_model,
            system_prompt=qa_system,
            user_prompt=(
                f"Track: {track_key}\n"
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
