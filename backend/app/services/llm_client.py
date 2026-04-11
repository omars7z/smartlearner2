import json

from app.core.config import get_settings
from app.core.groq_rate_limits import update_from_headers

try:
    from groq import Groq
except Exception:  # pragma: no cover
    Groq = None


class LLMClientError(RuntimeError):
    """Raised when placement (and other agent-only paths) need Groq but it is unavailable."""


def _is_placement_mcq_generator(system_prompt: str) -> bool:
    """PlacementGeneratorAgent — must use live LLM, not static fallbacks."""
    s = system_prompt.lower()
    return "placement" in s and "validator" not in s


class LLMClient:
    """Groq client. Use ``use_validator_key=True`` for validator-only agents (separate API key)."""

    def __init__(self, *, use_validator_key: bool = False) -> None:
        self.settings = get_settings()
        self.use_validator_key = use_validator_key
        self.client = None
        if not Groq:
            return
        key: str | None
        if use_validator_key:
            key = self.settings.groq_api_key_validators or self.settings.groq_api_key
        else:
            key = self.settings.groq_api_key
        if key:
            self.client = Groq(api_key=key)

    def generate_json(self, model: str, system_prompt: str, user_prompt: str) -> str:
        if self.client is None:
            if _is_placement_mcq_generator(system_prompt):
                parts: list[str] = []
                if not Groq:
                    parts.append("Install the Groq SDK: pip install groq.")
                if not (self.settings.groq_api_key or "").strip():
                    parts.append("Set GROQ_API_KEY in backend/.env (see .env.example).")
                base = " ".join(parts) if parts else "Groq client could not be created (check key and network)."
                raise LLMClientError(
                    f"{base} Placement MCQs are generated only by the LLM agent — there is no static fallback."
                )
            return self._mock_json(system_prompt, user_prompt)
        try:
            chat = self.client.chat.completions
            if hasattr(chat, "with_raw_response"):
                raw = chat.with_raw_response.create(
                    model=model,
                    temperature=0.4,
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
            if _is_placement_mcq_generator(system_prompt):
                raise LLMClientError(
                    f"Groq placement generation failed ({type(exc).__name__}: {exc}). "
                    "Fix network, model name, quota, or GROQ_API_KEY; placement does not use static questions."
                ) from exc
            return self._mock_json(system_prompt, user_prompt, self.use_validator_key)

    def _mock_json(self, system_prompt: str, user_prompt: str, use_validator_key: bool = False) -> str:
        sp = system_prompt.lower()
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
