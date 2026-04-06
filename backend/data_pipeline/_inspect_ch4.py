from __future__ import annotations

import requests
from bs4 import BeautifulSoup

url = "https://www.py4e.com/html3/08-lists.php"
headers = {"User-Agent": "Mozilla/5.0"}
r = requests.get(url, headers=headers, timeout=20)
print("status:", r.status_code)
soup = BeautifulSoup(r.text, "html.parser")

print("=== ALL DIV/SECTION/MAIN/ARTICLE tags with id/class ===")
for tag in soup.find_all(["div", "section", "main", "article"]):
  cid = tag.get("id") or ""
  cls = " ".join(tag.get("class", [])) if tag.get("class") else ""
  preview = tag.get_text(strip=True)[:80].replace("\n", " ")
  print(f"<{tag.name} id='{cid}' class='{cls}'> :: {len(tag.get_text(strip=True))} chars :: {preview}")

