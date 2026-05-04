import difflib

from app.core.placement_rubric import (
    chapter_scope_for_level,
    concepts_for_level,
    normalize_level,
)
from app.services.agents.base import AgentPair, AgentValidationError
from app.services.llm_client import LLMClient
from app.services.rag_service import RAGService

# Edit these strings to experiment with placement quality; one MCQ per LLM call (per rubric slot).
PLACEMENT_MCQ_SYSTEM_PROMPT = (
    "Placement MCQ generator aligned to the selected track's source material. "
    "You will receive a rubric_concept in the user message — generate ONE question for THAT concept ONLY. "
    "Do NOT introduce concepts, syntax, or ideas from other levels or chapters. "
#   "Allowed scope per level: "
#     "beginner = Ch 1-3 and Ch 6 only (variables, expressions, conditionals, strings, basic I/O, errors). "
#     "intermediate = Ch 4-5 and Ch 7-10 (functions, loops, files, lists, dictionaries, tuples). "
#     "advanced = Ch 11-13 (regex, networking, web services, data parsing). "
#     "very_advanced = Ch 14-16 (OOP, databases, visualization). "
#     "Never use self, classes, asyncio, SQL, APIs, or OOP concepts for beginner level. 
    "Allowed scope per level is provided dynamically in the prompt payload for the selected track. "
    "Strictly follow that dynamic scope and the ordered rubric_concepts list. "
    "For beginner level, avoid advanced framework/system-design topics unless explicitly included in scope. "
    "Return JSON only: question (string), choices (array of exactly 4 distinct strings), "
    "correct_answer (must exactly match one of choices), concept (copy rubric_concept verbatim). "
    "Test conceptual understanding, not memorization or trivia. "
    "Across the five slots, each question must use a DISTINCT scenario—vary stories, code snippets, "
    "and distractors; never reuse the same question template or stem pattern."
)

# User message template for .format(): lvl, chunk_text, rubric_concept, slot (1-based), question_count
DEFAULT_PLACEMENT_USER_PROMPT_TEMPLATE = (
    "Placement level: {lvl}. "
    "Allowed chapters for this level: beginner=Ch1-3,Ch6 | intermediate=Ch4,5,7,8,9,10 | advanced=Ch11-13 | very_advanced=Ch14-16.\n"
    "RAG context:\n{chunk_text}\n\n"
    "Rubric objective (you MUST test THIS concept and ONLY this concept): {rubric_concept}\n"
    "Question slot {slot} of {question_count}.\n"
    "Write ONE multiple-choice question that:\n"
    "- Tests ONLY the rubric objective above\n"
    "- Uses vocabulary and difficulty appropriate for {lvl} level\n"
    "- Does NOT introduce concepts from other levels or chapters\n"
    "- Does NOT repeat wording, scenarios, or stems from other slots in this test\n"
    "Return JSON only."
)


def _placement_question_too_similar(candidate: str, prior_texts: list[str], *, max_ratio: float) -> bool:
    """Reject near-duplicate stems when wording differs slightly from an earlier slot."""
    c = " ".join(candidate.lower().split())
    if len(c) < 24:
        return False
    for p in prior_texts:
        p2 = " ".join(p.lower().split())
        if len(p2) < 24:
            continue
        if difflib.SequenceMatcher(None, c, p2).ratio() > max_ratio:
            return True
    return False


def _normalize_choice_list(raw: object) -> list[str] | None:
    """Coerce model output into exactly four non-empty distinct choice strings."""
    if not isinstance(raw, list) or len(raw) != 4:
        return None
    out: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            t = item.get("text") or item.get("choice") or item.get("label") or item.get("value")
            if t is None:
                return None
            out.append(str(t).strip())
        else:
            out.append(str(item).strip())
    if any(not x for x in out):
        return None
    if len({x.casefold() for x in out}) != 4:
        return None
    return out


