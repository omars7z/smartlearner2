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


def _needle_variants(title: str) -> List[str]:
  """Try a few phrasings so scraped HTML text still matches TOC titles."""
  t = title.strip()
  seen: set[str] = set()
  out: List[str] = []
  for cand in (
    t,
    t.split("(", 1)[0].strip(),
    t.split(":", 1)[-1].strip() if ":" in t else "",
    t.split(":", 1)[0].strip() if ":" in t else "",
    t.replace("—", "-"),
    t.replace(" / ", " "),
  ):
    if cand and len(cand) >= 4 and cand.lower() not in seen:
      seen.add(cand.lower())
      out.append(cand)
  return out


def _build_sublesson_anchors(full_text: str, sub_lessons: List[Dict[str, str]]) -> List[tuple[int, str, str]]:
  """
  Map each TOC sub-lesson to a start word index in `full_text` (single-space normalized).
  Scans in TOC order; each match must occur after the previous match (avoids re-using
  generic headings like 'Debugging' from an earlier section).
  """
  if not full_text or not sub_lessons:
    return []
  fl = full_text.lower()
  anchors: List[tuple[int, str, str]] = []
  last_char = -1
  for sl in sub_lessons:
    sid = str(sl.get("id") or "").strip()
    title = str(sl.get("title") or "").strip()
    if not sid or not title:
      continue
    best_pos = -1
    for needle in _needle_variants(title):
      p = fl.find(needle.lower(), last_char + 1)
      if p >= 0 and (best_pos < 0 or p < best_pos):
        best_pos = p
    if best_pos < 0:
      continue
    prefix = full_text[:best_pos]
    word_index = len(prefix.split()) if prefix.strip() else 0
    anchors.append((word_index, sid, title))
    last_char = best_pos
  anchors.sort(key=lambda x: x[0])
  deduped: List[tuple[int, str, str]] = []
  for a in anchors:
    if deduped and deduped[-1][0] == a[0]:
      continue
    deduped.append(a)
  return deduped


def _sublesson_for_word_index(
  anchors: List[tuple[int, str, str]],
  word_index: int,
  sub_lessons: List[Dict[str, str]],
) -> tuple[str, str]:
  if not sub_lessons:
    return "", ""
  if not anchors:
    return "", ""
  if word_index < anchors[0][0]:
    return "preface", "Chapter opening"
  sid_out, title_out = anchors[0][1], anchors[0][2]
  for wi, sid, title in anchors:
    if wi <= word_index:
      sid_out, title_out = sid, title
    else:
      break
  return sid_out, title_out


