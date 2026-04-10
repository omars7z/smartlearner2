import pickle
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


def _query_tokens_for_overlap(query: str) -> set[str]:
    raw = {t for t in query.lower().split() if t}
    filtered = raw - _QA_STOPWORDS
    return filtered if filtered else raw


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
        score, overlap_n = self._best_chunk_score_and_overlap(q)
        if len(mt) >= 2 and overlap_n < 2:
            return False
        if len(mt) == 1:
            return score >= QA_SINGLE_TOKEN_MIN_SCORE
        return score >= QA_MIN_BOOK_RELEVANCE_SCORE

    def retrieve_python_basics_context(self, query: str, k: int = 3) -> list[str]:
        chunks = self._chunks_for_retrieval()
        scored = []
        q_tokens = set(query.lower().split())
        for chunk in chunks:
            text = str(chunk.get("text", ""))
            t_tokens = set(text.lower().split())
            score = len(q_tokens.intersection(t_tokens)) / (np.sqrt(len(t_tokens) + 1))
            scored.append((score, text))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [text for _, text in scored[:k] if text]
        return top
