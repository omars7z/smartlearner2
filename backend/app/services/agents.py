import difflib
import json
import random

from app.core.config import get_settings
from app.core.placement_rubric import (
    PLACEMENT_CONCEPTS_BY_LEVEL,
    SYLLABUS_RUBRIC_CONCEPTS_BY_LEVEL,
    SYLLABUS_TOPIC_ALLOWLIST_BY_LEVEL,
    SYLLABUS_TOPIC_ORDER_BY_LEVEL,
    chapter_scope_for_level,
    concepts_for_level,
    forbidden_terms_for_level,
    normalize_level,
)
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


def _placement_question_too_similar(candidate: str, prior_texts: list[str]) -> bool:
    """Reject near-duplicate stems when wording differs slightly from an earlier slot."""
    c = " ".join(candidate.lower().split())
    if len(c) < 24:
        return False
    for p in prior_texts:
        p2 = " ".join(p.lower().split())
        if len(p2) < 24:
            continue
        if difflib.SequenceMatcher(None, c, p2).ratio() > 0.74:
            return True
    return False


def _extract_question_obj(payload: dict) -> dict | None:
    q = payload.get("question") if isinstance(payload.get("question"), dict) else payload
    if isinstance(q, dict) and "question" in q and "choices" in q:
        return q
    if isinstance(payload.get("questions"), list) and payload["questions"]:
        first = payload["questions"][0]
        if isinstance(first, dict):
            return first
    return None


def _syllabus_allowed_topics_ordered(level: str) -> list[str]:
    """Topics in syllabus order (PY4E-aligned), not alphabetical."""
    lvl = normalize_level(level)
    allow = SYLLABUS_TOPIC_ALLOWLIST_BY_LEVEL.get(lvl, frozenset())
    order = SYLLABUS_TOPIC_ORDER_BY_LEVEL.get(lvl)
    if order:
        out: list[str] = [t for t in order if t in allow]
        for t in allow:
            if t not in out:
                out.append(t)
        return out
    return sorted(allow)


def _syllabus_rubric_concepts_for_level(level: str) -> list[str]:
    lvl = normalize_level(level)
    return list(SYLLABUS_RUBRIC_CONCEPTS_BY_LEVEL.get(lvl, PLACEMENT_CONCEPTS_BY_LEVEL.get(lvl, ())))


