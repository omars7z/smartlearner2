import json

from app.core.config import get_settings
from app.core.groq_rate_limits import update_from_headers

try:
    from groq import Groq
except Exception:  # pragma: no cover
    Groq = None


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
            return self._mock_json(system_prompt, user_prompt)
        try:
            chat = self.client.chat.completions
            if hasattr(chat, "with_raw_response"):
                raw = chat.with_raw_response.create(
                    model=model,
                    temperature=0.2,
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
        except Exception:
            # Dev-safe fallback when Groq key/model/network is unavailable.
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
        if "placement" in system_prompt.lower() and "validator" not in system_prompt.lower():
            from app.core.placement_rubric import concepts_for_level, normalize_level

            slot = 1
            if "Question slot" in user_prompt:
                try:
                    slot = int(user_prompt.split("Question slot")[1].split("of")[0].strip())
                except Exception:
                    slot = 1
            elif "Question index:" in user_prompt:
                try:
                    slot = int(user_prompt.split("Question index:")[1].split("of")[0].strip())
                except Exception:
                    slot = 1
            lvl = "beginner"
            if "Placement level:" in user_prompt:
                try:
                    lvl = user_prompt.split("Placement level:")[1].split("\n")[0].strip()
                except Exception:
                    pass
            lvl = normalize_level(lvl)
            concepts = concepts_for_level(lvl)
            ci = max(0, min(slot - 1, len(concepts) - 1))
            concept = concepts[ci]
            payload = {
                "question": f"Mock diagnostic ({lvl}) #{slot}: what does `2 + 2` evaluate to?",
                "choices": ["3", "4", "22", "5"],
                "correct_answer": "4",
                "concept": concept,
            }
            return json.dumps(payload)
        if "syllabus" in system_prompt.lower():
            up = user_prompt.lower()
            if "very_advanced" in up or "placement level: very" in up:
                payload = {
                    "lessons": [
                        {"topic": "Web APIs", "description": "HTTP and services."},
                        {"topic": "Object-Oriented Python", "description": "Classes and objects."},
                    ]
                }
            elif "intermediate" in up:
                payload = {
                    "lessons": [
                        {"topic": "Functions", "description": "Defining and calling functions."},
                        {"topic": "Loops", "description": "for and while loops."},
                    ]
                }
            elif "advanced" in up:
                payload = {
                    "lessons": [
                        {"topic": "Dictionaries", "description": "Key-value maps."},
                        {"topic": "Tuples", "description": "Immutable sequences."},
                    ]
                }
            else:
                payload = {
                    "lessons": [
                        {"topic": "Expressions", "description": "Values and operators."},
                        {"topic": "Variable Assignment", "description": "Binding names to values."},
                    ]
                }
            return json.dumps(payload)
        if "lesson" in system_prompt.lower() and "q&a" not in system_prompt.lower():
            payload = {
                "markdown": (
                    "# Expressions\n"
                    "From Python for Everybody (Introduction / variables): "
                    "expressions evaluate to values, and string replication uses `*`."
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
