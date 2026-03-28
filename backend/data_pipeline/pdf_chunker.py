from __future__ import annotations

"""
Simple book chunker for RAG.

Supports both PDF and TXT source files under configured folders and
produces paragraph-aware text chunks with metadata.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import json
import pickle
import re

import numpy as np
from pypdf import PdfReader


@dataclass
class Chunk:
  text: str
  metadata: Dict[str, Any]


class BookChunker:
  """
  Chunk educational books into smaller passages for RAG ingestion.
  """

  # Minimal config; extend as needed.
  BOOK_CONFIG: Dict[str, Dict[str, Any]] = {
    "python_automatetheboringstuff": {
      "track": "Python Foundations",
      "folder": "backend/data/books/python",
      "chapters": {
        "intro": {
          "title": "Introduction",
          "difficulty": "beginner",
          "topics": ["introduction"],
        },
        "ch01_basics": {
          "title": "Python Basics",
          "difficulty": "beginner",
          "topics": ["python_basics"],
        },
        "ch02_flow": {
          "title": "Flow Control",
          "difficulty": "beginner",
          "topics": ["control_flow"],
        },
        "ch03_functions": {
          "title": "Functions",
          "difficulty": "beginner",
          "topics": ["functions"],
        },
        "ch04_lists": {
          "title": "Lists",
          "difficulty": "beginner",
          "topics": ["lists"],
        },
        "ch05_dicts": {
          "title": "Dictionaries",
          "difficulty": "beginner",
          "topics": ["dictionaries"],
        },
        "ch06_strings": {
          "title": "Strings",
          "difficulty": "beginner",
          "topics": ["strings"],
        },
        "ch07_regex": {
          "title": "Regular Expressions",
          "difficulty": "intermediate",
          "topics": ["regex"],
        },
        "ch08_input": {
          "title": "Input Validation",
          "difficulty": "intermediate",
          "topics": ["input_validation"],
        },
        "ch09_files": {
          "title": "Reading and Writing Files",
          "difficulty": "intermediate",
          "topics": ["file_io"],
        },
        "ch10_organize": {
          "title": "Organizing Files",
          "difficulty": "intermediate",
          "topics": ["filesystem"],
        },
        "ch11_debug": {
          "title": "Debugging",
          "difficulty": "intermediate",
          "topics": ["debugging"],
        },
        "ch12_scraping": {
          "title": "Web Scraping",
          "difficulty": "advanced",
          "topics": ["web_scraping"],
        },
      },
    },
  }

  def __init__(self) -> None:
    self.all_chunks: List[Chunk] = []
    self.index = None
    self.embed_model_name = "all-MiniLM-L6-v2"

  # ------------ file readers -------------

  def extract_text_from_pdf(self, pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(pages)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

  def extract_text_from_txt(self, txt_path: str) -> str:
    """Extract clean text from .txt file."""
    with open(txt_path, "r", encoding="utf-8") as f:
      text = f.read()

    # Remove metadata header lines (TRACK:, CHAPTER:, etc.)
    lines = text.split("\n")
    content_lines: List[str] = []
    skip_header = True

    for line in lines:
      if skip_header and line.strip() == "---":
        skip_header = False
        continue
      if not skip_header:
        content_lines.append(line)

    clean_text = " ".join(content_lines)
    clean_text = re.sub(r"\s+", " ", clean_text).strip()
    return clean_text

  # ------------ chunking logic -------------

  def smart_chunk_text(
    self,
    text: str,
    source: str,
    track: str,
    topic: str,
    difficulty: str,
    chapter_title: str,
    target_words: int = 180,
    overlap_words: int = 30,
  ) -> List[Chunk]:
    """
    Very simple word-based chunker with overlap.
    """
    words = text.split()
    chunks: List[Chunk] = []
    i = 0
    while i < len(words):
      window = words[i : i + target_words]
      if not window:
        break
      chunk_text = " ".join(window)
      meta = {
        "source": source,
        "track": track,
        "topic": topic,
        "difficulty": difficulty,
        "chapter_title": chapter_title,
      }
      chunks.append(Chunk(text=chunk_text, metadata=meta))
      i += max(target_words - overlap_words, 1)
    return chunks

  # ------------ processing per book -------------

  def process_book(self, book_key: str) -> int:
    config = self.BOOK_CONFIG[book_key]
    folder = Path(config["folder"])
    total_chunks = 0

    if not folder.exists():
      print(f"   Folder not found: {folder}")
      return 0

    # Support both PDF and TXT files
    files = list(folder.glob("*.pdf")) + list(folder.glob("*.txt"))
    files = sorted(files)

    if not files:
      print(f"   No files found in {folder}")
      return 0

    for file_path in files:
      # Detect chapter info from filename
      chapter_key = None
      stem_lower = file_path.stem.lower()
      for key in config["chapters"]:
        if key in stem_lower:
          chapter_key = key
          break

      if chapter_key:
        ch_info = config["chapters"][chapter_key]
      else:
        ch_info = {
          "title": file_path.stem.replace("_", " ").title(),
          "difficulty": "intermediate",
          "topics": [stem_lower],
        }

      print(f"   {file_path.name}")

      try:
        # Read based on file type
        if file_path.suffix.lower() == ".pdf":
          text = self.extract_text_from_pdf(str(file_path))
        elif file_path.suffix.lower() == ".txt":
          text = self.extract_text_from_txt(str(file_path))
        else:
          continue

        if len(text.split()) < 50:
          print("      Too little text, skipping")
          continue

        primary_topic = ch_info["topics"][0]

        chunks = self.smart_chunk_text(
          text=text,
          source=file_path.stem,
          track=config["track"],
          topic=primary_topic,
          difficulty=ch_info["difficulty"],
          chapter_title=ch_info["title"],
        )

        self.all_chunks.extend(chunks)
        total_chunks += len(chunks)
        print(f"      {len(chunks)} chunks from {len(text.split()):,} words")

      except Exception as e:  # noqa: BLE001
        print(f"      Error: {e}")

    return total_chunks


  # ------------ index + persistence -------------

  def build_faiss_index(self) -> None:
    """Embed all chunks and build an in-memory FAISS index."""
    if not self.all_chunks:
      print("No chunks to index.")
      return
    from sentence_transformers import SentenceTransformer
    import faiss

    texts = [c.text for c in self.all_chunks]
    print(f"Building embeddings for {len(texts)} chunks using {self.embed_model_name} ...")
    model = SentenceTransformer(self.embed_model_name)
    emb = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    emb = emb.astype("float32")
    dim = emb.shape[1]
    self.index = faiss.IndexFlatIP(dim)
    self.index.add(emb)
    print(f"FAISS index built with {self.index.ntotal} vectors (dim={dim}).")

  def save(self, output_dir: str = "backend/vector_db") -> None:
    """Save FAISS index and chunks metadata to disk."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if not self.all_chunks or self.index is None:
      print("Nothing to save (no chunks or index).")
      return

    import faiss

    index_path = out_path / "faiss.index"
    chunks_path = out_path / "chunks.pkl"
    summary_path = out_path / "index_summary.json"

    faiss.write_index(self.index, str(index_path))

    serializable_chunks = [
      {"text": c.text, **c.metadata} for c in self.all_chunks
    ]
    with open(chunks_path, "wb") as f:
      pickle.dump(serializable_chunks, f)

    by_topic: Dict[str, int] = {}
    by_track: Dict[str, int] = {}
    for c in serializable_chunks:
      by_topic[c.get("topic", "unknown")] = by_topic.get(c.get("topic", "unknown"), 0) + 1
      by_track[c.get("track", "unknown")] = by_track.get(c.get("track", "unknown"), 0) + 1

    summary = {
      "total_chunks": len(serializable_chunks),
      "by_topic": by_topic,
      "by_track": by_track,
      "embed_model": self.embed_model_name,
    }
    with open(summary_path, "w", encoding="utf-8") as f:
      json.dump(summary, f, indent=2)

    print(f"Saved index to {index_path}")
    print(f"Saved chunks to {chunks_path}")
    print(f"Saved summary to {summary_path}")

  def print_summary(self) -> None:
    if not self.all_chunks:
      print("No chunks in memory.")
      return
    total = len(self.all_chunks)
    print(f"\nSummary: {total} chunks in memory.")


def main() -> None:
  chunker = BookChunker()

  total = 0
  for book_key in ["python_automatetheboringstuff"]:
    print(f"Processing book: {book_key}")
    n = chunker.process_book(book_key)
    total += n
    print(f"   Book done: {n} chunks")

  if total == 0:
    print("No chunks created!")
    return

  chunker.build_faiss_index()
  chunker.save(output_dir="backend/vector_db")
  chunker.print_summary()
  print("\nVector DB saved! Restart the server to use new data.")


if __name__ == "__main__":
  main()

