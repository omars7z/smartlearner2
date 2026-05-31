import difflib
import random
import uuid

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

# User message template for .format(): lvl, chapter_scope, chunk_text, rubric_concept, slot, question_count
DEFAULT_PLACEMENT_USER_PROMPT_TEMPLATE = (
    "Placement level: {lvl}.\n"
    "Allowed scope for this level: {chapter_scope}\n"
    "RAG context:\n{chunk_text}\n\n"
    "Rubric objective (you MUST test THIS concept and ONLY this concept): {rubric_concept}\n"
    "Question slot {slot} of {question_count}.\n"
    "Session variation id: {variation_id} (use this to pick a fresh scenario; do not copy textbook defaults).\n"
    "Scenario direction: {scenario_hint}\n"
    "Write ONE multiple-choice question that:\n"
    "- Tests ONLY the rubric objective above\n"
    "- Uses vocabulary and difficulty appropriate for {lvl} level\n"
    "- Does NOT introduce concepts from other levels or chapters\n"
    "- Does NOT repeat wording, scenarios, or stems from other slots in this test\n"
    "- Avoid overused examples unless you change the angle\n"
    "Return JSON only."
)

# Per-concept scenario nudges so repeated sessions don't always get the same LLM default stem.
_SCENARIO_HINTS_BY_CONCEPT: dict[str, tuple[str, ...]] = {
    "Variables, values, and types": (
        "Ask about type() or isinstance() for a string literal like 'hello'.",
        "Use an integer variable such as age = 21 and ask for its type.",
        "Use a boolean from a comparison, e.g. is_active = 5 > 3.",
        "Use a list literal like items = [1, 2, 3] and ask for the type of items.",
        "Use None assignment x = None and ask what type(x) returns.",
        "Use a variable reassigned from int to str and ask about the final type.",
    ),
    "Expressions and operators": (
        "Use floor division or modulo with integers.",
        "Use string concatenation with + on two str literals.",
        "Use mixed int/float arithmetic and ask which type the result has.",
        "Use parentheses to change order of operations in a numeric expression.",
    ),
    "Conditionals": (
        "Use if/elif/else with numeric thresholds.",
        "Use a nested conditional with string comparison.",
        "Use and/or in a compound boolean condition.",
    ),
}

_DEEP_LEARNING_SCENARIO_HINTS: dict[str, tuple[str, ...]] = {
    "Introduction to machine and deep learning": (
        "Ask what distinguishes deep learning from traditional feature engineering.",
        "Use a scenario about labeled vs unlabeled data.",
        "Ask about when neural networks are preferred over linear models.",
    ),
    "Supervised learning and data splits": (
        "Ask about train/validation/test purpose.",
        "Use a small dataset split ratio question.",
        "Ask why validation data must not leak into training.",
    ),
    "Logistic regression intuition": (
        "Ask about sigmoid output interpretation.",
        "Use binary classification with two features.",
        "Ask what logits represent before sigmoid.",
    ),
    "Gradient descent and learning rate": (
        "Ask how learning rate affects convergence.",
        "Use a loss curve that diverges with lr too high.",
        "Ask about batch vs stochastic gradient descent.",
    ),
    "Loss functions for classification": (
        "Ask when cross-entropy is used.",
        "Compare MSE vs cross-entropy for classification.",
        "Ask what happens if labels are wrong for loss computation.",
    ),
    "Feed-forward network layers": (
        "Ask about input/hidden/output layer roles.",
        "Use a network with stated input and output dimensions.",
        "Ask why depth adds representational capacity.",
    ),
    "Activation functions": (
        "Ask why ReLU is common in hidden layers.",
        "Compare ReLU vs sigmoid for vanishing gradients.",
        "Ask which activation suits binary output.",
    ),
    "Forward propagation and shapes": (
        "Ask matrix multiply shape compatibility.",
        "Use a 2-layer MLP with given dimensions.",
        "Ask what happens if weight matrix shapes mismatch.",
    ),
    "Backpropagation intuition": (
        "Ask what chain rule role is in backprop.",
        "Ask which parameters get updated after backward pass.",
        "Use a simple computational graph scenario.",
    ),
    "Training an MLP": (
        "Ask about epochs, batches, and loss monitoring.",
        "Ask when to stop training early.",
        "Use overfitting on small data as scenario.",
    ),
    "Convolutional neural networks": (
        "Ask why conv layers suit image data.",
        "Ask about local receptive fields vs fully connected.",
        "Use a small feature map example.",
    ),
    "Convolution pooling and feature maps": (
        "Ask what pooling reduces (spatial size / parameters).",
        "Ask stride vs padding effect on output size.",
        "Use max pooling on a 2x2 window.",
    ),
    "RNN and sequence modeling": (
        "Ask why RNNs handle variable-length sequences.",
        "Ask about hidden state carrying past context.",
        "Use a simple next-token prediction scenario.",
    ),
    "LSTM and GRU gates": (
        "Ask what forget/input/output gates control.",
        "Compare LSTM vs vanilla RNN on long sequences.",
        "Ask why gating helps vanishing gradients.",
    ),
    "Sequence task applications": (
        "Ask which tasks are sequence-to-sequence.",
        "Use machine translation or time-series example.",
        "Ask about encoder-decoder structure.",
    ),
    "Classification evaluation metrics": (
        "Ask when accuracy is misleading.",
        "Use imbalanced classes scenario.",
        "Ask about true/false positive definitions.",
    ),
    "Precision recall and F1": (
        "Ask trade-off when precision vs recall matters.",
        "Compute F1 from given precision/recall.",
        "Use medical diagnosis cost scenario.",
    ),
    "Confusion matrix interpretation": (
        "Ask to read TP/FP/FN/TN from a matrix.",
        "Ask which cell is false negative.",
        "Use a 2x2 confusion matrix with numbers.",
    ),
    "Regression metrics (MSE MAE)": (
        "Ask when MAE is more robust than MSE.",
        "Compare sensitivity to outliers.",
        "Use predicted vs actual numeric example.",
    ),
    "Choosing metrics for a task": (
        "Ask which metric fits fraud detection.",
        "Ask metric choice for multi-class vs binary.",
        "Use business cost of false negatives scenario.",
    ),
}


