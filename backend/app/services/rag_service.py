import pickle
import re
from pathlib import Path

import numpy as np

from app.core.config import get_settings
from app.services.guardrails import QA_MIN_BOOK_RELEVANCE_SCORE, QA_SINGLE_TOKEN_MIN_SCORE

# Used when chunks.pkl is missing (dev); same texts as previous fallback retrieval.
_FALLBACK_CHUNK_TEXTS = [
    "Python for Everybody (Variables, expressions, and statements): expressions evaluate to values.",
    "Python data types include integers, floats, strings, and booleans.",
    "String replication uses the * operator with a string and integer.",
]

# Strip noisy tokens so overlap reflects topic words, not "the / is / what".
_QA_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "how",
        "why",
        "when",
        "where",
        "do",
        "does",
        "did",
        "can",
        "could",
        "would",
        "should",
        "may",
        "might",
        "must",
        "to",
        "of",
        "in",
        "on",
        "with",
        "from",
        "as",
        "by",
        "and",
        "or",
        "but",
        "if",
        "then",
        "else",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "i",
        "you",
        "we",
        "they",
        "me",
        "my",
        "your",
        "about",
        "into",
        "just",
        "like",
        "so",
        "very",
        "too",
        "also",
        "not",
        "no",
        "yes",
        "please",
        "tell",
        "explain",
        "give",
        "help",
    }
)

# One-word messages that are never book questions (skip LLM).
_QA_CHITCHAT_TOKENS = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "thanks",
        "thank",
        "ok",
        "okay",
        "bye",
        "yo",
        "sup",
    }
)

# Core PY4E/Python learning terms that should pass scope-gate quickly.
_QA_PY4E_CORE_TOKENS = frozenset(
    {
        "python",
        "variable",
        "variables",
        "assignment",
        "expression",
        "expressions",
        "statement",
        "statements",
        "string",
        "strings",
        "integer",
        "integers",
        "float",
        "floats",
        "boolean",
        "booleans",
        "list",
        "lists",
        "dictionary",
        "dictionaries",
        "tuple",
        "tuples",
        "loop",
        "loops",
        "condition",
        "conditional",
        "function",
        "functions",
        "parameter",
        "parameters",
        "argument",
        "arguments",
        "file",
        "files",
        "input",
        "output",
        "debug",
        "debugging",
    }
)


def _query_tokens_for_overlap(query: str) -> set[str]:
    raw = {t for t in query.lower().split() if t}
    filtered = raw - _QA_STOPWORDS
    return filtered if filtered else raw


def _format_rag_passage(chunk: dict) -> str:
    """Prefix chunk text with stable PY4E location tags for the LLM."""
    text = str(chunk.get("text", "")).strip()
    parts: list[str] = []
    src = str(chunk.get("source", "") or "").strip()
    ch = str(chunk.get("chapter_title", "") or "").strip()
    sid = str(chunk.get("sub_lesson_id", "") or "").strip()
    stitle = str(chunk.get("sub_lesson_title", "") or "").strip()
    if src or ch or sid or stitle:
        head = []
        if src:
            head.append(src)
        if ch and ch not in head:
            head.append(ch)
        if sid:
            head.append(f"sub_lesson:{sid}")
        if stitle and stitle not in " ".join(head):
            head.append(stitle)
        parts.append("[" + " | ".join(head) + "]")
    parts.append(text)
    return "\n".join(parts)


