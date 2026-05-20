from app.core.placement_rubric import chapter_scope_for_level, normalize_level
from app.services.agents.base import AgentPair, AgentValidationError
from app.services.agents.syllabus_common import (
    chapter_structure_hint,
    syllabus_allowed_topics_ordered,
    syllabus_rubric_concepts_for_level,
)
from app.services.llm_client import LLMClient
from app.services.rag_service import RAGService


class SyllabusGeneratorAgent(AgentPair):
    """LLM + RAG: generates a personalized syllabus aligned to level and selected-track rubric."""

    name = "syllabus-generator"

    def __init__(self, llm: LLMClient, rag: RAGService):
        super().__init__("syllabus-generator", llm)
        self.rag = rag

    def generate(
        self,
        score: int,
        level: str,
        track: str = "python",
        weak_topics: list[str] | None = None,
        strong_topics: list[str] | None = None,
    ) -> dict:
        lvl = normalize_level(level)
        track_key = (track or "python").strip().lower().replace("-", "_")
        is_dl = track_key in {"deep_learning", "dl"}
        allowed_topics = syllabus_allowed_topics_ordered(lvl, track=track_key)
        rubric_concepts = syllabus_rubric_concepts_for_level(lvl, track=track_key)
        scope = chapter_scope_for_level(lvl, track=track_key)

        rag_query = f"{track_key} lecture notes {lvl} " + " ".join(allowed_topics)
        rag_chunks = self.rag.retrieve_python_basics_context(rag_query, k=12)
        rag_context = "\n\n".join(str(c).strip() for c in rag_chunks) if rag_chunks else ""

        if not rag_context:
            raise AgentValidationError("No RAG context available for syllabus generation.")

        weak = [str(t).strip() for t in (weak_topics or []) if str(t).strip()]
        strong = [str(t).strip() for t in (strong_topics or []) if str(t).strip()]

        personalization_block = ""
        if weak:
            personalization_block += (
                f"\nSTUDENT WEAK CONCEPTS (prioritize and expand coverage for these):\n"
                + "\n".join(f"- {t}" for t in weak)
            )
        if strong:
            personalization_block += (
                f"\nSTUDENT STRONG CONCEPTS (student already knows these — keep coverage brief):\n"
                + "\n".join(f"- {t}" for t in strong)
            )

        allowed_txt = "\n".join(f"- {t}" for t in allowed_topics)
        concepts_txt = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(rubric_concepts))

        return self._generate_with_retries(
            model=self.settings.smart_model,
            system_prompt=(
                f"Syllabus generator for track '{track_key}'. "
                "Generate a personalized syllabus starting ONLY from the student's placement level. "
                "Do NOT include content from lower levels. "
                "Return JSON with top-level key \"units\" (array). Do NOT return flat lessons[] only. "
                "\n\n"
                + (
                    "STRUCTURE — mirror the Deep Learning track chapter structure. "
                    if is_dl
                    else "STRUCTURE — mirror the exact PY4E chapter structure. "
                )
                + ("Each unit = one Deep Learning chapter. " if is_dl else "Each unit = one PY4E chapter. ")
                + "Each unit MUST have: "
                + (
                    "\"chapter\" (int — Deep Learning chapter number e.g. 5); "
                    "\"title\" (string — exact Deep Learning chapter title for this track); "
                    if is_dl
                    else "\"chapter\" (int — PY4E chapter number e.g. 2); "
                    "\"title\" (string — exact PY4E chapter title e.g. 'Variables, Expressions and Statements'); "
                )
                + "\"summary\" (one sentence: what the learner achieves in this chapter); "
                + "\"lessons\" (array of sub-lessons, MINIMUM 4 per chapter). "
                + "\n\n"
                + "Each sub-lesson MUST have: "
                + "\"topic\" — copied EXACTLY from the allowed topic list (no changes, no paraphrasing); "
                + "\"lesson_title\" — specific and engaging, NOT just the topic name "
                + "(e.g. 'Storing and Naming Values' not 'Variables'); "
                # + "Do NOT prefix lesson_title with the word \"Practical\" (no titles like \"Practical X\"). "
                + "\"description\" — 2-3 sentences: concept taught, what learner practices, measurable outcome; "
                + "\"learning_objectives\" — list of 3-5 strings starting with action verbs "
                + "(Identify, Write, Use, Explain, Debug, Apply, Distinguish); "
                + "\"rubric_concept\" — exact match from the rubric_concepts list provided; "
                + (
                    "\"chapter_ref\" (int — the Deep Learning chapter number this sub-lesson belongs to). "
                    if is_dl
                    else "\"chapter_ref\" (int — the PY4E chapter number this sub-lesson belongs to). "
                )
                + "\n\n"
                + "COMPREHENSIVENESS RULES: "
                + "Minimum 4 sub-lessons per chapter — if a chapter has more major concepts, add more. "
                + "Every description must be grounded in the RAG context provided — no generic filler. "
                + "learning_objectives must reflect what a student at THIS level genuinely needs to master. "
                + "Each chapter unit must feel self-contained so a student can finish it and move on confidently. "
                + "\n\n"
                + "ORDER RULES: "
                + "Units must appear in ascending chapter number order. "
                + (
                    "Within Ch 2, sub-lesson for 'Expressions' must come before 'Variable Assignment'. "
                    if not is_dl
                    else ""
                )
                + "\n\n"
                + "STRICT SCOPE: "
                + "Generate ONLY content from the allowed chapters for this level. "
                + "Do NOT introduce any topic, syntax, or concept from other levels or chapters. "
                + "rubric_concept must exactly match one entry from the rubric_concepts list — do not invent."
                + "\n\n"
                + "PERSONALIZATION RULES: "
                + "You will receive STUDENT WEAK CONCEPTS and STUDENT STRONG CONCEPTS in the user message. "
                + "For weak concepts: add more sub-lessons, more detailed descriptions, "
                + "and more learning_objectives focused on that concept. "
                + "For strong concepts: keep coverage concise — one sub-lesson is enough, "
                + "shorter description, fewer objectives. "
                + "Never skip a required topic — just adjust depth. "
            ),
            user_prompt=(
                f"Student placement level: {lvl}.\n"
                f"Track: {track_key}.\n"
                f"STRICT SCOPE: generate syllabus for {lvl} level ONLY — do not include any other level.\n"
                f"Allowed chapters: {scope}.\n\n"
                + chapter_structure_hint(lvl, track=track_key)
                + f"\n\nAllowed topic strings (copy EXACTLY, use every one exactly once across all units):\n{allowed_txt}\n\n"
                f"Rubric concepts in order (map each sub-lesson to its closest matching concept):\n{concepts_txt}\n\n"
                f"RAG context (ground all descriptions and objectives here):\n{rag_context}\n\n"
                f"{personalization_block}\n\n"
                f"Score index: {score}.\n"
                "Return full syllabus JSON now. "
                "Minimum 4 sub-lessons per chapter. "
                "Every sub-lesson must have: topic, lesson_title, description, learning_objectives, rubric_concept, chapter_ref."
            ),
        )
