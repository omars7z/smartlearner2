import json

from app.core.config import get_settings

try:
    from groq import Groq
except Exception:  # pragma: no cover
    Groq = None


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = None
        if Groq and self.settings.groq_api_key:
            self.client = Groq(api_key=self.settings.groq_api_key)

    def generate_json(self, model: str, system_prompt: str, user_prompt: str) -> str:
        if self.client is None:
            return self._mock_json(system_prompt, user_prompt)
        try:
            completion = self.client.chat.completions.create(
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
            return self._mock_json(system_prompt, user_prompt)

    def _mock_json(self, system_prompt: str, user_prompt: str) -> str:
        if "placement" in system_prompt.lower():
            payload = {
                "questions": [
                    {
                        "question": "What is 2 + 2 in Python?",
                        "choices": ["3", "4", "22", "5"],
                        "correct_answer": "4",
                        "concept": "expressions",
                    }
                ]
            }
            return json.dumps(payload)
        if "syllabus" in system_prompt.lower():
            payload = {
                "lessons": [
                    {"title": "Expressions and Values", "topic": "Expressions", "prerequisites": []},
                    {
                        "title": "Variables and Assignment",
                        "topic": "Variable Assignment",
                        "prerequisites": ["Expressions"],
                    },
                ]
            }
            return json.dumps(payload)
        if "lesson" in system_prompt.lower() and "q&a" not in system_prompt.lower():
            payload = {
                "markdown": (
                    "# Expressions\n"
                    "From Automate the Boring Stuff with Python, Python Basics: "
                    "expressions evaluate to values, and string replication uses `*`."
                )
            }
            return json.dumps(payload)
        sp = system_prompt.lower()
        if (
            "python basics tutor" in sp
            or "q&a tutor" in sp
            or "tutor for automate the boring stuff" in sp
        ):
            payload = {
                "answer": (
                    "Python is a programming language you run with an interpreter. "
                    "Automate the Boring Stuff with Python (Python Basics) introduces expressions "
                    "(values combined with operators) and simple data types like strings and integers."
                )
            }
            return json.dumps(payload)
        return json.dumps(
            {
                "answer": (
                    "Expressions evaluate to single values; see Automate the Boring Stuff with Python, "
                    "Python Basics, for operators and data types."
                )
            }
        )
