from __future__ import annotations

import json

import httpx


def main() -> None:
  url = "http://127.0.0.1:8000/api/v1/qa/ask"
  payload = {"question": "How do for loops work in Python?", "current_topic": "Python Basics"}
  r = httpx.post(url, json=payload, timeout=60.0)
  print("status:", r.status_code)
  resp = r.json()
  print("intent:", resp.get("intent"))
  result = resp.get("result", {})
  rag = result.get("rag") or {}
  print("rag_source:", rag.get("source"))
  print("retrieval_confidence:", rag.get("retrieval_confidence"))
  chunks = rag.get("chunks") or rag.get("selected_chunks") or []
  print("num_chunks:", len(chunks))
  for c in chunks[:2]:
    print("- source:", c.get("source"), "topic:", c.get("topic"), "score:", c.get("relevance_score"))
    preview = (c.get("text") or c.get("content", ""))[:200].replace("\n", " ")
    print("  text_preview:", preview)


if __name__ == "__main__":
  main()

