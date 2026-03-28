from __future__ import annotations

import httpx
from pprint import pprint


def main() -> None:
  url = "http://127.0.0.1:8000/api/v1/qa/ask"
  payload = {"question": "Explain Python lists with examples.", "current_topic": "Python Basics"}
  r = httpx.post(url, json=payload, timeout=60.0)
  print("status:", r.status_code)
  resp = r.json()
  pprint(resp)


if __name__ == "__main__":
  main()

