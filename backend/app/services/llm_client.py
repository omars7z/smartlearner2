import json
import logging
import random
import re
import time
from importlib import import_module

from app.core.config import get_settings

logger = logging.getLogger(__name__)
from app.core.groq_rate_limits import update_from_headers

_LOGGED_GROQ_UNAVAILABLE_PRIMARY = False
_LOGGED_GROQ_UNAVAILABLE_VALIDATOR = False
_LOGGED_GEMINI_UNAVAILABLE = False

# Tried in order on 429/503/etc. Gemini 1.5 IDs return 404 (retired); use 2.x/3.x per Google AI docs.
_GEMINI_REST_MODEL_FALLBACKS = (
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-flash-latest",
)
# Retry once with backoff, then try the next model.
_GEMINI_TRANSIENT_HTTP = frozenset({429, 502, 503, 504})

def _load_optional_module(name: str):
    try:
        return import_module(name)
    except Exception:  # pragma: no cover
        return None


groq_mod = _load_optional_module("groq")
genai = _load_optional_module("google.generativeai")
requests = _load_optional_module("requests")


class LLMClientError(RuntimeError):
    """Raised when placement (and other agent-only paths) need Groq but it is unavailable."""


def _is_placement_mcq_generator(system_prompt: str) -> bool:
    """PlacementGeneratorAgent — must use live LLM, not static fallbacks."""
    s = system_prompt.lower()
    return "placement" in s and "validator" not in s


def _is_lesson_or_syllabus_generation(system_prompt: str) -> bool:
    s = system_prompt.lower().strip()
    # Keep this strict so QA prompts that mention "lesson topic" are NOT misclassified.
    return (
        s.startswith("lesson generator for ")
        or s.startswith("you write remedial sub-lessons for ")
        or s.startswith("syllabus generator for track ")
    )


def _prompt_route(system_prompt: str) -> str:
    s = system_prompt.lower()
    if _is_placement_mcq_generator(system_prompt):
        return "placement"
    if s.strip().startswith("syllabus generator for track "):
        return "syllabus"
    if s.strip().startswith("lesson generator for ") or s.strip().startswith("you write remedial sub-lessons for "):
        return "lesson"
    if "validator" in s:
        return "validator"
    if "q&a" in s or "qa" in s or "tutor" in s:
        return "qa"
    return "generic"


