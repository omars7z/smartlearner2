"""
Python for Everybody (PY4E) — track grouping + per-chapter sub-lessons (book-style TOC).

Track map (aligned with product tiers):
  beginner:       Ch 1, 2, 3, 6
  intermediate: Ch 4, 5, 7, 8, 9, 10
  advanced:       Ch 11–14
  very_advanced:  Ch 15–16
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

# chapter_key|lesson_id|title
_TOC_LINES = """
py4e_01_intro|1.1|Creativity and motivation
py4e_01_intro|1.2|Computer hardware architecture
py4e_01_intro|1.3|Understanding programming
py4e_01_intro|1.4|Words and sentences
py4e_01_intro|1.5|Conversing with Python
py4e_01_intro|1.6|Terminology: Interpreter and compiler
py4e_01_intro|1.7|Writing a program
py4e_01_intro|1.8|What is a program?
py4e_01_intro|1.9|The building blocks of programs
py4e_01_intro|1.10|What could possibly go wrong?
py4e_01_intro|1.11|Debugging
py4e_01_intro|1.12|The learning journey
py4e_01_intro|1.13|Glossary
py4e_01_intro|1.14|Exercises
py4e_02_variables|2.1|Values and types
py4e_02_variables|2.2|Variables
py4e_02_variables|2.3|Variable names and keywords
py4e_02_variables|2.4|Statements
py4e_02_variables|2.5|Operators and operands
py4e_02_variables|2.6|Expressions
py4e_02_variables|2.7|Order of operations
py4e_02_variables|2.8|Modulus operator
py4e_02_variables|2.9|String operations
py4e_02_variables|2.10|Asking the user for input
py4e_02_variables|2.11|Comments
py4e_02_variables|2.12|Choosing mnemonic variable names
py4e_02_variables|2.13|Debugging
py4e_02_variables|2.14|Glossary
py4e_02_variables|2.15|Exercises
py4e_03_conditional|3.1|Boolean expressions
py4e_03_conditional|3.2|Logical operators
py4e_03_conditional|3.3|Conditional execution
py4e_03_conditional|3.4|Alternative execution
py4e_03_conditional|3.5|Chained conditionals
py4e_03_conditional|3.6|Nested conditionals
py4e_03_conditional|3.7|Catching exceptions using try and except
py4e_03_conditional|3.8|Short-circuit evaluation of logical expressions
py4e_03_conditional|3.9|Debugging
py4e_03_conditional|3.10|Glossary
py4e_03_conditional|3.11|Exercises
py4e_04_functions|4.1|Function calls
py4e_04_functions|4.2|Built-in functions
py4e_04_functions|4.3|Type conversion functions
py4e_04_functions|4.4|Math functions
py4e_04_functions|4.5|Random numbers
py4e_04_functions|4.6|Adding new functions
py4e_04_functions|4.7|Definitions and uses
py4e_04_functions|4.8|Flow of execution
py4e_04_functions|4.9|Parameters and arguments
py4e_04_functions|4.10|Fruitful functions and void functions
py4e_04_functions|4.11|Why functions?
py4e_04_functions|4.12|Debugging
py4e_04_functions|4.13|Glossary
py4e_04_functions|4.14|Exercises
py4e_05_iterations|5.1|Updating variables
py4e_05_iterations|5.2|The while statement
py4e_05_iterations|5.3|Infinite loops
py4e_05_iterations|5.4|Finishing iterations with continue
py4e_05_iterations|5.5|Definite loops using for
py4e_05_iterations|5.6|Loop patterns
py4e_05_iterations|5.6.1|Counting and summing loops
py4e_05_iterations|5.6.2|Maximum and minimum loops
py4e_05_iterations|5.7|Debugging
py4e_05_iterations|5.8|Glossary
py4e_05_iterations|5.9|Exercises
py4e_06_strings|6.1|A string is a sequence
py4e_06_strings|6.2|Getting the length of a string using len
py4e_06_strings|6.3|Traversal through a string with a loop
py4e_06_strings|6.4|String slices
py4e_06_strings|6.5|Strings are immutable
py4e_06_strings|6.6|Looping and counting
py4e_06_strings|6.7|The in operator
py4e_06_strings|6.8|String comparison
py4e_06_strings|6.9|String methods
py4e_06_strings|6.10|Parsing strings
py4e_06_strings|6.11|Formatted string literals
py4e_06_strings|6.12|Debugging
py4e_06_strings|6.13|Glossary
py4e_06_strings|6.14|Exercises
py4e_07_files|7.1|Persistence
py4e_07_files|7.2|Opening files
py4e_07_files|7.3|Text files and lines
py4e_07_files|7.4|Reading files
py4e_07_files|7.5|Searching through a file
py4e_07_files|7.6|Letting the user choose the file name
py4e_07_files|7.7|Using try, except, and open
py4e_07_files|7.8|Writing files
py4e_07_files|7.9|Debugging
py4e_07_files|7.10|Glossary
py4e_07_files|7.11|Exercises
py4e_08_lists|8.1|A list is a sequence
py4e_08_lists|8.2|Lists are mutable
py4e_08_lists|8.3|Traversing a list
py4e_08_lists|8.4|List operations
py4e_08_lists|8.5|List slices
py4e_08_lists|8.6|List methods
py4e_08_lists|8.7|Deleting elements
py4e_08_lists|8.8|Lists and functions
py4e_08_lists|8.9|Lists and strings
py4e_08_lists|8.10|Parsing lines
py4e_08_lists|8.11|Objects and values
py4e_08_lists|8.12|Aliasing
py4e_08_lists|8.13|List arguments
py4e_08_lists|8.14|Debugging
py4e_08_lists|8.15|Glossary
py4e_08_lists|8.16|Exercises
py4e_09_dictionaries|9.1|Dictionary as a set of counters
py4e_09_dictionaries|9.2|Dictionaries and files
py4e_09_dictionaries|9.3|Looping and dictionaries
py4e_09_dictionaries|9.4|Advanced text parsing
py4e_09_dictionaries|9.5|Debugging
py4e_09_dictionaries|9.6|Glossary
py4e_09_dictionaries|9.7|Exercises
py4e_10_tuples|10.1|Tuples are immutable
py4e_10_tuples|10.2|Comparing tuples
py4e_10_tuples|10.3|Tuple assignment
py4e_10_tuples|10.4|Dictionaries and tuples
py4e_10_tuples|10.5|Multiple assignment with dictionaries
py4e_10_tuples|10.6|The most common words
py4e_10_tuples|10.7|Using tuples as keys in dictionaries
py4e_10_tuples|10.8|Sequences: strings, lists, and tuples — Oh My!
py4e_10_tuples|10.9|List comprehension
py4e_10_tuples|10.10|Debugging
py4e_10_tuples|10.11|Glossary
py4e_10_tuples|10.12|Exercises
py4e_11_regex|11.1|Character matching in regular expressions
py4e_11_regex|11.2|Extracting data using regular expressions
py4e_11_regex|11.3|Combining searching and extracting
py4e_11_regex|11.4|Escape character
py4e_11_regex|11.5|Summary
py4e_11_regex|11.6|Bonus section for Unix / Linux users
py4e_11_regex|11.7|Debugging
py4e_11_regex|11.8|Glossary
py4e_11_regex|11.9|Exercises
py4e_12_network|12.1|Hypertext Transfer Protocol — HTTP
py4e_12_network|12.2|The world's simplest web browser
py4e_12_network|12.3|Retrieving an image over HTTP
py4e_12_network|12.4|Retrieving web pages with urllib
py4e_12_network|12.5|Reading binary files using urllib
py4e_12_network|12.6|Parsing HTML and scraping the web
py4e_12_network|12.7|Parsing HTML using regular expressions
py4e_12_network|12.8|Parsing HTML using BeautifulSoup
py4e_12_network|12.9|Bonus section for Unix / Linux users
py4e_12_network|12.10|Glossary
py4e_12_network|12.11|Exercises
py4e_13_web|13.1|eXtensible Markup Language — XML
py4e_13_web|13.2|Parsing XML
py4e_13_web|13.3|Looping through nodes
py4e_13_web|13.4|JavaScript Object Notation — JSON
py4e_13_web|13.5|Parsing JSON
py4e_13_web|13.6|Application Programming Interfaces
py4e_13_web|13.7|Security and API usage
py4e_13_web|13.8|Glossary
py4e_14_objects|14.1|Managing larger programs
py4e_14_objects|14.2|Getting started
py4e_14_objects|14.3|Using objects
py4e_14_objects|14.4|Starting with programs
py4e_14_objects|14.5|Subdividing a problem
py4e_14_objects|14.6|Our first Python object
py4e_14_objects|14.7|Classes as types
py4e_14_objects|14.8|Object lifecycle
py4e_14_objects|14.9|Multiple instances
py4e_14_objects|14.10|Inheritance
py4e_14_objects|14.11|Summary
py4e_14_objects|14.12|Glossary
py4e_15_database|15.1|What is a database?
py4e_15_database|15.2|Database concepts
py4e_15_database|15.3|Database browser for SQLite
py4e_15_database|15.4|Creating a database table
py4e_15_database|15.5|Structured Query Language summary
py4e_15_database|15.6|Multiple tables and basic data modeling
py4e_15_database|15.7|Data model diagrams
py4e_15_database|15.8|Automatically creating primary keys
py4e_15_database|15.9|Logical keys for fast lookup
py4e_15_database|15.10|Adding constraints to the database
py4e_15_database|15.11|Sample multi-table application
py4e_15_database|15.12|Many-to-many relationships in databases
py4e_15_database|15.13|Modeling data at the many-to-many connection
py4e_15_database|15.14|Summary
py4e_15_database|15.15|Debugging
py4e_15_database|15.16|Glossary
py4e_16_viz|16.1|Building a map from OpenStreetMap geocoded data
py4e_16_viz|16.2|Visualizing networks and interconnections
py4e_16_viz|16.3|Visualizing mail data
"""


def _parse_toc() -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    for raw in _TOC_LINES.strip().splitlines():
        line = raw.strip()
        if not line:
            continue
        key, lid, title = line.split("|", 2)
        out.setdefault(key, []).append({"id": lid, "title": title.strip()})
    return out


TRACKS: tuple[dict[str, Any], ...] = (
    {
        "id": "beginner",
        "label_en": "Beginner",
        "chapter_keys": ("py4e_01_intro", "py4e_02_variables", "py4e_03_conditional", "py4e_06_strings"),
    },
    {
        "id": "intermediate",
        "label_en": "Intermediate",
        "chapter_keys": (
            "py4e_04_functions",
            "py4e_05_iterations",
            "py4e_07_files",
            "py4e_08_lists",
            "py4e_09_dictionaries",
            "py4e_10_tuples",
        ),
    },
    {
        "id": "advanced",
        "label_en": "Advanced",
        "chapter_keys": ("py4e_11_regex", "py4e_12_network", "py4e_13_web", "py4e_14_objects"),
    },
    {
        "id": "very_advanced",
        "label_en": "Very Advanced",
        "chapter_keys": ("py4e_15_database", "py4e_16_viz"),
    },
)

# chapter_key -> (number, short title, difficulty tier, rag_topics)
CHAPTER_META: dict[str, dict[str, Any]] = {
    "py4e_01_intro": {"number": 1, "title": "Why we program", "difficulty": "beginner", "topics": ["introduction"]},
    "py4e_02_variables": {
        "number": 2,
        "title": "Variables, expressions, and statements",
        "difficulty": "beginner",
        "topics": ["python_basics"],
    },
    "py4e_03_conditional": {"number": 3, "title": "Conditional execution (if/else)", "difficulty": "beginner", "topics": ["control_flow"]},
    "py4e_04_functions": {"number": 4, "title": "Functions", "difficulty": "intermediate", "topics": ["functions"]},
    "py4e_05_iterations": {"number": 5, "title": "Iteration (loops)", "difficulty": "intermediate", "topics": ["control_flow"]},
    "py4e_06_strings": {"number": 6, "title": "Strings", "difficulty": "beginner", "topics": ["strings"]},
    "py4e_07_files": {"number": 7, "title": "Files", "difficulty": "intermediate", "topics": ["file_io"]},
    "py4e_08_lists": {"number": 8, "title": "Lists", "difficulty": "intermediate", "topics": ["lists"]},
    "py4e_09_dictionaries": {"number": 9, "title": "Dictionaries", "difficulty": "intermediate", "topics": ["dictionaries"]},
    "py4e_10_tuples": {"number": 10, "title": "Tuples", "difficulty": "intermediate", "topics": ["tuples"]},
    "py4e_11_regex": {"number": 11, "title": "Regular Expressions", "difficulty": "advanced", "topics": ["regex"]},
    "py4e_12_network": {"number": 12, "title": "Networked Programs", "difficulty": "advanced", "topics": ["networking"]},
    "py4e_13_web": {"number": 13, "title": "Web Services (XML, JSON, APIs)", "difficulty": "advanced", "topics": ["web_services"]},
    "py4e_14_objects": {"number": 14, "title": "Object-Oriented Programming", "difficulty": "advanced", "topics": ["oop"]},
    "py4e_15_database": {"number": 15, "title": "Databases & SQL (SQLite)", "difficulty": "very_advanced", "topics": ["databases"]},
    "py4e_16_viz": {
        "number": 16,
        "title": "Visualizing Data (OpenStreetMap, Networks, Mail Data)",
        "difficulty": "very_advanced",
        "topics": ["visualization"],
    },
}


@lru_cache
def _outlines() -> dict[str, list[dict[str, str]]]:
    return _parse_toc()


def chapter_payload(chapter_key: str) -> dict[str, Any] | None:
    meta = CHAPTER_META.get(chapter_key)
    if not meta:
        return None
    subs = _outlines().get(chapter_key, [])
    track_id = next((t["id"] for t in TRACKS if chapter_key in t["chapter_keys"]), "beginner")
    return {
        "key": chapter_key,
        "track_id": track_id,
        **meta,
        "sub_lessons": subs,
    }


def curriculum_payload() -> dict[str, Any]:
    chapters = {k: chapter_payload(k) for k in CHAPTER_META}
    return {
        "source": "Python for Everybody (PY4E) — chapter TOC mirrors the open textbook.",
        "tracks": [dict(t) for t in TRACKS],
        "chapters": chapters,
    }


def book_chunker_chapter_config() -> dict[str, dict[str, Any]]:
    """Shape compatible with data_pipeline.pdf_chunker.BOOK_CONFIG['python_py4e']['chapters']."""
    out: dict[str, dict[str, Any]] = {}
    for key, meta in CHAPTER_META.items():
        out[key] = {
            "title": meta["title"],
            "difficulty": meta["difficulty"],
            "topics": list(meta["topics"]),
        }
    return out


def sub_lessons_for_chapter(chapter_key: str) -> list[dict[str, str]]:
    """TOC rows for RAG chunk alignment (id + title)."""
    return list(_outlines().get(chapter_key, []))
