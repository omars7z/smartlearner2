from __future__ import annotations

"""
Scrape chapters from:
Automate the Boring Stuff with Python (3rd Edition)
https://automatetheboringstuff.com/

Each chapter is saved as a clean .txt file under backend/data/books/python
for later RAG / embedding ingestion.
"""

import os
import re
import time
from typing import List, Tuple

import requests
from bs4 import BeautifulSoup

OUTPUT_DIR = "backend/data/books/python"
os.makedirs(OUTPUT_DIR, exist_ok=True)

Chapter = Tuple[str, str, str, str]

CHAPTERS: List[Chapter] = [
  ("https://automatetheboringstuff.com/2e/chapter0/", "intro", "Introduction", "beginner"),
  ("https://automatetheboringstuff.com/2e/chapter1/", "ch01_basics", "Python Basics", "beginner"),
  ("https://automatetheboringstuff.com/2e/chapter2/", "ch02_flow", "Flow Control", "beginner"),
  ("https://automatetheboringstuff.com/2e/chapter3/", "ch03_functions", "Functions", "beginner"),
  ("https://automatetheboringstuff.com/2e/chapter4/", "ch04_lists", "Lists", "beginner"),
  ("https://automatetheboringstuff.com/2e/chapter5/", "ch05_dicts", "Dictionaries", "beginner"),
  ("https://automatetheboringstuff.com/2e/chapter6/", "ch06_strings", "Strings", "beginner"),
  ("https://automatetheboringstuff.com/2e/chapter7/", "ch07_regex", "Regular Expressions", "intermediate"),
  ("https://automatetheboringstuff.com/2e/chapter8/", "ch08_input", "Input Validation", "intermediate"),
  ("https://automatetheboringstuff.com/2e/chapter9/", "ch09_files", "Reading Writing Files", "intermediate"),
  ("https://automatetheboringstuff.com/2e/chapter10/", "ch10_organize", "Organizing Files", "intermediate"),
  ("https://automatetheboringstuff.com/2e/chapter11/", "ch11_debug", "Debugging", "intermediate"),
  ("https://automatetheboringstuff.com/2e/chapter12/", "ch12_scraping", "Web Scraping", "advanced"),
  ("https://automatetheboringstuff.com/2e/chapter13/", "ch13_excel", "Excel Spreadsheets", "advanced"),
  ("https://automatetheboringstuff.com/2e/chapter14/", "ch14_sheets", "Google Sheets", "advanced"),
  ("https://automatetheboringstuff.com/2e/chapter15/", "ch15_sqlite", "SQLite Databases", "advanced"),
  ("https://automatetheboringstuff.com/2e/chapter16/", "ch16_pdf", "PDF and Word Documents", "advanced"),
  ("https://automatetheboringstuff.com/2e/chapter17/", "ch17_csv", "CSV JSON XML Files", "intermediate"),
  ("https://automatetheboringstuff.com/2e/chapter18/", "ch18_time", "Time and Scheduling", "advanced"),
  ("https://automatetheboringstuff.com/2e/chapter19/", "ch19_email", "Sending Email", "advanced"),
  ("https://automatetheboringstuff.com/2e/chapter20/", "ch20_images", "Images and Graphs", "advanced"),
  ("https://automatetheboringstuff.com/2e/chapter21/", "ch21_ocr", "Recognizing Text in Images", "advanced"),
  ("https://automatetheboringstuff.com/2e/chapter22/", "ch22_keyboard", "Keyboard and Mouse", "advanced"),
  ("https://automatetheboringstuff.com/2e/chapter23/", "ch23_speech", "Text to Speech", "advanced"),
]


def get_main_content(soup: BeautifulSoup):
  """Best-effort extractor for main chapter content."""
  # Pre-built candidates in preferred order
  candidates = [
    soup.find("div", {"id": "main-content"}),
    soup.find("div", {"id": "content"}),
    soup.find("div", {"class": "content"}),
    soup.find("div", {"id": "chapter"}),
    # Observed on automatetheboringstuff.com:
    soup.find("div", {"class": "calibre"}),
    soup.find("article"),
    soup.find("main"),
    soup.find("div", {"role": "main"}),
  ]

  for cand in candidates:
    if cand:
      text_len = len(cand.get_text(strip=True))
      if text_len > 500:
        return cand

  # Last resort: div with most text
  all_divs = soup.find_all("div")
  if all_divs:
    return max(all_divs, key=lambda d: len(d.get_text(strip=True)))

  return soup.body


def scrape_chapter(url: str, filename: str, title: str, difficulty: str) -> bool:
  try:
    headers = {"User-Agent": "Mozilla/5.0 SmartLearner Educational Bot"}
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove navigation, headers, footers, scripts, ads
    for tag in soup.find_all(["nav", "header", "footer", "script", "style", "aside"]):
      tag.decompose()

    main = get_main_content(soup)

    if not main:
      try:
        print(f"  [warn] No main content found for {title}")
      except Exception:
        pass
      return False

    text = main.get_text(separator=" ", strip=True)

    # Normalise whitespace
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\n+", "\n", text)

    content = f"""TRACK: Python Foundations
CHAPTER: {title}
DIFFICULTY: {difficulty}
SOURCE: Automate the Boring Stuff with Python (3rd Edition)
URL: {url}
---
{text}
"""
    filepath = os.path.join(OUTPUT_DIR, f"{filename}.txt")
    with open(filepath, "w", encoding="utf-8") as f:
      f.write(content)

    word_count = len(text.split())
    try:
      print(f"  OK {title}: {word_count:,} words → {filename}.txt")
    except Exception:
      pass
    return True
  except Exception as e:  # noqa: BLE001
    try:
      print(f"  Failed {title}: {e}")
    except Exception:
      pass
    return False


def main() -> None:
  # Avoid Unicode emojis for Windows consoles (cp1252).
  try:
    print("Scraping Automate the Boring Stuff with Python (3rd Edition)")
    print(f"   Saving to: {OUTPUT_DIR}/")
    print(f"   Total chapters: {len(CHAPTERS)}\n")
  except Exception:
    pass

  success = 0
  for url, filename, title, difficulty in CHAPTERS:
    if scrape_chapter(url, filename, title, difficulty):
      success += 1
    time.sleep(1)  # Be polite to the server

  print("\n" + "=" * 40)
  try:
    print(f"Done! {success}/{len(CHAPTERS)} chapters scraped")
    print(f"Files saved to: {OUTPUT_DIR}/")
  except Exception:
    pass

  total_words = 0
  for f_name in os.listdir(OUTPUT_DIR):
    if not f_name.endswith(".txt"):
      continue
    with open(os.path.join(OUTPUT_DIR, f_name), encoding="utf-8") as file:
      total_words += len(file.read().split())

  try:
    print(f"Total words: {total_words:,}")
    print(f"Estimated RAG chunks: ~{total_words // 150:,}")
  except Exception:
    pass


if __name__ == "__main__":
  main()

