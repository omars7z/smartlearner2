from __future__ import annotations

"""
Scrape the free HTML textbook from Python for Everybody (Charles Severance,
University of Michigan). Same material as the Coursera specialization:
https://www.coursera.org/specializations/python
Chapters: https://www.py4e.com/html3/

Outputs clean .txt files under backend/data/books/python for RAG / embedding ingestion.
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

# (url, filename stem, chapter title, difficulty)
CHAPTERS: List[Chapter] = [
    ("https://www.py4e.com/html3/01-intro.php", "py4e_01_intro", "Introduction", "beginner"),
    (
        "https://www.py4e.com/html3/02-variables.php",
        "py4e_02_variables",
        "Variables, Expressions, and Statements",
        "beginner",
    ),
    ("https://www.py4e.com/html3/03-conditional.php", "py4e_03_conditional", "Conditionals", "beginner"),
    ("https://www.py4e.com/html3/04-functions.php", "py4e_04_functions", "Functions", "intermediate"),
    ("https://www.py4e.com/html3/05-iterations.php", "py4e_05_iterations", "Iterations", "intermediate"),
    ("https://www.py4e.com/html3/06-strings.php", "py4e_06_strings", "Strings", "beginner"),
    ("https://www.py4e.com/html3/07-files.php", "py4e_07_files", "Files", "intermediate"),
    ("https://www.py4e.com/html3/08-lists.php", "py4e_08_lists", "Lists", "intermediate"),
    ("https://www.py4e.com/html3/09-dictionaries.php", "py4e_09_dictionaries", "Dictionaries", "intermediate"),
    ("https://www.py4e.com/html3/10-tuples.php", "py4e_10_tuples", "Tuples", "intermediate"),
    ("https://www.py4e.com/html3/11-regex.php", "py4e_11_regex", "Regular Expressions", "advanced"),
    ("https://www.py4e.com/html3/12-network.php", "py4e_12_network", "Networked Programs", "advanced"),
    ("https://www.py4e.com/html3/13-web.php", "py4e_13_web", "Python and Web Services", "advanced"),
    ("https://www.py4e.com/html3/14-objects.php", "py4e_14_objects", "Python Objects", "advanced"),
    ("https://www.py4e.com/html3/15-database.php", "py4e_15_database", "Python and Databases", "very_advanced"),
    ("https://www.py4e.com/html3/16-viz.php", "py4e_16_viz", "Data Visualization", "very_advanced"),
]

COURSE_PAGE = "https://www.coursera.org/specializations/python"
MATERIALS_ROOT = "https://www.py4e.com/html3/"
SOURCE_LINE = (
    "Python for Everybody (Charles R. Severance, University of Michigan) | "
    f"Coursera: {COURSE_PAGE} | Text: {MATERIALS_ROOT}"
)


def get_main_content(soup: BeautifulSoup):
    """Extract chapter body text from a PY4E HTML page."""
    for tag in soup.find_all(["nav", "header", "footer", "script", "style", "aside"]):
        tag.decompose()
    return soup.body


def scrape_chapter(url: str, filename: str, title: str, difficulty: str) -> bool:
    try:
        headers = {"User-Agent": "Mozilla/5.0 SmartLearner Educational Bot"}
        response = requests.get(url, headers=headers, timeout=25)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        main = get_main_content(soup)

        if not main:
            print(f"  [warn] No body for {title}")
            return False

        text = main.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\n+", "\n", text)

        content = f"""TRACK: Python Foundations
CHAPTER: {title}
DIFFICULTY: {difficulty}
SOURCE: {SOURCE_LINE}
URL: {url}
---
{text}
"""
        filepath = os.path.join(OUTPUT_DIR, f"{filename}.txt")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        word_count = len(text.split())
        print(f"  OK {title}: {word_count:,} words -> {filename}.txt")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  Failed {title}: {e}")
        return False


def main() -> None:
    print("Python for Everybody (PY4E) - scraping HTML textbook chapters")
    print(f"   Saving to: {OUTPUT_DIR}/")
    print(f"   Total chapters: {len(CHAPTERS)}\n")

    success = 0
    for url, filename, title, difficulty in CHAPTERS:
        if scrape_chapter(url, filename, title, difficulty):
            success += 1
        time.sleep(1)

    print("\n" + "=" * 40)
    print(f"Done: {success}/{len(CHAPTERS)} chapters saved.")


if __name__ == "__main__":
    main()