class RAGService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.chunks = self._load_chunks()

    def _load_chunks(self) -> list[dict]:
        chunk_file = Path(self.settings.vector_db_path) / "chunks.pkl"
        if not chunk_file.exists():
            return []
        with chunk_file.open("rb") as f:
            data = pickle.load(f)
        if isinstance(data, list):
            return data
        return []

    def _chunks_for_retrieval(self) -> list[dict]:
        if not self.chunks:
            return [{"text": t} for t in _FALLBACK_CHUNK_TEXTS]
        return self.chunks

    def _best_chunk_score_and_overlap(self, query: str) -> tuple[float, int]:
        """Highest token-overlap score vs a single chunk, and how many query tokens hit that chunk."""
        q_tokens = _query_tokens_for_overlap(query.strip())
        if not q_tokens:
            return 0.0, 0
        best_score = -1.0
        best_overlap = 0
        for chunk in self._chunks_for_retrieval():
            text = str(chunk.get("text", ""))
            t_tokens = set(text.lower().split())
            inter = q_tokens.intersection(t_tokens)
            n = len(inter)
            score = n / (np.sqrt(len(t_tokens) + 1))
            if score > best_score:
                best_score = score
                best_overlap = n
        return best_score, best_overlap

    def max_book_relevance_score(self, query: str) -> float:
        """
        Heuristic overlap between the question and PY4E chunk texts (same scoring as retrieval).
        Does not call the LLM.
        """
        s, _ = self._best_chunk_score_and_overlap(query)
        return s

    def is_likely_book_related_question(self, query: str) -> bool:
        """
        True if the question plausibly relates to PY4E material (cheap heuristic, no LLM).
        Multi-word questions must match at least two meaningful words somewhere in the best-matching
        chunk so incidental single-token hits (e.g. "weather" in a scraping example) do not pass.
        """
        q = query.strip()
        mt = _query_tokens_for_overlap(q)
        if not mt:
            return False
        if len(mt) == 1 and next(iter(mt)) in _QA_CHITCHAT_TOKENS:
            return False
        # Accept direct Python/PY4E concept questions even if lexical overlap is low.
        if mt.intersection(_QA_PY4E_CORE_TOKENS):
            return True
        score, overlap_n = self._best_chunk_score_and_overlap(q)
        if len(mt) >= 2 and overlap_n < 2:
            return False
        if len(mt) == 1:
            return score >= QA_SINGLE_TOKEN_MIN_SCORE
        return score >= QA_MIN_BOOK_RELEVANCE_SCORE

    def retrieve_course_context(self, query: str, k: int = 3, *, track: str | None = None) -> list[str]:
        """
        Lexical match over chunk text + TOC metadata.
        When `track` is set, prefer chunks from that course (Python vs Deep Learning).
        """
        chunks = self._chunks_for_retrieval()
        if track:
            track_key = track.strip().lower().replace("-", "_")
            if track_key in {"deep_learning", "dl"}:
                filtered = [
                    c
                    for c in chunks
                    if "deep learning" in str(c.get("track", "")).lower()
                    or str(c.get("source", "")).lower().startswith("dl_")
                ]
            elif track_key == "python":
                filtered = [
                    c
                    for c in chunks
                    if "python" in str(c.get("track", "")).lower()
                    or str(c.get("source", "")).startswith("py4e_")
                ]
            else:
                filtered = []
            if filtered:
                chunks = filtered
        q_raw = (query or "").strip()
        q_tokens = {t for t in re.findall(r"[a-zA-Z_]{3,}", q_raw.lower())}
        q_lower = q_raw.lower()
        scored: list[tuple[float, dict]] = []

        for chunk in chunks:
            text = str(chunk.get("text", ""))
            sub_title = str(chunk.get("sub_lesson_title", "") or "")
            sub_id = str(chunk.get("sub_lesson_id", "") or "")
            chapter_title = str(chunk.get("chapter_title", "") or "")
            meta_line = f"{sub_title} {sub_id} {chapter_title}".lower()
            t_tokens = set(re.findall(r"[a-zA-Z_]{3,}", text.lower()))
            t_tokens |= set(re.findall(r"[a-zA-Z_]{3,}", meta_line))
            overlap = len(q_tokens.intersection(t_tokens))
            score = overlap / (np.sqrt(len(t_tokens) + 1))
            if sub_id and sub_id in q_lower:
                score += 0.35
            if sub_title and len(sub_title) > 5:
                st_l = sub_title.lower()
                if st_l in q_lower:
                    score += 0.5
                for w in re.findall(r"[a-zA-Z_]{4,}", st_l):
                    if w in q_tokens:
                        score += 0.08
            scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        out: list[str] = []
        for _, ch in scored[:k]:
            passage = _format_rag_passage(ch)
            if passage:
                out.append(passage)
        return out

    def retrieve_python_basics_context(self, query: str, k: int = 3, *, track: str = "python") -> list[str]:
        """Track-scoped RAG retrieval (defaults to Python/PY4E)."""
        return self.retrieve_course_context(query, k=k, track=track)
