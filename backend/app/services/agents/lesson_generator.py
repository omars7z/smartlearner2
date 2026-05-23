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
        track_key = (track or "python").strip().lower().replace("-", "_")
        is_dl = track_key in {"deep_learning", "dl"}
        scope_bits: list[str] = [
            f"Track: {track_key}",
            f"Lesson display title: {display_title}",
            f"Rubric / search topic (slug): {sanitized_topic}",
            f"Target learner level: {level}",
        ]
        if chapter_ref is not None:
            if is_dl:
                scope_bits.append(f"Deep Learning chapter reference (for grounding): chapter {chapter_ref}")
            else:
                scope_bits.append(f"Py4E chapter reference (for grounding): chapter {chapter_ref}")
        if adaptation_instructions:
            scope_bits.append(f"Adaptation instructions: {adaptation_instructions}")
        user_head = "\n".join(scope_bits)
        payload = self._generate_with_retries(
            model=self.settings.smart_model,
            system_prompt=(
                (
                    "Lesson generator for Deep Learning (Ian Goodfellow, Yoshua Bengio, Aaron Courville; MIT Press). "
                    if is_dl
                    else "Lesson generator for Python for Everybody (Charles Severance, University of Michigan). "
                )
                + "Return JSON with a single key \"markdown\" (string). "
                "Write a substantive lesson (aim for roughly 600–1200 words unless the model limit requires shorter). "
                "Use GitHub-flavored Markdown only: "
                "## and ### headings, **bold** key terms, bullet lists, numbered steps where useful, "
                "and at least two fenced ```python``` code blocks with runnable examples and brief comments. "
                "Structure the markdown in this order: "
                "## Learning objectives (3–5 bullets); "
                f"## Core ideas (clear explanations tied to {'deep learning lecture notes' if is_dl else 'PY4E'}); "
                "## Worked examples (code + explanation); "
                "## Common pitfalls (short bullets); "
                "## Practice (2–3 exercises described in text); "
                "## Summary (bullets). "
                "For python track, cite 'Python for Everybody' at least once. "
                "For deep_learning track, cite 'Deep Learning' at least once and ground examples in lecture-note style practice. "
                "For deep_learning track, NEVER mention 'Python for Everybody', 'PY4E', or Py4E chapter references. "
                "Ground explanations in the provided course-text context when relevant."
            ),
            user_prompt=(
                f"{user_head}\n\n"
                f"Course text context (RAG):\n{context}\n\n"
                + "Generate the full markdown lesson. Do not leave headings empty."
            ),
        )
        # make markdown everytimr you generate a lesson to compress tokens 
        if is_dl and isinstance(payload, dict):
            md = str(payload.get("markdown") or "")
            if md:
                # Defensive cleanup in case the model leaks legacy cross-track references.
                payload["markdown"] = (
                    md.replace("Python for Everybody", "Deep Learning")
                    .replace("PY4E", "Deep Learning")
                    .replace("py4e.com", "deeplearningbook.org")
                )
        return payload

    def generate_sub_lesson(
        self,
        *,
        parent_topic: str,
        sub_title: str,
        source_excerpt: str,
        failure_context: str | None = None,
        continuity_instructions: str | None = None,
        sequence_part: tuple[int, int] | None = None,
        track: str = "python",
        level: str = "beginner",
        chapter_ref: int | None = None,
    ) -> dict:
        """
        Remediation slice after a failed assessment: slower pace, more examples, no terse summary.
        """
        rag_query = (parent_topic or "python").strip()
        if sequence_part:
            part_i, part_n = sequence_part
            rag_query = f"{rag_query} {sanitize_prompt(sub_title)} part {part_i} of {part_n}"
        context = self.rag.retrieve_python_basics_context(rag_query, k=6)
        sanitized_topic = sanitize_prompt(parent_topic)
        display_title = sanitize_prompt(sub_title)
        track_key = (track or "python").strip().lower().replace("-", "_")
        is_dl = track_key in {"deep_learning", "dl"}
        intro_line = (
            "The learner is working through a split lesson; this installment must cover only the slice implied by the title and excerpt."
            if sequence_part
            else "The student failed to understand this topic. Generate a more detailed, beginner-friendly explanation."
        )
        scope_bits: list[str] = [
            f"Track: {track_key}",
            f"Sub-lesson title: {display_title}",
            f"Original topic (slug): {sanitized_topic}",
            f"Target learner level: {level}",
            intro_line,
            "Do NOT summarize the topic in bullet-only form; expand with intuition, definitions, and reasoning.",
            "Include at least two concrete examples and one short step-by-step walkthrough.",
            "Add practical context (when/why this matters) and common misconceptions.",
            "Prioritize clarity over breadth; stay within this sub-lesson slice.",
            (
                f"Ground in this excerpt (this part's slice of the original lesson):\n{sanitize_prompt(source_excerpt[:12000])}"
                if sequence_part
                else f"Ground in this excerpt from their prior lesson attempt:\n{sanitize_prompt(source_excerpt[:12000])}"
            ),
        ]
        if sequence_part:
            pi, pn = sequence_part
            scope_bits.insert(
                0,
                "MULTI-PART SEQUENCE: You are writing ONE installment of a longer topic. "
                f"This is part {pi} of {pn} (the topic is split into at most 3 parts). "
                "Each part must use different examples, different analogies, and different section headings than the other parts. "
                "Do not restate the full topic overview from scratch as if part 1; build forward. "
                "Keep content compressed: cover only what belongs in this slice—no padding or repeated summaries. "
                "If this is not part 1, open with one short bridging paragraph that references that the learner already covered earlier steps.",
            )
        if continuity_instructions:
            scope_bits.append(
                "Continuity and scope constraints for this installment:\n"
                + sanitize_prompt(continuity_instructions[:6000])
            )
        if failure_context:
            scope_bits.append(
                "Personalize remediation using this assessment failure context. "
                "Explicitly target the misconceptions shown here, then provide one corrected mini-example per misconception:\n"
                + sanitize_prompt(failure_context[:6000])
            )
        if chapter_ref is not None:
            scope_bits.append(
                f"Deep Learning chapter reference (for grounding): chapter {chapter_ref}"
                if is_dl
                else f"Py4E chapter reference (for grounding): chapter {chapter_ref}"
            )
        user_head = "\n".join(scope_bits)
        seq_extra = ""
        if sequence_part:
            seq_extra = (
                " When this is one of several parts, never copy-paste identical paragraphs across parts: "
                "each part must advance the learner with new material."
            )
        payload = self._generate_with_retries(
            model=self.settings.smart_model,
            system_prompt=(
                (
                    "You write remedial sub-lessons for Deep Learning (Ian Goodfellow, Yoshua Bengio, Aaron Courville; MIT Press). "
                    if is_dl
                    else "You write remedial sub-lessons for Python for Everybody (Charles Severance, University of Michigan). "
                )
                + "Return JSON with a single key \"markdown\" (string). "
                "Use GitHub-flavored Markdown: ## and ### headings, **bold** terms, numbered steps, fenced ```python``` blocks. "
                "Avoid a short recap section; instead end with a brief 'Check your understanding' (2 questions in prose, no quiz UI). "
                + (
                    "Aim for roughly 400–650 words of teaching content (dense, no filler)."
                    if sequence_part
                    else "Aim for roughly 500–900 words of teaching content."
                )
                + seq_extra
            ),
            user_prompt=(
                f"{user_head}\n\n"
                f"Course text context (RAG):\n{context}\n\n"
                "Generate the full markdown for this sub-lesson only."
            ),
        )
        if is_dl and isinstance(payload, dict):
            md = str(payload.get("markdown") or "")
            if md:
                payload["markdown"] = (
                    md.replace("Python for Everybody", "Deep Learning")
                    .replace("PY4E", "Deep Learning")
                    .replace("py4e.com", "deeplearningbook.org")
                )
        return payload