class LLMClient:
    """Groq client. Use ``use_validator_key=True`` for validator-only agents (separate API key)."""

    def __init__(self, *, use_validator_key: bool = False) -> None:
        global _LOGGED_GROQ_UNAVAILABLE_PRIMARY, _LOGGED_GROQ_UNAVAILABLE_VALIDATOR, _LOGGED_GEMINI_UNAVAILABLE
        self.settings = get_settings()
        self.use_validator_key = use_validator_key
        self.gemini_api_key = (getattr(self.settings, "gemini_api_key", None) or "").strip()
        self.client = None
        if groq_mod:
            key: str | None
            if use_validator_key:
                key = self.settings.groq_api_key_validators or self.settings.groq_api_key
            else:
                key = self.settings.groq_api_key
            if key:
                self.client = groq_mod.Groq(api_key=key)

        self.gemini_client = None
        if genai:
            if self.gemini_api_key:
                try:
                    genai.configure(api_key=self.gemini_api_key)
                    self.gemini_client = genai.GenerativeModel(
                        model_name="gemini-2.0-flash",
                        generation_config={"response_mime_type": "application/json"},
                    )
                except Exception as exc:
                    logger.warning("LLM: Gemini init failed: %s", exc)
                    self.gemini_client = None
        if self.client is None:
            if use_validator_key and not _LOGGED_GROQ_UNAVAILABLE_VALIDATOR:
                logger.warning("LLM: Groq validator client is not configured (key missing or SDK unavailable).")
                _LOGGED_GROQ_UNAVAILABLE_VALIDATOR = True
            elif not use_validator_key and not _LOGGED_GROQ_UNAVAILABLE_PRIMARY:
                logger.warning("LLM: Groq primary client is not configured (key missing or SDK unavailable).")
                _LOGGED_GROQ_UNAVAILABLE_PRIMARY = True
        if not self._gemini_fallback_available() and not _LOGGED_GEMINI_UNAVAILABLE:
            logger.warning("LLM: Gemini fallback is not configured/available.")
            _LOGGED_GEMINI_UNAVAILABLE = True

    def _gemini_rest_available(self) -> bool:
        return bool(self.gemini_api_key) and requests is not None

    def _gemini_fallback_available(self) -> bool:
        return self.gemini_client is not None or self._gemini_rest_available()

    @staticmethod
    def _text_from_gemini_rest_json(data: dict) -> str:
        cands = data.get("candidates") or []
        if not isinstance(cands, list) or not cands:
            raise LLMClientError("Gemini REST returned no candidates.")
        parts = (((cands[0] or {}).get("content") or {}).get("parts")) or []
        if not isinstance(parts, list):
            raise LLMClientError("Gemini REST returned malformed content.")
        text = ""
        for p in parts:
            if isinstance(p, dict) and isinstance(p.get("text"), str):
                text += p["text"]
        text = text.strip()
        if not text:
            raise LLMClientError("Gemini REST returned empty text.")
        return text

    def _generate_with_gemini_rest(self, system_prompt: str, user_prompt: str) -> str:
        if not self.gemini_api_key:
            raise LLMClientError("Gemini API key missing — set GEMINI_API_KEY in .env.")
        if requests is None:
            raise LLMClientError("requests package unavailable for Gemini REST fallback.")
        # Header auth: never put API key in URL (avoids leaking keys in HTTP error strings).
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.gemini_api_key}
        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}],
                }
            ],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        base = "https://generativelanguage.googleapis.com/v1beta/models/"
        last_status: int | None = None
        for model_id in _GEMINI_REST_MODEL_FALLBACKS:
            url = f"{base}{model_id}:generateContent"
            for attempt in range(2):
                if attempt:
                    time.sleep(2.0 + random.random())
                try:
                    resp = requests.post(url, json=body, headers=headers, timeout=(15, 90))
                    last_status = resp.status_code
                    if resp.status_code == 404:
                        logger.warning(
                            "LLM: Gemini REST model %s not available (HTTP 404); trying next.",
                            model_id,
                        )
                        break
                    if resp.status_code in _GEMINI_TRANSIENT_HTTP:
                        logger.warning(
                            "LLM: Gemini REST model %s returned HTTP %s (transient), attempt %s/%s.",
                            model_id,
                            resp.status_code,
                            attempt + 1,
                            2,
                        )
                        if attempt == 0:
                            continue
                        break
                    if resp.status_code != 200:
                        resp.raise_for_status()
                    data = resp.json()
                    text = self._text_from_gemini_rest_json(data)
                    if model_id != _GEMINI_REST_MODEL_FALLBACKS[0]:
                        logger.warning("LLM: Gemini REST succeeded using fallback model %s.", model_id)
                    return text
                except requests.RequestException as exc:
                    r = getattr(exc, "response", None)
                    status = getattr(r, "status_code", None) if r is not None else None
                    last_status = status or last_status
                    if status in _GEMINI_TRANSIENT_HTTP and attempt == 0:
                        continue
                    if status is None:
                        raise LLMClientError("Gemini REST request failed (network or timeout).") from exc
                    if status in _GEMINI_TRANSIENT_HTTP:
                        break
                    raise LLMClientError(f"Gemini REST failed with HTTP {status}.") from exc
                except ValueError as exc:
                    raise LLMClientError(f"Gemini REST invalid JSON response: {exc}") from exc
        if last_status in _GEMINI_TRANSIENT_HTTP:
            raise LLMClientError(
                "Gemini REST: all fallback models exhausted after retries "
                "(HTTP 429/502/503/504). Retry later or check Google AI Studio / billing / status."
            )
        raise LLMClientError("Gemini REST failed for all fallback models.")

    def _generate_with_gemini(self, system_prompt: str, user_prompt: str) -> str:
        """Fallback to Gemini when Groq is unavailable or rate-limited."""
        if self.gemini_client is None and not self._gemini_rest_available():
            raise LLMClientError(
                "Gemini client not configured — set GEMINI_API_KEY (and install `requests` for REST fallback)."
            )
        try:
            logger.warning("LLM: attempting Gemini fallback (route=%s).", _prompt_route(system_prompt))
            if self.gemini_client is not None:
                combined = f"{system_prompt}\n\n{user_prompt}"
                response = self.gemini_client.generate_content(combined)
                text = response.text or "{}"
            else:
                text = self._generate_with_gemini_rest(system_prompt, user_prompt)
            logger.warning("LLM: Gemini fallback succeeded (route=%s).", _prompt_route(system_prompt))
            return text
        except Exception as exc:
            if isinstance(exc, LLMClientError):
                raise exc
            raise LLMClientError(f"Gemini fallback also failed: {type(exc).__name__}") from exc

    def _generate_with_groq_relaxed_json(self, model: str, system_prompt: str, user_prompt: str) -> str:
        """
        Retry path when Groq strict JSON validation rejects an otherwise useful answer.
        Leaves schema enforcement to our own JSON parser/retry logic upstream.
        """
        if self.client is None:
            raise LLMClientError("Groq client unavailable for relaxed retry.")
        completion = self.client.chat.completions.create(
            model=model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return completion.choices[0].message.content or "{}"

    def generate_json(self, model: str, system_prompt: str, user_prompt: str) -> str:
        if self.client is None:
            route = _prompt_route(system_prompt)
            logger.warning("LLM: Groq unavailable; trying Gemini fallback (route=%s).", route)
            if self._gemini_fallback_available():
                try:
                    return self._generate_with_gemini(system_prompt, user_prompt)
                except LLMClientError as gemini_exc:
                    logger.error(
                        "LLM: Gemini fallback failed while Groq unavailable (route=%s): %s",
                        route,
                        gemini_exc,
                    )
            else:
                logger.error("LLM: Gemini fallback unavailable (route=%s).", route)
            if _is_lesson_or_syllabus_generation(system_prompt):
                raise LLMClientError(
                    "Groq unavailable and Gemini fallback failed/unavailable for lesson/syllabus generation. "
                    "Set GROQ_API_KEY and GEMINI_API_KEY."
                )
            if _is_placement_mcq_generator(system_prompt):
                logger.warning(
                    "Groq client unavailable for placement and Gemini fallback failed/unavailable; "
                    "using local mock fallback."
                )
            return self._mock_json(system_prompt, user_prompt)
        try:
            chat = self.client.chat.completions
            if hasattr(chat, "with_raw_response"):
                raw = chat.with_raw_response.create(
                    model=model,
                    temperature=0.3,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                try:
                    update_from_headers(getattr(raw, "headers", None))
                except Exception:
                    pass
                completion = raw.parse()
            else:
                completion = chat.create(
                    model=model,
                    temperature=0.2,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
            return completion.choices[0].message.content or "{}"
        except LLMClientError:
            raise
        except Exception as exc:
            is_rate_limit = "429" in str(exc) or "rate_limit" in str(exc).lower() or "quota" in str(exc).lower()
            is_json_validate_failed = "json_validate_failed" in str(exc).lower() or "failed to generate json" in str(exc).lower()
            route = _prompt_route(system_prompt)
            logger.warning(
                "LLM: Groq request failed (route=%s, model=%s, rate_limit=%s, error=%s: %s).",
                route,
                model,
                is_rate_limit,
                type(exc).__name__,
                exc,
            )
            if route == "qa" and is_json_validate_failed:
                logger.warning(
                    "LLM: Groq strict JSON validation failed for QA; retrying once with relaxed JSON mode."
                )
                try:
                    return self._generate_with_groq_relaxed_json(model, system_prompt, user_prompt)
                except Exception as retry_exc:
                    logger.error(
                        "LLM: Groq relaxed JSON retry failed for QA (%s: %s).",
                        type(retry_exc).__name__,
                        retry_exc,
                    )
            if _is_placement_mcq_generator(system_prompt):
                if is_rate_limit and self._gemini_fallback_available():
                    try:
                        return self._generate_with_gemini(system_prompt, user_prompt)
                    except LLMClientError as gemini_exc:
                        logger.error(
                            "LLM: Gemini fallback failed for placement after Groq rate-limit: %s",
                            gemini_exc,
                        )
                logger.warning(
                    "Groq placement generation failed (%s: %s); using local mock fallback.",
                    type(exc).__name__,
                    exc,
                )
                return self._mock_json(system_prompt, user_prompt)
            if self._gemini_fallback_available():
                try:
                    return self._generate_with_gemini(system_prompt, user_prompt)
                except LLMClientError as gemini_exc:
                    logger.error(
                        "LLM: Gemini fallback failed after Groq error (route=%s): %s",
                        route,
                        gemini_exc,
                    )
            else:
                logger.error("LLM: Gemini fallback unavailable after Groq error (route=%s).", route)
            if _is_lesson_or_syllabus_generation(system_prompt):
                raise LLMClientError(
                    "Groq failed and Gemini fallback failed/unavailable for lesson/syllabus generation. "
                    "Check API keys and provider quota."
                )
            return self._mock_json(system_prompt, user_prompt, self.use_validator_key)

    def _mock_json(self, system_prompt: str, user_prompt: str, use_validator_key: bool = False) -> str:
        sp = system_prompt.lower()
        if "placement" in sp and "validator" not in sp:
            # Keep placement flow usable in local/dev even if Groq is unavailable.
            concept_match = re.search(
                r"Rubric objective.*?:\s*(.+?)(?:\n|$)",
                user_prompt,
                flags=re.IGNORECASE | re.DOTALL,
            )
            concept = (concept_match.group(1).strip() if concept_match else "python basics").strip()
            if len(concept) > 80:
                concept = concept[:80].strip()
            concept_text = concept or "python basics"
            stems = [
                f"A student is reviewing {concept_text}. Which statement is most accurate?",
                f"Which option best reflects how {concept_text} works in Python?",
                f"In a beginner Python lesson, what does {concept_text} usually mean?",
                f"Pick the best explanation of {concept_text}.",
                f"When solving simple problems, how should you think about {concept_text}?",
                f"Which choice shows correct understanding of {concept_text}?",
                f"A quiz asks about {concept_text}. Which answer should be selected?",
                f"From these options, choose the strongest description of {concept_text}.",
            ]
            corrects = [
                f"It focuses on {concept_text} and applying it correctly in small Python tasks.",
                f"It is a core idea about {concept_text}, used to write predictable Python code.",
                f"It helps reason about {concept_text} while avoiding common beginner mistakes.",
                f"It describes practical use of {concept_text} in normal Python exercises.",
            ]
            wrong_pool = [
                "It means Python programs never produce runtime errors.",
                "It is only relevant for machine learning projects.",
                "It can only be used inside web frameworks.",
                "It is unrelated to expressions, conditions, or loops.",
                "It is only useful after learning advanced networking topics.",
                "It replaces the need to test or debug your code.",
                "It is a syntax rule that applies only to class inheritance.",
                "It is not used in beginner-level Python at all.",
            ]
            question = random.choice(stems)
            correct = random.choice(corrects)
            wrongs = random.sample(wrong_pool, k=3)
            choices = wrongs + [correct]
            random.shuffle(choices)
            return json.dumps(
                {
                    "question": question,
                    "choices": choices,
                    "correct_answer": correct,
                    "concept": concept,
                }
            )
        if "placementvalidatoragent" in sp.replace(" ", "") or (
            use_validator_key and "placement" in sp and "validator" in sp
        ):
            try:
                payload_in = json.loads(user_prompt)
                qs = payload_in.get("candidate_questions") or payload_in.get("questions") or []
                out: list[dict] = []
                for q in qs:
                    if not isinstance(q, dict):
                        continue
                    ch = [str(c).strip() for c in (q.get("choices") or [])]
                    ca = str(q.get("correct_answer", "")).strip()
                    out.append(
                        {
                            "question": str(q.get("question", "")).strip(),
                            "choices": ch[:4] if len(ch) >= 4 else ch + ["?"] * (4 - len(ch)),
                            "correct_answer": ca,
                            "concept": str(q.get("concept", "")).strip(),
                        }
                    )
                return json.dumps({"valid": True, "questions": out[: len(qs)]})
            except Exception:
                return json.dumps({"valid": False, "error": "mock placement validator could not parse input"})
        if "syllabus" in system_prompt.lower():
            up = user_prompt.lower()
            if "very_advanced" in up or "placement level: very" in up:
                payload = {
                    "units": [
                        {
                            "title": "Services & objects",
                            "summary": "APIs and OOP at scale.",
                            "lessons": [
                                {
                                    "topic": "Web APIs",
                                    "lesson_title": "Consuming HTTP APIs",
                                    "description": "Requests, JSON, status codes.",
                                },
                                {
                                    "topic": "Object-Oriented Python",
                                    "lesson_title": "Classes and instances",
                                    "description": "State, methods, and constructors.",
                                },
                                {
                                    "topic": "Databases",
                                    "lesson_title": "SQL with Python",
                                    "description": "Queries and connections.",
                                },
                                {
                                    "topic": "Visualization",
                                    "lesson_title": "Plotting basics",
                                    "description": "Charts from tabular data.",
                                },
                                {
                                    "topic": "Architecture and Best Practices",
                                    "lesson_title": "Structuring programs",
                                    "description": "Modules, tests, and design.",
                                },
                            ],
                        }
                    ]
                }
            elif "intermediate" in up:
                from app.core.placement_rubric import (
                    SYLLABUS_RUBRIC_CONCEPTS_BY_LEVEL,
                    SYLLABUS_TOPIC_ORDER_BY_LEVEL,
                )

                tops = list(SYLLABUS_TOPIC_ORDER_BY_LEVEL["intermediate"])
                rcs = list(SYLLABUS_RUBRIC_CONCEPTS_BY_LEVEL["intermediate"])
                titles = [
                    "Designing reusable function signatures",
                    "Controlling repetition with for and while",
                    "Reading and writing text files safely",
                    "Growing and slicing Python lists",
                    "Mapping real data with dictionaries",
                    "Choosing tuples when immutability matters",
                ]
                descs = [
                    "Learn how Python binds names to function objects and passes arguments. "
                    "You will practice writing small helpers and predicting return values from calls.",
                    "Explore definite and indefinite iteration with for and while loops. "
                    "You will trace loop variables and avoid common off-by-one mistakes in exercises.",
                    "Open files, iterate lines, and write output using patterns from Python for Everybody. "
                    "You will use context managers and handle encoding choices in short tasks.",
                    "Build and transform lists with indexing, slicing, and common list methods. "
                    "You will reason about aliasing and in-place changes through guided examples.",
                    "Store labeled data with dict lookups, keys, values, and safe updates. "
                    "You will practice counting, grouping, and reading nested structures from samples.",
                    "Use tuples for fixed records, multiple return values, and immutable sequences. "
                    "You will compare tuple and list trade-offs when modeling simple records.",
                ]
                lessons_a = []
                lessons_b = []
                for i in range(3):
                    lessons_a.append(
                        {
                            "topic": tops[i],
                            "lesson_title": titles[i],
                            "description": descs[i],
                            "learning_objectives": [
                                "Identify core ideas from the reading",
                                "Write small programs that apply the topic",
                                "Explain outcomes of the practice exercises",
                            ],
                            "rubric_concept": rcs[i],
                        }
                    )
                for i in range(3, 6):
                    lessons_b.append(
                        {
                            "topic": tops[i],
                            "lesson_title": titles[i],
                            "description": descs[i],
                            "learning_objectives": [
                                "Identify core ideas from the reading",
                                "Write small programs that apply the topic",
                                "Explain outcomes of the practice exercises",
                            ],
                            "rubric_concept": rcs[i],
                        }
                    )
                payload = {
                    "units": [
                        {
                            "title": "Functions, loops, and files",
                            "summary": "Chapters 4–5 and 7 foundations.",
                            "lessons": lessons_a,
                        },
                        {
                            "title": "Lists, dictionaries, and tuples",
                            "summary": "Chapters 8–10 data structures.",
                            "lessons": lessons_b,
                        },
                    ]
                }
            elif "advanced" in up and "very" not in up:
                payload = {
                    "units": [
                        {
                            "title": "Data shapes & text",
                            "summary": "Mappings, tuples, and pattern matching.",
                            "lessons": [
                                {
                                    "topic": "Dictionaries",
                                    "lesson_title": "Mapping keys to values",
                                    "description": "Dict operations and idioms.",
                                },
                                {
                                    "topic": "Tuples",
                                    "lesson_title": "Immutable data",
                                    "description": "Packing, unpacking, records.",
                                },
                                {
                                    "topic": "Regular Expressions",
                                    "lesson_title": "Pattern search",
                                    "description": "re module and practical patterns.",
                                },
                            ],
                        },
                        {
                            "title": "Programs that talk",
                            "summary": "Networking and parsing.",
                            "lessons": [
                                {
                                    "topic": "Networking",
                                    "lesson_title": "Sockets and protocols",
                                    "description": "Clients, servers, basics of HTTP.",
                                },
                                {
                                    "topic": "Data Parsing",
                                    "lesson_title": "Turning bytes into data",
                                    "description": "Formats beyond plain text.",
                                },
                            ],
                        },
                    ]
                }
            else:
                payload = {
                    "units": [
                        {
                            "title": "Foundations",
                            "summary": "Expressions through branching.",
                            "lessons": [
                                {
                                    "topic": "Expressions",
                                    "lesson_title": "Values, operators, and types",
                                    "description": "How Python evaluates expressions.",
                                },
                                {
                                    "topic": "Variable Assignment",
                                    "lesson_title": "Names, assignment, and memory",
                                    "description": "Binding names to objects.",
                                },
                                {
                                    "topic": "Conditionals",
                                    "lesson_title": "if, elif, else",
                                    "description": "Controlling flow with decisions.",
                                },
                            ],
                        },
                        {
                            "title": "Text & programs",
                            "summary": "Strings, I/O, and debugging.",
                            "lessons": [
                                {
                                    "topic": "Strings",
                                    "lesson_title": "Representing and manipulating text",
                                    "description": "Literals, indexing, basic operations.",
                                },
                                {
                                    "topic": "Debugging and Reading Code",
                                    "lesson_title": "Reading tracebacks and fixing bugs",
                                    "description": "Strategies from Python for Everybody.",
                                },
                            ],
                        },
                    ]
                }
            return json.dumps(payload)
        if "lesson" in system_prompt.lower() and "q&a" not in system_prompt.lower():
            payload = {
                "markdown": (
                    "## Learning objectives\n"
                    "- Evaluate simple expressions in Python 3.\n"
                    "- Relate examples to **Python for Everybody** (Charles Severance).\n"
                    "- Run short programs in the interpreter.\n\n"
                    "## Core ideas\n"
                    "An *expression* is code that produces a value. In Python for Everybody you first "
                    "meet numeric expressions, string literals, and the idea that types determine what "
                    "operations are allowed.\n\n"
                    "## Worked examples\n"
                    "```python\n"
                    "# Numeric expression\nprint(2 + 3)\n"
                    "# String replication uses *\nprint('ha' * 3)\n"
                    "```\n"
                    "The first line prints `5`. The second prints `hahaha` because `*` repeats strings.\n\n"
                    "## Common pitfalls\n"
                    "- Mixing incompatible types in `+` without converting.\n"
                    "- Forgetting that `**` is exponentiation, not XOR.\n\n"
                    "## Practice\n"
                    "1. Predict the output of `10 // 3` and `10 % 3`.\n"
                    "2. Write an expression that builds a border string using `*`.\n\n"
                    "## Summary\n"
                    "- Expressions reduce to values; Python prints them when asked.\n"
                    "- Strings and numbers follow different rules—keep types in mind.\n"
                )
            }
            return json.dumps(payload)
        sp = system_prompt.lower()
        if (
            "python basics tutor" in sp
            or "q&a tutor" in sp
            or "tutor for python for everybody" in sp
        ):
            payload = {
                "answer": (
                    "Python is a programming language you run with an interpreter. "
                    "Python for Everybody introduces expressions "
                    "(values combined with operators) and simple data types like strings and integers."
                )
            }
            return json.dumps(payload)
        return json.dumps(
            {
                "answer": (
                    "Expressions evaluate to single values; see Python for Everybody "
                    "(Variables and expressions) for operators and data types."
                )
            }
        )
