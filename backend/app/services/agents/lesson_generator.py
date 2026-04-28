from app.services.agents.base import AgentPair
from app.services.guardrails import sanitize_prompt
from app.services.llm_client import LLMClient
from app.services.rag_service import RAGService


class LessonGeneratorAgent(AgentPair):
    def __init__(self, llm: LLMClient, rag: RAGService):
        super().__init__("lesson-generator", llm)
        self.rag = rag

    def generate(
        self,
        topic: str,
        lesson_title: str | None = None,
        *,
        track: str = "python",
        level: str = "beginner",
        chapter_ref: int | None = None,
        adaptation_instructions: str | None = None,
    ) -> dict:
        context = self.rag.retrieve_python_basics_context(topic, k=8)
        sanitized_topic = sanitize_prompt(topic)
        display_title = sanitize_prompt(lesson_title) if lesson_title else sanitized_topic
        scope_bits: list[str] = [
            f"Track: {track}",
            f"Lesson display title: {display_title}",
            f"Rubric / search topic (slug): {sanitized_topic}",
            f"Target learner level: {level}",
        ]
        if chapter_ref is not None:
            scope_bits.append(f"Py4E chapter reference (for grounding): chapter {chapter_ref}")
        if adaptation_instructions:
            scope_bits.append(f"Adaptation instructions: {adaptation_instructions}")
        user_head = "\n".join(scope_bits)
        payload = self._generate_with_retries(
            model=self.settings.smart_model,
            system_prompt=(
                "Lesson generator for Python for Everybody (Charles Severance, University of Michigan), "
                # "Coursera specialization scope. "
                "Return JSON with a single key \"markdown\" (string). "
                "Write a substantive lesson (aim for roughly 600–1200 words unless the model limit requires shorter). "
                "Use GitHub-flavored Markdown only: "
                "## and ### headings, **bold** key terms, bullet lists, numbered steps where useful, "
                "and at least two fenced ```python``` code blocks with runnable examples and brief comments. "
                "Structure the markdown in this order: "
                "## Learning objectives (3–5 bullets); "
                "## Core ideas (clear explanations tied to PY4E); "
                "## Worked examples (code + explanation); "
                "## Common pitfalls (short bullets); "
                "## Practice (2–3 exercises described in text); "
                "## Summary (bullets). "
                "For python track, cite 'Python for Everybody' at least once. "
                "For deep_learning track, ground examples in lecture-note style deep learning practice. "
                "Ground explanations in the provided course-text context when relevant."
            ),
            user_prompt=(
                f"{user_head}\n\n"
                f"Course text context (RAG):\n{context}\n\n"
                "Generate the full markdown lesson. Do not leave headings empty."
            ),
        )
        return payload
