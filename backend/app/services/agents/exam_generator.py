from __future__ import annotations

import random

from app.core.placement_rubric import normalize_level, normalize_track
from app.services.agents.base import AgentPair
from app.services.llm_client import LLMClient, LLMClientError
from app.services.rag_service import RAGService

EXAM_AGENT_SYSTEM_PROMPT = (
    "You are ExamAgent for an adaptive learning platform. "
    "Generate high-quality multiple-choice exam questions grounded in the provided lesson context and RAG evidence. "
    "Return strict JSON only with key `questions` (array). "
    "Each question object MUST include:\n"
    "- question (string, non-empty stem)\n"
    "- choices (array of exactly 4 distinct, non-empty strings)\n"
    "- correct_answer (string that exactly equals one item in choices)\n"
    "- concept (string, the skill being tested)\n"
    "- difficulty (one of: easy, medium, hard)\n"
    "- explanation (string, 1-2 sentences explaining why the correct answer is right)\n\n"
    "Pedagogical rules:\n"
    "- Test understanding and application, not trivia or trick wording.\n"
    "- Align difficulty with the requested level and difficulty mix.\n"
    "- Prefer scenarios, code snippets, or short problems when appropriate for the track.\n"
    "- Each stem must be unique; do not repeat templates or near-duplicate wording.\n"
    "- Distractors must be plausible misconceptions, not joke answers.\n"
    "- Stay within lesson scope and track source material.\n"
    "- If weak_topics are provided, include at least one question targeting a weak topic when relevant.\n"
    "- If strong_topics are provided, avoid over-testing only strong areas.\n"
    "- If previous exam stems are listed, every new stem must be materially different.\n"
)

EXAM_USER_PROMPT_TEMPLATE = (
    "Track: {track}\n"
    "Lesson title: {lesson_title}\n"
    "Topic slug: {topic}\n"
    "Exam level: {level}\n"
    "Question count: {question_count}\n"
    "Difficulty mix target: {difficulty_mix}\n"
    "Weak topics (prioritize remediation when relevant): {weak_topics}\n"
    "Strong topics (do not over-focus here): {strong_topics}\n"
    "Variation seed: {seed}\n"
    "Attempt number: {attempt_number}\n"
    "Previous exam stems to AVOID repeating or closely paraphrasing:\n{previous_stems}\n\n"
    "Lesson context (primary):\n{lesson_markdown}\n\n"
    "RAG evidence (secondary, cite concepts supported by chunks):\n{rag_context}\n\n"
    "Generate exactly {question_count} MCQ questions as JSON under key `questions`."
)


def _difficulty_mix_for_level(level: str) -> str:
    lvl = normalize_level(level.replace(" ", "_").lower())
    if lvl in {"advanced", "very_advanced"}:
        return "30% easy, 40% medium, 30% hard"
    if lvl == "intermediate":
        return "40% easy, 40% medium, 20% hard"
    return "55% easy, 35% medium, 10% hard"