class BookChunker:
  """
  Chunk educational books into smaller passages for RAG ingestion.
  """

  # Minimal config; extend as needed.
  BOOK_CONFIG: Dict[str, Dict[str, Any]] = {
    "python_py4e": {
      "track": "Python Foundations",
      "folder": "data/books/python",
      "chapters": {
        "py4e_01_intro": {
          "title": "Introduction",
          "difficulty": "beginner",
          "topics": ["introduction"],
        },
        "py4e_02_variables": {
          "title": "Variables, Expressions, and Statements",
          "difficulty": "beginner",
          "topics": ["python_basics"],
        },
        "py4e_03_conditional": {
          "title": "Conditionals",
          "difficulty": "beginner",
          "topics": ["control_flow"],
        },
        "py4e_04_functions": {
          "title": "Functions",
          "difficulty": "intermediate",
          "topics": ["functions"],
        },
        "py4e_05_iterations": {
          "title": "Iterations",
          "difficulty": "intermediate",
          "topics": ["control_flow"],
        },
        "py4e_06_strings": {
          "title": "Strings",
          "difficulty": "beginner",
          "topics": ["strings"],
        },
        "py4e_07_files": {
          "title": "Files",
          "difficulty": "intermediate",
          "topics": ["file_io"],
        },
        "py4e_08_lists": {
          "title": "Lists",
          "difficulty": "intermediate",
          "topics": ["lists"],
        },
        "py4e_09_dictionaries": {
          "title": "Dictionaries",
          "difficulty": "intermediate",
          "topics": ["dictionaries"],
        },
        "py4e_10_tuples": {
          "title": "Tuples",
          "difficulty": "intermediate",
          "topics": ["tuples"],
        },
        "py4e_11_regex": {
          "title": "Regular Expressions",
          "difficulty": "advanced",
          "topics": ["regex"],
        },
        "py4e_12_network": {
          "title": "Networked Programs",
          "difficulty": "advanced",
          "topics": ["networking"],
        },
        "py4e_13_web": {
          "title": "Python and Web Services",
          "difficulty": "advanced",
          "topics": ["web_services"],
        },
        "py4e_14_objects": {
          "title": "Python Objects",
          "difficulty": "advanced",
          "topics": ["oop"],
        },
        "py4e_15_database": {
          "title": "Python and Databases",
          "difficulty": "very_advanced",
          "topics": ["databases"],
        },
        "py4e_16_viz": {
          "title": "Data Visualization",
          "difficulty": "very_advanced",
          "topics": ["visualization"],
        },
      },
    },
    "deep_learning_lectures": {
      "track": "Deep Learning",
      "folder": "data/books/deep_learning",
      "chapters": {
        "dl_01_math": {
          "title": "Math Foundations",
          "difficulty": "beginner",
          "topics": ["vectors", "matrices", "calculus"],
        },
        "dl_02_python": {
          "title": "Python for Deep Learning",
          "difficulty": "beginner",
          "topics": ["numpy", "tensor_ops"],
        },
        "dl_03_data": {
          "title": "Data Pipelines and Splits",
          "difficulty": "beginner",
          "topics": ["datasets", "data_splits", "leakage"],
        },
        "dl_04_linear_models": {
          "title": "Linear and Logistic Models",
          "difficulty": "beginner",
          "topics": ["linear_regression", "logistic_regression", "losses"],
        },
        "dl_05_nn_basics": {
          "title": "Neural Network Fundamentals",
          "difficulty": "intermediate",
          "topics": ["mlp", "activations", "forward_pass"],
        },
        "dl_06_backprop": {
          "title": "Backpropagation",
          "difficulty": "intermediate",
          "topics": ["chain_rule", "gradients", "backward_pass"],
        },
        "dl_07_optimization": {
          "title": "Optimization",
          "difficulty": "intermediate",
          "topics": ["sgd", "adam", "learning_rate"],
        },
        "dl_08_regularization": {
          "title": "Generalization and Regularization",
          "difficulty": "intermediate",
          "topics": ["dropout", "batch_norm", "early_stopping"],
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
    *,
    chapter_key: str | None = None,
    sub_lessons: List[Dict[str, str]] | None = None,
  ) -> List[Chunk]:
    """
    Word-based chunker with overlap. Optionally tags each chunk with PY4E sub-lesson
    (TOC) metadata by locating subsection titles in normalized chapter text.
    """
    words = text.split()
    full_text = " ".join(words)
    anchors: List[tuple[int, str, str]] = []
    subs = sub_lessons or []
    if subs and full_text:
      anchors = _build_sublesson_anchors(full_text, subs)

    chunks: List[Chunk] = []
    i = 0
    while i < len(words):
      window = words[i : i + target_words]
      if not window:
        break
      chunk_text = " ".join(window)
      sub_id, sub_title = _sublesson_for_word_index(anchors, i, subs)
      meta: Dict[str, Any] = {
        "source": source,
        "track": track,
        "topic": topic,
        "difficulty": difficulty,
        "chapter_title": chapter_title,
      }
      if chapter_key:
        meta["chapter_key"] = chapter_key
      if sub_id:
        meta["sub_lesson_id"] = sub_id
      if sub_title:
        meta["sub_lesson_title"] = sub_title
      chunks.append(Chunk(text=chunk_text, metadata=meta))
      i += max(target_words - overlap_words, 1)
    return chunks

  # ------------ processing per book -------------

  def process_book(self, book_key: str) -> int:
    config = self.BOOK_CONFIG[book_key]
    chapters_cfg: Dict[str, Any] = config["chapters"]
    if book_key == "python_py4e":
      try:
        from app.core.py4e_curriculum import book_chunker_chapter_config

        chapters_cfg = book_chunker_chapter_config()
      except ImportError:
        pass
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
      for key in chapters_cfg:
        if key in stem_lower:
          chapter_key = key
          break

      if chapter_key:
        ch_info = chapters_cfg[chapter_key]
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

        sub_lessons: List[Dict[str, str]] | None = None
        ck = chapter_key
        if book_key == "python_py4e" and chapter_key:
          try:
            from app.core.py4e_curriculum import sub_lessons_for_chapter

            sub_lessons = sub_lessons_for_chapter(chapter_key)
          except ImportError:
            sub_lessons = None

        chunks = self.smart_chunk_text(
          text=text,
          source=file_path.stem,
          track=config["track"],
          topic=primary_topic,
          difficulty=ch_info["difficulty"],
          chapter_title=ch_info["title"],
          chapter_key=ck,
          sub_lessons=sub_lessons,
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
  for book_key in ["python_py4e", "deep_learning_lectures"]:
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