def _scenario_hint_for(concept: str, attempt: int, *, track: str = "python") -> str:
    track_key = (track or "python").strip().lower().replace("-", "_")
    hints = (
        _DEEP_LEARNING_SCENARIO_HINTS.get(concept)
        if track_key in {"deep_learning", "dl"}
        else _SCENARIO_HINTS_BY_CONCEPT.get(concept)
    )
    if not hints:
        return (
            f"Pick scenario variant #{attempt + 1}: use a different variable name, "
            "context, and code snippet than typical textbook examples."
        )
    return hints[(attempt + random.randint(0, len(hints) - 1)) % len(hints)]


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
            from app.core.deep_learning_curriculum import DL_SOURCE_RESOURCE

            source_label = DL_SOURCE_RESOURCE
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
            track=track_key,
        )
        if not pool_fallback:
            pool_fallback = [
                "AI342 Deep Learning: introduction, logistic regression, gradient descent, "
                "feed-forward networks, CNNs, sequence models, and evaluation metrics."
                if track_key in {"deep_learning", "dl"}
                else "Python for Everybody (PY4E) foundations: variables, expressions, conditionals, strings, "
                "basic I/O, and reading small programs including errors and tracebacks."
            ]

        chapter_scope = chapter_scope_for_level(lvl, track=track_key)
        questions: list[dict] = []
        session_variation_id = uuid.uuid4().hex[:10]

        for idx in range(question_count):
            rubric_concept = forced_concepts[idx]
            slot_chunks = self.rag.retrieve_python_basics_context(
                f"{track_key} {lvl} {rubric_concept} lecture notes",
                k=14,
                track=track_key,
            )
            if not slot_chunks:
                slot_chunks = pool_fallback
            picked_chunks = (
                random.sample(slot_chunks, k=min(5, len(slot_chunks)))
                if len(slot_chunks) > 1
                else slot_chunks[:5]
            )
            chunk_text = "\n\n---\n\n".join(picked_chunks).strip()
            prior_stems = [str(q.get("question", "")).strip() for q in questions if q.get("question")]
            rejected_similar_in_slot: list[str] = []
            # Later slots get more attempts and a looser similarity cap (models repeat "What prints?" patterns).
            similarity_cap = min(0.82, 0.72 + idx * 0.025)
            max_attempts = 10 if idx >= 2 else 8
            for attempt in range(max_attempts):
                user_prompt = user_tpl.format(
                    lvl=lvl,
                    chapter_scope=chapter_scope,
                    chunk_text=chunk_text,
                    rubric_concept=rubric_concept,
                    slot=idx + 1,
                    question_count=question_count,
                    variation_id=f"{session_variation_id}-s{idx + 1}-a{attempt + 1}",
                    scenario_hint=_scenario_hint_for(rubric_concept, attempt, track=track_key),
                )
                if rejected_similar_in_slot:
                    user_prompt += (
                        "\n\nPreviously rejected stems (do NOT repeat or paraphrase closely):\n"
                        + "\n".join(f"- {s}" for s in rejected_similar_in_slot[-4:])
                    )
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
