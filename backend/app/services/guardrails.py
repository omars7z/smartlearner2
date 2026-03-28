import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass


INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"system prompt",
    r"developer message",
    r"jailbreak",
    r"bypass",
]

OUT_OF_SCOPE_TOPICS = {"asyncio", "metaclass", "c extensions", "threading internals"}
SOURCE_KEY_CONCEPTS = {"expressions", "data types", "string replication", "variable assignment"}


def sanitize_prompt(text: str) -> str:
    sanitized = text
    for pattern in INJECTION_PATTERNS:
        sanitized = re.sub(pattern, "[filtered]", sanitized, flags=re.IGNORECASE)
    return sanitized.strip()


def safe_json_loads(raw: str) -> dict | list:
    return json.loads(raw)


def has_python3_hallucinations(answer: str) -> bool:
    disallowed = ["print x", "xrange(", "raw_input(", "apply("]
    return any(token in answer for token in disallowed)


def validate_content_scope(markdown: str) -> tuple[bool, str]:
    lowered = markdown.lower()
    for topic in OUT_OF_SCOPE_TOPICS:
        if topic in lowered:
            return False, f"Out of scope topic detected: {topic}"
    if not any(concept in lowered for concept in SOURCE_KEY_CONCEPTS):
        return False, "Missing required source concept citation."
    if "automate the boring stuff" not in lowered:
        return False, "Lesson must cite the canonical source."
    return True, "ok"


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    return_code: int


def run_exam_code_in_sandbox(code: str, timeout_seconds: int = 2) -> SandboxResult:
    forbidden = ["import os", "import socket", "import subprocess", "__import__", "open("]
    if any(token in code for token in forbidden):
        return SandboxResult("", "Forbidden operation in code.", 1)

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tmp:
        tmp.write(code)
        temp_path = tmp.name

    try:
        proc = subprocess.run(
            [sys.executable, "-I", temp_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return SandboxResult(proc.stdout, proc.stderr, proc.returncode)
    except subprocess.TimeoutExpired:
        return SandboxResult("", "Execution timed out.", 1)
