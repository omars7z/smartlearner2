import re

from app.services.agents.base import AgentPair
from app.services.guardrails import sanitize_prompt
from app.services.llm_client import LLMClient
from app.services.rag_service import RAGService


class QAGeneratorAgent(AgentPair):
    def __init__(self, llm: LLMClient, rag: RAGService):
        super().__init__("qa-generator", llm)
        self.rag = rag

    def _question_style_hint(self, question: str) -> tuple[str, str]:
        q = (question or "").strip().lower()
        if re.search(r"\b(what is|what are|define|meaning of)\b", q):
            return (
                "conceptual",
                "Format: short definition, one simple analogy, then one small example.",
            )
        if re.search(r"\b(how do i|how to|steps?|implement|build)\b", q):
            return (
                "how_to",
                "Format: numbered steps, then code block if useful.",
            )
        if re.search(r"\b(vs|versus|difference between|compare)\b", q):
            return (
                "comparison",
                "Format: compact side-by-side markdown table or bullet comparison.",
            )
        if re.search(r"\b(why does|why is|why do|cause of|root cause)\b", q):
            return (
                "root_cause",
                "Format: root cause, explanation, then prevention tips.",
            )
        if re.search(r"\b(error|exception|traceback|bug|not working|fails?)\b", q):
            return (
                "debugging",
                "Format: diagnosis, fix, and corrected code snippet with explanation.",
            )
        if re.search(r"\b(list|types of|examples of|top \d+)\b", q):
            return (
                "list_request",
                "Format: clean bulleted or numbered list with short descriptions.",
            )
        if re.search(r"\b(summary|summarize|tl;dr|brief)\b", q):
            return (
                "summary",
                "Format: TL;DR first, then concise structured breakdown.",
            )
        return (
            "explanation",
            "Format: medium structured explanation with headings and concise bullets.",
        )

    def generate(
        self,
        question: str,
        lesson_markdown: str,
        track: str = "python",
        student_context: dict | None = None,
    ) -> dict:
        safe_question = sanitize_prompt(question)
        track_key = (track or "python").strip().lower().replace("-", "_")
        if track_key in {"deep_learning", "dl"}:
            source_label = "Deep Learning (Goodfellow, Bengio, Courville; MIT Press)"
            default_course = "Deep Learning Foundations"
            source_ref = "https://www.deeplearningbook.org/"
        else:
            source_label = "Python for Everybody (Charles Severance, University of Michigan; Coursera)"
            default_course = "Python for Everybody"
            source_ref = "https://www.py4e.com/"
        active_course = (
            str(student_context.get("active_course") or "").strip()
            if isinstance(student_context, dict)
            else ""
        ) or default_course
        style_type, style_hint = self._question_style_hint(safe_question)
        is_confused = bool(
            isinstance(student_context, dict)
            and (
                student_context.get("qa_confused") is True
                or re.search(
                    r"\b(i don't get|still confused|مش فاهم|مو فاهم|مش فاهمة|مو فاهمة)\b",
                    safe_question.lower(),
                )
            )
        )
        followup = bool(isinstance(student_context, dict) and student_context.get("qa_followup"))
        mastered = bool(isinstance(student_context, dict) and student_context.get("qa_mastered_last_check"))
        length_hint = (
            "Length rule: simple factual questions max 3-4 lines; explanatory questions medium length; "
            "deep dives can be longer."
        )
        followup_hint = (
            "Follow-up rule: if this is a follow-up, build on prior answer and do not repeat basic definitions."
            if followup
            else "Follow-up rule: start from essentials and then move to practical understanding."
        )
        confusion_hint = (
            "Confusion handling: user seems confused; use a different analogy and include a tiny ASCII diagram."
            if is_confused
            else "Confusion handling: keep explanation clear and direct."
        )
        mastery_hint = (
            "Mastery handling: user answered previous check correctly, so raise complexity slightly."
            if mastered
            else "Mastery handling: keep complexity appropriate to learner level."
        )

        mastery_level = ""
        low_mastery_topics: list[str] = []
        if isinstance(student_context, dict):
            mastery_level = str(student_context.get("mastery_level") or "").strip().lower()
            km = student_context.get("knowledge_map")
            if isinstance(km, dict):
                for k, v in km.items():
                    try:
                        fv = float(v)
                    except (TypeError, ValueError):
                        continue
                    if fv < 0.45:
                        low_mastery_topics.append(str(k))
        low_mastery_topics = low_mastery_topics[:4]
        if mastery_level in {"beginner", "low"} or low_mastery_topics:
            adapt_mode = "supportive_step_by_step"
        elif mastery_level in {"advanced", "very_advanced", "high"}:
            adapt_mode = "concise_technical"
        else:
            adapt_mode = "balanced"

        qa_system = (
            "You are an adaptive AI tutor assistant. "
            f"ACTIVE_COURSE = {active_course}. "
            f"Course reference source = {source_label}. "
            "Respond ONLY with valid JSON. "
            '{"answer": "<markdown or plain text>", "suggestions": ["<optional follow-up 1>", "<optional follow-up 2>"]}. '
            "Use the provided RAG context as primary evidence; explain only topics those chunks support. "
            "Stay strictly within ACTIVE_COURSE and the provided context. "
            "Do not introduce concepts beyond what the context covers. "
            "Output markdown with good structure: use ## headings, bullets/numbered lists, **bold** first-use key terms, "
            "and fenced code blocks with language when code is needed. "
            "Do not use one flat paragraph format for all answers. "
            "If question is outside ACTIVE_COURSE, answer exactly: "
            "\"That's outside your current course scope. Want me to answer it generally, or switch courses first?\" "
            f'The answer field MUST contain the exact substring: {source_label.split(" (")[0]}. '
            "Adapt teaching style using ADAPT_MODE from the user message: "
            "supportive_step_by_step = slower pace, clearer steps, simpler wording, one quick check; "
            "balanced = practical concise explanation with one example; "
            "concise_technical = short direct technical answer. "
            "When helpful, include a tiny runnable code snippet. "
            "Include 1-2 short follow-up suggestions in suggestions[] that stay in track scope. "
            "If the user asks a broad definition, answer clearly and briefly, then relate it to the track context."
        )
        context = self.rag.retrieve_python_basics_context(safe_question, k=4)
        payload = self._generate_with_retries(
            model=self.settings.qa_model,
            system_prompt=qa_system,
            user_prompt=(
                f"Question style detected: {style_type}.\n"
                f"Formatting policy: {style_hint}\n"
                f"{length_hint}\n"
                f"{followup_hint}\n"
                f"{confusion_hint}\n"
                f"{mastery_hint}\n\n"
                f"ACTIVE_COURSE: {active_course}\n"
                f"Track: {track_key}\n"
                f"ADAPT_MODE: {adapt_mode}\n"
                f"Low mastery topics (if any): {', '.join(low_mastery_topics) if low_mastery_topics else 'none'}\n"
                f"Optional app context (may be generic): {lesson_markdown}\n"
                f"Student context: {student_context if isinstance(student_context, dict) else {}}\n"
                f"Question: {safe_question}\n"
                f"RAG context: {context}"
            ),
        )
        if not isinstance(payload.get("suggestions"), list):
            payload["suggestions"] = []
        payload["rag"] = {
            "chunks_used": len(context),
            "selected_chunks": [
                {"text": chunk, "source": source_ref} for chunk in context
            ],
        }
        return payload
