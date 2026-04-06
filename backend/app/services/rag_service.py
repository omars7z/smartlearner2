import pickle
from pathlib import Path

import numpy as np

from app.core.config import get_settings


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

    def retrieve_python_basics_context(self, query: str, k: int = 3) -> list[str]:
        if not self.chunks:
            return [
                "Python for Everybody (Variables, expressions, and statements): expressions evaluate to values.",
                "Python data types include integers, floats, strings, and booleans.",
                "String replication uses the * operator with a string and integer.",
            ]
        scored = []
        q_tokens = set(query.lower().split())
        for chunk in self.chunks:
            text = str(chunk.get("text", ""))
            t_tokens = set(text.lower().split())
            score = len(q_tokens.intersection(t_tokens)) / (np.sqrt(len(t_tokens) + 1))
            scored.append((score, text))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [text for _, text in scored[:k] if text]
        return top