class ExamGeneratorAgent(AgentPair):
    """LLM + RAG adaptive exam question generator."""

    def __init__(self, llm: LLMClient, rag: RAGService):
        super().__init__("exam-generator", llm)
        self.rag = rag

    def _fallback_questions(
        self,
        *,
        topic: str,
        level: str,
        lesson_title: str,
        question_count: int,
        attempt_number: int = 1,
        previous_stems: list[str] | None = None,
    ) -> dict:
        topic_text = (topic or lesson_title or "core concepts").replace("_", " ")
        templates = [
            "Which statement best describes {concept} in this lesson?",
            "What is the most accurate application of {concept}?",
            "Which option correctly explains {concept}?",
            "In a practical exercise, how should {concept} be used?",
            "Which misconception about {concept} is most important to avoid?",
            "How does {concept} connect to the lesson's main learning goal?",
            "Which example best demonstrates {concept}?",
            "When solving a problem involving {concept}, what is the best first step?",
        ]
        concepts = [
            topic_text,
            lesson_title.strip() or topic_text,
            f"{topic_text} basics",
            "lesson practice",
            f"{topic_text} in context",
            "core lesson idea",
        ]
        prev = {s.strip().lower() for s in (previous_stems or []) if str(s).strip()}
        rng = random.Random((attempt_number * 10007) + question_count + len(topic_text))
        start_tpl = (attempt_number - 1) % len(templates)
        ordered_templates = templates[start_tpl:] + templates[:start_tpl]
        questions: list[dict] = []
        tries = 0
        i = 0
        while len(questions) < question_count and tries < question_count * 4:
            tries += 1
            concept = concepts[(i + attempt_number + tries) % len(concepts)]
            stem = ordered_templates[i % len(ordered_templates)].format(concept=concept)
            i += 1
            if stem.lower() in prev:
                continue
            correct = f"It applies {concept} correctly as taught in this lesson."
            wrongs = [
                f"It ignores the role of {concept} in solving problems.",
                f"It confuses {concept} with an unrelated advanced topic.",
                f"It describes {concept} in a way that contradicts the lesson.",
            ]
            choices = wrongs + [correct]
            rng.shuffle(choices)
            diff = "easy" if len(questions) < max(1, question_count // 2) else "medium"
            questions.append(
                {
                    "question": stem,
                    "choices": choices,
                    "correct_answer": correct,
                    "concept": concept,
                    "difficulty": diff,
                    "explanation": f"The correct option reflects how {concept} is used in this lesson.",
                }
            )
        while len(questions) < question_count:
            n = len(questions) + 1
            concept = topic_text
            stem = f"Review question {n} (attempt {attempt_number}): what is key about {concept}?"
            correct = f"It summarizes {concept} accurately for this lesson."
            wrongs = [
                f"It misstates {concept}.",
                f"It applies {concept} to the wrong context.",
                f"It contradicts the lesson on {concept}.",
            ]
            choices = wrongs + [correct]
            rng.shuffle(choices)
            questions.append(
                {
                    "question": stem,
                    "choices": choices,
                    "correct_answer": correct,
                    "concept": concept,
                    "difficulty": "medium",
                    "explanation": f"The correct option matches the lesson's treatment of {concept}.",
                }
            )
        return {"questions": questions}

    def generate(
        self,
        *,
        lesson_title: str,
        topic: str,
        track: str,
        level: str,
        question_count: int,
        lesson_markdown: str,
        weak_topics: list[str] | None = None,
        strong_topics: list[str] | None = None,
        previous_stems: list[str] | None = None,
        attempt_number: int = 1,
    ) -> dict:
        track_key = normalize_track(track)
        lvl = normalize_level(level.replace(" ", "_").lower())
        weak = [str(x).strip() for x in (weak_topics or []) if str(x).strip()][:6]
        strong = [str(x).strip() for x in (strong_topics or []) if str(x).strip()][:6]
        prev = [str(x).strip() for x in (previous_stems or []) if str(x).strip()][:20]
        seed = random.randint(1000, 99999)
        rag_query = f"{lesson_title} {topic} {lvl} exam assessment attempt {attempt_number}"
        rag_context = self.rag.retrieve_python_basics_context(rag_query, k=5)
        user_prompt = EXAM_USER_PROMPT_TEMPLATE.format(
            track=track_key,
            lesson_title=lesson_title,
            topic=topic,
            level=lvl,
            question_count=question_count,
            difficulty_mix=_difficulty_mix_for_level(lvl),
            weak_topics=", ".join(weak) if weak else "none",
            strong_topics=", ".join(strong) if strong else "none",
            seed=seed,
            attempt_number=attempt_number,
            previous_stems="\n".join(f"- {s}" for s in prev) if prev else "(none)",
            lesson_markdown=(lesson_markdown or "")[:6000],
            rag_context="\n---\n".join(rag_context[:5]) if rag_context else "(no RAG chunks)",
        )
        try:
            data = self._generate_with_retries(
                model=self.settings.smart_model,
                system_prompt=EXAM_AGENT_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            if isinstance(data, dict) and isinstance(data.get("questions"), list) and prev:
                overlap = sum(
                    1
                    for q in data["questions"]
                    if isinstance(q, dict)
                    and str(q.get("question") or "").strip().lower() in {p.lower() for p in prev}
                )
                if overlap >= max(1, question_count // 2):
                    raise ValueError("LLM repeated too many prior exam stems.")
            return data
        except LLMClientError:
            return self._fallback_questions(
                topic=topic,
                level=lvl,
                lesson_title=lesson_title,
                question_count=question_count,
                attempt_number=attempt_number,
                previous_stems=prev,
            )
        except Exception:
            return self._fallback_questions(
                topic=topic,
                level=lvl,
                lesson_title=lesson_title,
                question_count=question_count,
                attempt_number=attempt_number,
                previous_stems=prev,
            )