# Edit these strings to experiment with placement quality; one MCQ per LLM call (per rubric slot).
PLACEMENT_MCQ_SYSTEM_PROMPT = (
    "Placement MCQ generator for Python for Everybody (University of Michigan). "
    "You will receive a rubric_concept in the user message — generate ONE question for THAT concept ONLY. "
    "Do NOT introduce concepts, syntax, or ideas from other levels or chapters. "
    "Allowed scope per level: "
    "beginner = Ch 1-3 and Ch 6 only (variables, expressions, conditionals, strings, basic I/O, errors). "
    "intermediate = Ch 4-5 and Ch 7-10 (functions, loops, files, lists, dictionaries, tuples). "
    "advanced = Ch 11-13 (regex, networking, web services, data parsing). "
    "very_advanced = Ch 14-16 (OOP, databases, visualization). "
    "Never use self, classes, asyncio, SQL, APIs, or OOP concepts for beginner level. "
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


class PlacementGeneratorAgent(AgentPair):
    """LLM + RAG: MCQs aligned to the placement rubric (Python for Everybody scope)."""

    def __init__(self, llm: LLMClient, rag: RAGService):
        super().__init__("placement-generator", llm)
        self.rag = rag

    def generate(
        self,
        level: str,
        question_count: int,
        *,
        system_prompt: str | None = None,
        user_prompt_template: str | None = None,
    ) -> dict:
        lvl = normalize_level(level)
        forced_concepts = concepts_for_level(lvl)
        if question_count != len(forced_concepts):
            raise AgentValidationError(
                f"Placement expects exactly {len(forced_concepts)} questions per level; got {question_count}."
            )

        sys_prompt = (
            PLACEMENT_MCQ_SYSTEM_PROMPT
            if not (isinstance(system_prompt, str) and system_prompt.strip())
            else system_prompt.strip()
        )
        sys_prompt = (
            sys_prompt
            + f"\n\nLevel scope: {chapter_scope_for_level(lvl)}."
            + "\n\nAllowed concepts for this level (one per question slot, in order):\n"
            + "\n".join(f"{i + 1}. {c}" for i, c in enumerate(forced_concepts))
        )
        user_tpl = (
            DEFAULT_PLACEMENT_USER_PROMPT_TEMPLATE
            if not (isinstance(user_prompt_template, str) and user_prompt_template.strip())
            else user_prompt_template.strip()
        )

        pool_fallback = self.rag.retrieve_python_basics_context(
            f"python for everybody {lvl} placement diagnostic",
            k=24,
        )
        if not pool_fallback:
            raise AgentValidationError("No context chunks available for placement generation.")

        questions: list[dict] = []

        for idx in range(question_count):
            rubric_concept = forced_concepts[idx]
            slot_chunks = self.rag.retrieve_python_basics_context(
                f"python for everybody {lvl} py4e {rubric_concept}",
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
            for _ in range(5):
                payload = self._generate_with_retries(
                    model=self.settings.smart_model,
                    system_prompt=sys_prompt,
                    user_prompt=user_prompt,
                )
                question_obj = _extract_question_obj(payload)
                if not question_obj or not isinstance(question_obj, dict):
                    continue
                text = str(question_obj.get("question", "")).strip()
                choices = question_obj.get("choices", [])
                correct = question_obj.get("correct_answer")
                if not text or not isinstance(choices, list) or len(choices) != 4 or correct is None:
                    continue
                if _placement_question_too_similar(text, prior_stems + rejected_similar_in_slot):
                    rejected_similar_in_slot.append(text)
                    continue
                questions.append(
                    {
                        "question": text,
                        "choices": list(choices),
                        "correct_answer": str(correct),
                        "concept": rubric_concept,
                    }
                )
                break
            else:
                raise AgentValidationError(
                    f"Placement generator could not produce a well-formed MCQ for slot {idx + 1}."
                )

        return {"questions": questions}


def _validate_placement_deterministic(data: dict, level: str, question_count: int) -> dict:
    """Rule-based validation and normalization (authoritative rubric enforcement)."""
    from app.core.placement_rubric import concepts_for_level, validate_question_concepts_for_level

    lvl = normalize_level(level)
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
        norm_choices = [str(c).strip() for c in choices]
        correct_str = str(correct).strip()
        if correct_str not in norm_choices:
            raise AgentValidationError(f"Question {i + 1}: correct_answer must be one of choices.")

        forbidden = forbidden_terms_for_level(lvl)
        for term in forbidden:
            if term in text_lower:
                raise AgentValidationError(
                    f"Question {i + 1}: level {lvl!r} must not reference '{term}'. "
                    f"Allowed scope: {chapter_scope_for_level(lvl)}."
                )

        normalized.append(
            {
                "question": text,
                "choices": norm_choices,
                "correct_answer": correct_str,
                "concept": str(q.get("concept") or "").strip(),
            }
        )

    expected = list(concepts_for_level(lvl))
    for i, row in enumerate(normalized):
        if row["concept"] != expected[i]:
            raise AgentValidationError(
                f"Question {i + 1}: concept must match rubric slot {expected[i]!r}; got {row['concept']!r}."
            )

    try:
        validate_question_concepts_for_level(normalized, lvl)
    except ValueError as exc:
        raise AgentValidationError(str(exc)) from exc

    return {"questions": normalized}


_PLACEMENT_VALIDATOR_SYSTEM = """You are PlacementValidatorAgent. Validate placement MCQs for Python for Everybody.
You receive JSON with:
- placement_level (string)
- expected_question_count (int)
- rubric_concepts_in_order (array of exact concept strings, one per slot)
- candidate_questions (array)

Check: each question has non-empty stem, exactly 4 distinct choices (strings), correct_answer must equal one choice after trim,
no duplicate stems (case-insensitive), for beginner level stems must not mention asyncio,
and for each index i concept must EXACTLY equal rubric_concepts_in_order[i].
Return JSON only:
{"valid": true, "questions": [ ... normalized objects with question, choices, correct_answer, concept ... ]}
or {"valid": false, "error": "brief reason"}.
If valid, echo normalized questions with correct_answer and choices as trimmed strings."""


class PlacementValidatorAgent(AgentPair):
    """LLM-assisted validation (validator API key) with deterministic rubric enforcement as fallback."""

    name = "placement-validator"

    def __init__(self, llm: LLMClient):
        super().__init__("placement-validator", llm)

    def validate(self, data: dict, level: str, question_count: int) -> dict:
        lvl = normalize_level(level)
        expected = list(concepts_for_level(lvl))
        payload = {
            "placement_level": lvl,
            "expected_question_count": question_count,
            "rubric_concepts_in_order": expected,
            "candidate_questions": data.get("questions") or [],
        }
        user_prompt = json.dumps(payload, ensure_ascii=False)
        try:
            out = self._generate_with_retries(
                model=self.settings.fast_model,
                system_prompt=_PLACEMENT_VALIDATOR_SYSTEM,
                user_prompt=user_prompt,
            )
            if not isinstance(out, dict) or not out.get("valid"):
                raise AgentValidationError(str(out.get("error") or "PlacementValidatorAgent rejected input"))
            merged = {"questions": out.get("questions") or []}
            return _validate_placement_deterministic(merged, level, question_count)
        except AgentValidationError:
            return _validate_placement_deterministic(data, level, question_count)


def _flatten_syllabus_payload(payload: dict) -> list[dict]:
    """
    Normalize syllabus JSON: either legacy flat `lessons[]` or hierarchical `units[]`
    with nested `lessons` (sub-lessons). Each row: topic, title, description, unit_title.
    """
    units = payload.get("units")
    if isinstance(units, list) and units:
        out: list[dict] = []
        for u in units:
            if not isinstance(u, dict):
                continue
            ut = str(u.get("title") or u.get("unit_title") or "").strip() or "Unit"
            summary = str(u.get("summary") or u.get("description") or "").strip()
            for sl in u.get("lessons") or []:
                if not isinstance(sl, dict):
                    continue
                topic = str(sl.get("topic") or "").strip()
                if not topic:
                    continue
                title = str(sl.get("lesson_title") or sl.get("title") or topic).strip()
                desc = str(sl.get("description") or "").strip()
                lo = sl.get("learning_objectives")
                row = {
                    "topic": topic,
                    "title": title,
                    "description": desc,
                    "unit_title": ut,
                    "learning_objectives": lo if isinstance(lo, list) else [],
                    "rubric_concept": str(sl.get("rubric_concept") or "").strip(),
                }
                lit = str(sl.get("lesson_title") or sl.get("title") or "").strip()
                if lit:
                    row["lesson_title"] = lit
                cref = sl.get("chapter_ref")
                if cref is not None:
                    try:
                        row["chapter_ref"] = int(cref)
                    except (TypeError, ValueError):
                        row["chapter_ref"] = cref
                if summary and not desc:
                    row["description"] = summary
                out.append(row)
        return out

    legacy = payload.get("lessons") or []
    rows: list[dict] = []
    for lesson in legacy:
        if not isinstance(lesson, dict):
            continue
        topic = str(lesson.get("topic") or "").strip()
        if not topic:
            continue
        lo = lesson.get("learning_objectives")
        lr = {
            "topic": topic,
            "title": str(lesson.get("lesson_title") or lesson.get("title") or topic).strip(),
            "description": str(lesson.get("description") or "").strip(),
            "unit_title": str(lesson.get("unit_title") or "").strip() or None,
            "learning_objectives": lo if isinstance(lo, list) else [],
            "rubric_concept": str(lesson.get("rubric_concept") or "").strip(),
        }
        cref = lesson.get("chapter_ref")
        if cref is not None:
            try:
                lr["chapter_ref"] = int(cref)
            except (TypeError, ValueError):
                lr["chapter_ref"] = cref
        rows.append(lr)
    return rows


def _chapter_structure_hint(level: str) -> str:
    """PY4E chapter breakdown injected into the syllabus generation prompt."""
    hints = {
        "beginner": (
            "Ch 1 – Why we program: What is programming, Hardware architecture, "
            "Python as a language, Writing your first program\n"
            "Ch 2 – Variables, expressions, statements: Values and types, "
            "Variables and assignment, Expressions and operators, "
            "Statements and order of execution, User input\n"
            "Ch 3 – Conditional execution: Boolean expressions, Logical operators, "
            "if/elif/else, Nested conditionals, try/except basics\n"
            "Ch 6 – Strings: String operations, String slicing, "
            "String methods, Searching in strings, String formatting"
        ),
        "intermediate": (
            "Ch 4 – Functions: Defining functions, Parameters and arguments, "
            "Return values, Local vs global scope, Fruitful functions\n"
            "Ch 5 – Iteration: while loop, for loop, "
            "Loop patterns (counting/summing/min/max), break and continue, "
            "Infinite loops and guards\n"
            "Ch 7 – Files: Opening and reading files, Writing to files, "
            "File paths, Looping over file lines, try/except with files\n"
            "Ch 8 – Lists: List operations, List methods, List slicing, "
            "Lists and loops, List algorithms\n"
            "Ch 9 – Dictionaries: Dictionary basics, Looping over dictionaries, "
            "Dictionary patterns (counting/grouping), get() and default values\n"
            "Ch 10 – Tuples: Tuple basics, Tuples vs lists, "
            "Sorting with tuples, DSU pattern, Tuples in loops"
        ),
        "advanced": (
            "Ch 11 – Regular Expressions: re module basics, search() and findall(), "
            "Character classes and quantifiers, Greedy vs non-greedy, "
            "Practical regex patterns\n"
            "Ch 12 – Networked Programs: HTTP basics, urllib and urlopen, "
            "Parsing HTML, Web scraping patterns, Error handling in networking\n"
            "Ch 13 – Web Services: JSON basics, Parsing JSON, "
            "REST APIs and requests, XML basics, Service-Oriented Architecture\n"
            "Ch 14 – OOP: Classes and objects, __init__ and self, "
            "Methods, Inheritance, OOP design patterns"
        ),
        "very_advanced": (
            "Ch 15 – Databases & SQL: SQLite basics, CREATE/INSERT/SELECT, "
            "Filtering and sorting, Joins and relationships, "
            "Python + SQLite integration\n"
            "Ch 16 – Visualizing Data: Data visualization concepts, "
            "OpenStreetMap data, Network graphs, "
            "Mail data analysis, End-to-end data pipeline"
        ),
    }
    return hints.get(normalize_level(level), hints["beginner"])


class SyllabusGeneratorAgent(AgentPair):
    """LLM + RAG: generates a personalized syllabus aligned to placement level and PY4E rubric."""

    name = "syllabus-generator"

    def __init__(self, llm: LLMClient, rag: RAGService):
        super().__init__("syllabus-generator", llm)
        self.rag = rag

    def generate(
        self,
        score: int,
        level: str,
        weak_topics: list[str] | None = None,
        strong_topics: list[str] | None = None,
    ) -> dict:
        lvl = normalize_level(level)
        allowed_topics = _syllabus_allowed_topics_ordered(lvl)
        rubric_concepts = _syllabus_rubric_concepts_for_level(lvl)
        scope = chapter_scope_for_level(lvl)

        rag_query = f"python for everybody {lvl} " + " ".join(allowed_topics)
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
                "Syllabus generator for Python for Everybody (University of Michigan). "
                "Generate a personalized syllabus starting ONLY from the student's placement level. "
                "Do NOT include content from lower levels. "
                "Return JSON with top-level key \"units\" (array). Do NOT return flat lessons[] only. "
                "\n\n"
                "STRUCTURE — mirror the exact PY4E chapter structure: "
                "Each unit = one PY4E chapter. "
                "Each unit MUST have: "
                "\"chapter\" (int — PY4E chapter number e.g. 2); "
                "\"title\" (string — exact PY4E chapter title e.g. 'Variables, Expressions and Statements'); "
                "\"summary\" (one sentence: what the learner achieves in this chapter); "
                "\"lessons\" (array of sub-lessons, MINIMUM 4 per chapter). "
                "\n\n"
                "Each sub-lesson MUST have: "
                "\"topic\" — copied EXACTLY from the allowed topic list (no changes, no paraphrasing); "
                "\"lesson_title\" — specific and engaging, NOT just the topic name "
                "(e.g. 'Storing and Naming Values' not 'Variables'); "
                "\"description\" — 2-3 sentences: concept taught, what learner practices, measurable outcome; "
                "\"learning_objectives\" — list of 3-5 strings starting with action verbs "
                "(Identify, Write, Use, Explain, Debug, Apply, Distinguish); "
                "\"rubric_concept\" — exact match from the rubric_concepts list provided; "
                "\"chapter_ref\" (int — the PY4E chapter number this sub-lesson belongs to). "
                "\n\n"
                "COMPREHENSIVENESS RULES: "
                "Minimum 4 sub-lessons per chapter — if a chapter has more major concepts, add more. "
                "Every description must be grounded in the RAG context provided — no generic filler. "
                "learning_objectives must reflect what a student at THIS level genuinely needs to master. "
                "Each chapter unit must feel self-contained so a student can finish it and move on confidently. "
                "\n\n"
                "ORDER RULES: "
                "Units must appear in ascending chapter number order. "
                "Within Ch 2, sub-lesson for 'Expressions' must come before 'Variable Assignment'. "
                "\n\n"
                "STRICT SCOPE: "
                "Generate ONLY content from the allowed chapters for this level. "
                "Do NOT introduce any topic, syntax, or concept from other levels or chapters. "
                "rubric_concept must exactly match one entry from the rubric_concepts list — do not invent."
                "\n\n"
                "PERSONALIZATION RULES: "
                "You will receive STUDENT WEAK CONCEPTS and STUDENT STRONG CONCEPTS in the user message. "
                "For weak concepts: add more sub-lessons, more detailed descriptions, "
                "and more learning_objectives focused on that concept. "
                "For strong concepts: keep coverage concise — one sub-lesson is enough, "
                "shorter description, fewer objectives. "
                "Never skip a required topic — just adjust depth. "
            ),
            user_prompt=(
                f"Student placement level: {lvl}.\n"
                f"STRICT SCOPE: generate syllabus for {lvl} level ONLY — do not include any other level.\n"
                f"Allowed chapters: {scope}.\n\n"
                f"PY4E chapter structure for {lvl} (use as backbone — one unit per chapter):\n"
                + _chapter_structure_hint(lvl)
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


_SYLLABUS_VALIDATOR_SYSTEM = """You are SyllabusValidatorAgent for Python for Everybody.
You receive JSON with:
- placement_level (string)
- chapter_scope (string)
- allowed_chapters (object: chapter number → chapter title)
- allowed_topics (array of exact allowed topic strings for this level)
- rubric_concepts (array of exact rubric concept strings for this level)
- candidate_units (the generated units array)

Validate every unit and sub-lesson:
1. topic must be copied EXACTLY from allowed_topics — no paraphrasing
2. lesson_title must NOT equal topic — must be more descriptive
3. description must be at least 2 sentences specific to the topic
4. learning_objectives must be a list of at least 3 actionable strings (verb-first)
5. rubric_concept must exactly match one entry from rubric_concepts
6. Every topic in allowed_topics appears exactly once — no omissions, no duplicates
7. No topics from other levels appear
8. chapter_ref must belong to allowed_chapters keys
9. Units must be in ascending chapter number order
10. Within Ch 2: sub-lesson with topic related to 'Expressions' appears before 'Variable Assignment'
11. Each chapter unit must have at least 4 sub-lessons

Return JSON only:
{"valid": true, "units": [ ...normalized units array unchanged... ]}
or {"valid": false, "error": "which lesson/unit failed and which rule number"}.
If valid, echo the full units array unchanged."""


def _validate_syllabus_deterministic(payload: dict, placement_level: str | None) -> dict:
    """Deterministic fallback — mirrors _validate_placement_deterministic pattern."""
    from app.core.placement_rubric import validate_syllabus_topics_for_level

    flat = _flatten_syllabus_payload(payload)
    if not flat:
        raise AgentValidationError(
            "Syllabus must contain units with lessons, or a non-empty lessons array."
        )

    seen_topics: set[str] = set()
    unique_lessons: list[dict] = []
    for lesson in flat:
        topic = lesson.get("topic", "")
        if topic and topic not in seen_topics:
            seen_topics.add(topic)
            unique_lessons.append(lesson)

    if placement_level:
        try:
            validate_syllabus_topics_for_level(unique_lessons, placement_level)
        except ValueError as exc:
            raise AgentValidationError(str(exc)) from exc

    if placement_level:
        lvl = normalize_level(placement_level)
        allowed_concepts = set(
            SYLLABUS_RUBRIC_CONCEPTS_BY_LEVEL.get(lvl, PLACEMENT_CONCEPTS_BY_LEVEL.get(lvl, ()))
        )
        for i, lesson in enumerate(unique_lessons):
            rc = str(lesson.get("rubric_concept") or "").strip()
            if rc and rc not in allowed_concepts:
                raise AgentValidationError(
                    f"Lesson {i + 1} ({lesson.get('topic')}): "
                    f"rubric_concept {rc!r} is not valid for level {lvl!r}."
                )

        ALLOWED_CHAPTER_NUMBERS = {
            "beginner": {1, 2, 3, 6},
            "intermediate": {4, 5, 7, 8, 9, 10},
            "advanced": {11, 12, 13, 14},
            "very_advanced": {15, 16},
        }
        lvl_ch = normalize_level(placement_level)
        allowed_ch = ALLOWED_CHAPTER_NUMBERS.get(lvl_ch, set())
        for i, lesson in enumerate(unique_lessons):
            ch_ref = lesson.get("chapter_ref")
            if ch_ref is not None:
                try:
                    if int(ch_ref) not in allowed_ch:
                        raise AgentValidationError(
                            f"Lesson {i + 1} ({lesson.get('topic')}): "
                            f"chapter_ref {ch_ref} is outside allowed chapters "
                            f"for level {lvl_ch!r}: {sorted(allowed_ch)}"
                        )
                except (TypeError, ValueError):
                    pass

    for i, lesson in enumerate(unique_lessons):
        desc = str(lesson.get("description") or "").strip()
        if len(desc) < 30:
            raise AgentValidationError(
                f"Lesson {i + 1} ({lesson.get('topic')}): description too short or missing."
            )
        objectives = lesson.get("learning_objectives")
        if not isinstance(objectives, list) or len(objectives) < 3:
            raise AgentValidationError(
                f"Lesson {i + 1} ({lesson.get('topic')}): "
                "learning_objectives must be a list of at least 3 items."
            )
        title = str(lesson.get("lesson_title") or lesson.get("title") or "").strip()
        topic = str(lesson.get("topic") or "").strip()
        if title.lower() == topic.lower():
            raise AgentValidationError(
                f"Lesson {i + 1}: lesson_title must differ from topic name."
            )

    topics = [lesson.get("topic", "") for lesson in unique_lessons]
    if "Variable Assignment" in topics and "Expressions" in topics:
        i_exp = next(i for i, l in enumerate(unique_lessons) if l.get("topic") == "Expressions")
        i_var = next(i for i, l in enumerate(unique_lessons) if l.get("topic") == "Variable Assignment")
        if i_exp > i_var:
            exp_lesson = unique_lessons.pop(i_exp)
            i_var = next(i for i, l in enumerate(unique_lessons) if l.get("topic") == "Variable Assignment")
            unique_lessons.insert(i_var, exp_lesson)

    topics = [lesson.get("topic", "") for lesson in unique_lessons]
    if len(set(topics)) != len(topics):
        raise AgentValidationError("Syllabus contains duplicate topics.")

    return {"lessons": unique_lessons, "units": payload.get("units")}


class SyllabusValidatorAgent(AgentPair):
    """LLM-assisted syllabus validation with deterministic fallback."""

    name = "syllabus-validator"

    def __init__(self, llm: LLMClient):
        super().__init__("syllabus-validator", llm)

    def validate(self, payload: dict, placement_level: str | None = None) -> dict:
        lvl = normalize_level(placement_level) if placement_level else "beginner"
        allowed_topics = _syllabus_allowed_topics_ordered(lvl)
        rubric_concepts = _syllabus_rubric_concepts_for_level(lvl)

        ALLOWED_CHAPTERS = {
            "beginner": {
                1: "Why we program",
                2: "Variables, Expressions and Statements",
                3: "Conditional execution",
                6: "Strings",
            },
            "intermediate": {
                4: "Functions",
                5: "Iteration",
                7: "Files",
                8: "Lists",
                9: "Dictionaries",
                10: "Tuples",
            },
            "advanced": {
                11: "Regular Expressions",
                12: "Networked Programs",
                13: "Web Services",
                14: "Object-Oriented Programming",
            },
            "very_advanced": {
                15: "Databases and SQL",
                16: "Visualizing Data",
            },
        }

        validation_input = {
            "placement_level": lvl,
            "chapter_scope": chapter_scope_for_level(lvl),
            "allowed_chapters": ALLOWED_CHAPTERS.get(lvl, {}),
            "allowed_topics": allowed_topics,
            "rubric_concepts": rubric_concepts,
            "candidate_units": payload.get("units") or [],
        }

        try:
            out = self._generate_with_retries(
                model=self.settings.fast_model,
                system_prompt=_SYLLABUS_VALIDATOR_SYSTEM,
                user_prompt=json.dumps(validation_input, ensure_ascii=False),
            )
            if not isinstance(out, dict) or not out.get("valid"):
                raise AgentValidationError(
                    str(out.get("error") or "SyllabusValidatorAgent rejected the syllabus")
                )
            merged = {"units": out.get("units") or [], "lessons": payload.get("lessons")}
            return _validate_syllabus_deterministic(merged, placement_level)
        except AgentValidationError:
            return _validate_syllabus_deterministic(payload, placement_level)


class LessonGeneratorAgent(AgentPair):
    def __init__(self, llm: LLMClient, rag: RAGService):
        super().__init__("lesson-generator", llm)
        self.rag = rag

    def generate(
        self,
        topic: str,
        lesson_title: str | None = None,
        *,
        level: str = "beginner",
        chapter_ref: int | None = None,
    ) -> dict:
        context = self.rag.retrieve_python_basics_context(topic, k=8)
        sanitized_topic = sanitize_prompt(topic)
        display_title = sanitize_prompt(lesson_title) if lesson_title else sanitized_topic
        scope_bits: list[str] = [
            f"Lesson display title: {display_title}",
            f"Rubric / search topic (slug): {sanitized_topic}",
            f"Target learner level: {level}",
        ]
        if chapter_ref is not None:
            scope_bits.append(f"Py4E chapter reference (for grounding): chapter {chapter_ref}")
        user_head = "\n".join(scope_bits)
        payload = self._generate_with_retries(
            model=self.settings.smart_model,
            system_prompt=(
                "Lesson generator for Python for Everybody (Charles Severance, University of Michigan), "
                "Coursera specialization scope. "
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
                "The prose MUST cite 'Python for Everybody' at least once. "
                "Ground explanations in the provided course-text context when relevant."
            ),
            user_prompt=(
                f"{user_head}\n\n"
                f"Course text context (RAG):\n{context}\n\n"
                "Generate the full markdown lesson. Do not leave headings empty."
            ),
        )
        return payload


class LessonValidatorAgent:
    name = "lesson-validator"

    def validate(self, payload: dict) -> dict:
        markdown = str(payload.get("markdown", ""))
        if "python for everybody" not in markdown.lower():
            s = get_settings()
            suffix = (
                f"\n\n(Source: Python for Everybody (Charles Severance, University of Michigan). "
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
        "You are a tutor for Python for Everybody (Charles Severance, University of Michigan; Coursera). "
        "Respond ONLY with valid JSON: "
        '{"answer": "<markdown or plain text>"}. '
        "Use the provided RAG context as primary evidence; explain Python topics those chunks support. "
        "Stay within the scope of the provided RAG context and lesson topic. Do not introduce concepts beyond what the context covers. "
        "The answer field MUST contain the exact substring: Python for Everybody."
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
        if "python for everybody" not in answer.lower():
            payload["answer"] = answer.rstrip() + _qa_source_grounding_suffix()
        return payload