def _resolve_correct_answer(raw: object, choices: list[str]) -> str | None:
    """Map correct_answer to one of choices (models often return index or near-miss string)."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int) and 0 <= raw < len(choices):
        return choices[raw]
    s = str(raw).strip()
    if s.isdigit():
        idx = int(s)
        if 0 <= idx < len(choices):
            return choices[idx]
    if s in choices:
        return s
    s_cf = s.casefold()
    for c in choices:
        if c.casefold() == s_cf:
            return c
    close = difflib.get_close_matches(s, choices, n=1, cutoff=0.72)
    return close[0] if close else None


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
    """LLM + RAG: MCQs aligned to the selected track placement rubric."""

    def __init__(self, llm: LLMClient, rag: RAGService):
        super().__init__("placement-generator", llm)
        self.rag = rag

    def generate(
        self,
        level: str,
        question_count: int,
        track: str = "python",
        *,
        system_prompt: str | None = None,
        user_prompt_template: str | None = None,
    ) -> dict:
        lvl = normalize_level(level)
        track_key = (track or "python").strip().lower().replace("-", "_")
        forced_concepts = concepts_for_level(lvl, track=track_key)
        if question_count != len(forced_concepts):
            raise AgentValidationError(
                f"Placement expects exactly {len(forced_concepts)} questions per level; got {question_count}."
            )

        sys_prompt = (
            PLACEMENT_MCQ_SYSTEM_PROMPT
            if not (isinstance(system_prompt, str) and system_prompt.strip())
            else system_prompt.strip()
        )
        if track_key in {"deep_learning", "dl"}:
            source_label = "Deep Learning (Goodfellow, Bengio, Courville; MIT Press, https://www.deeplearningbook.org/)"
        else:
            source_label = "Python for Everybody (University of Michigan)"
        sys_prompt = (
            f"Track: {track_key}. Source material: {source_label}. " + sys_prompt
            + f"\n\nTrack: {track_key}."
            + f"\n\nLevel scope: {chapter_scope_for_level(lvl, track=track_key)}."
            + "\n\nAllowed concepts for this level (one per question slot, in order):\n"
            + "\n".join(f"{i + 1}. {c}" for i, c in enumerate(forced_concepts))
        )
        user_tpl = (
            DEFAULT_PLACEMENT_USER_PROMPT_TEMPLATE
            if not (isinstance(user_prompt_template, str) and user_prompt_template.strip())
            else user_prompt_template.strip()
        )

        pool_fallback = self.rag.retrieve_python_basics_context(
            f"{track_key} {lvl} placement diagnostic lecture notes",
            k=24,
        )
        if not pool_fallback:
            pool_fallback = [
                "Python for Everybody (PY4E) foundations: variables, expressions, conditionals, strings, "
                "basic I/O, and reading small programs including errors and tracebacks."
                if track_key not in {"deep_learning", "dl"}
                else "Deep Learning foundations: vectors, matrices, gradients, data splits, linear models, "
                "and evaluating simple predictors."
            ]

        questions: list[dict] = []

        for idx in range(question_count):
            rubric_concept = forced_concepts[idx]
            slot_chunks = self.rag.retrieve_python_basics_context(
                f"{track_key} {lvl} {rubric_concept} lecture notes",
                k=14,
            )
            if not slot_chunks:
                slot_chunks = pool_fallback
            chunk_text = "\n\n---\n\n".join(slot_chunks[:5]).strip()
            user_prompt = user_tpl.format(
                lvl=lvl,
                chunk_text=chunk_text,
                rubric_concept=rubric_concept,
                slot=idx + 1,
                question_count=question_count,
            )
            prior_stems = [str(q.get("question", "")).strip() for q in questions if q.get("question")]
            rejected_similar_in_slot: list[str] = []
            # Later slots get more attempts and a looser similarity cap (models repeat "What prints?" patterns).
            similarity_cap = min(0.82, 0.72 + idx * 0.025)
            max_attempts = 10 if idx >= 2 else 8
            for _ in range(max_attempts):
                payload = self._generate_with_retries(
                    model=self.settings.smart_model,
                    system_prompt=sys_prompt,
                    user_prompt=user_prompt,
                )
                question_obj = _extract_question_obj(payload)
                if not question_obj or not isinstance(question_obj, dict):
                    continue
                text = str(question_obj.get("question", "")).strip()
                norm_choices = _normalize_choice_list(question_obj.get("choices"))
                if not text or not norm_choices:
                    continue
                correct_resolved = _resolve_correct_answer(question_obj.get("correct_answer"), norm_choices)
                if correct_resolved is None:
                    continue
                if _placement_question_too_similar(
                    text,
                    prior_stems + rejected_similar_in_slot,
                    max_ratio=similarity_cap,
                ):
                    rejected_similar_in_slot.append(text)
                    continue
                questions.append(
                    {
                        "question": text,
                        "choices": norm_choices,
                        "correct_answer": correct_resolved,
                        "concept": rubric_concept,
                    }
                )
                break
            else:
                raise AgentValidationError(
                    f"Placement generator could not produce a well-formed MCQ for slot {idx + 1}."
                )

        return {"questions": questions}
