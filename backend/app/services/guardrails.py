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

# If QA overlap with PY4E book chunks is below this, skip the LLM (saves tokens).
QA_MIN_BOOK_RELEVANCE_SCORE = 0.022
# Single-token questions must clear this (e.g. "lists", "variables"); chitchat is handled separately.
QA_SINGLE_TOKEN_MIN_SCORE = 0.04

OUT_OF_SCOPE_TOPICS = {"asyncio", "metaclass", "c extensions", "threading internals"}
# Any lesson must touch at least one of these (lowercased match) so scope stays pedagogical, not arbitrary chat.
# Covers Python for Everybody–style topics beyond the intro chapter.
# Deep learning lessons are not expected to mention Python-for-Everybody anchors; use ML terms instead.
DL_SOURCE_KEY_CONCEPTS = frozenset(
    {
        "neural",
        "layer",
        "gradient",
        "activation",
        "loss",
        "training",
        "model",
        "network",
        "convolution",
        "tensor",
        "optimizer",
        "epoch",
        "backprop",
        "weight",
        "bias",
        "dropout",
        "batch",
        "dataset",
        "classification",
        "embedding",
        "attention",
        "learning rate",
        "regularization",
        "overfit",
        "parameter",
        "inference",
        "supervised",
    }
)

SOURCE_KEY_CONCEPTS = frozenset(
    {
        "expressions",
        "data types",
        "string replication",
        "variable assignment",
        "variable",
        "function",
        "def ",
        "loop",
        "for ",
        "while ",
        "list",
        "dictionary",
        "tuple",
        "string",
        "file",
        "open(",
        "condition",
        "if ",
        "class ",
        "import ",
        "module",
        "regex",
        "network",
        "socket",
        "database",
        "sql",
        "visualization",
        "object",
        "method",
        "iteration",
        "syntax",
        "algorithm",
    }
)


def sanitize_prompt(text: str) -> str:
    sanitized = text
    for pattern in INJECTION_PATTERNS:
        sanitized = re.sub(pattern, "[filtered]", sanitized, flags=re.IGNORECASE)
    return sanitized.strip()


def safe_json_loads(raw: str) -> dict | list:
    return json.loads(raw)


def parse_llm_json_response(raw: str) -> dict | list:
    """Parse JSON from LLM output, allowing optional ``` / ```json fences."""
    text = (raw or "").strip()
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1 :]
        fence = text.rfind("```")
        if fence != -1:
            text = text[:fence].strip()
    return json.loads(text)


def has_python3_hallucinations(answer: str) -> bool:
    disallowed = ["print x", "xrange(", "raw_input(", "apply("]
    return any(token in answer for token in disallowed)


def validate_content_scope(markdown: str, *, track: str = "python") -> tuple[bool, str]:
    lowered = markdown.lower()
    track_key = (track or "python").strip().lower().replace("-", "_")
    is_dl = track_key in {"deep_learning", "dl"}

    for topic in OUT_OF_SCOPE_TOPICS:
        if topic in lowered:
            return False, f"Out of scope topic detected: {topic}"

    concepts = DL_SOURCE_KEY_CONCEPTS if is_dl else SOURCE_KEY_CONCEPTS
    if not any(concept in lowered for concept in concepts):
        return False, (
            "Missing required source concept citation (no recognized deep learning topic terms)."
            if is_dl
            else "Missing required source concept citation (no recognized Python topic terms)."
        )

    if is_dl:
        if not any(
            phrase in lowered
            for phrase in (
                "deep learning",
                "deeplearningbook.org",
                "goodfellow",
                "bengio",
                "courville",
            )
        ):
            return False, "Lesson must cite the canonical deep learning source (Goodfellow et al.)."
    elif "python for everybody" not in lowered:
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
