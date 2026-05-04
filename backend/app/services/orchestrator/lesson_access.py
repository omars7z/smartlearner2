"""Syllabus progression: sub-lesson blocks and access rules."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.entities import Lesson


@dataclass(frozen=True)
class _Block:
    kind: str  # "single" | "parent"
    root: Lesson
    children: tuple[Lesson, ...]


def _sorted_roots(lessons: list[Lesson]) -> list[Lesson]:
    roots = [L for L in lessons if L.parent_lesson_id is None]
    return sorted(roots, key=lambda x: x.order_index)


def build_progression_blocks(lessons: list[Lesson]) -> list[_Block]:
    """Order-preserving blocks: each root is either a single assessable lesson or a parent with sub-lessons."""
    roots = _sorted_roots(lessons)
    out: list[_Block] = []
    for r in roots:
        children = sorted(
            [L for L in lessons if L.parent_lesson_id == r.id],
            key=lambda x: x.order_index,
        )
        if children:
            out.append(_Block("parent", r, tuple(children)))
        else:
            out.append(_Block("single", r, ()))
    return out


def split_markdown_into_sub_focuses(markdown: str) -> tuple[list[str], list[str]]:
    """
    Returns (part_markdown_snippets, suggested_titles) for 2–4 sub-lessons.
    Uses ## sections when possible; otherwise splits body into balanced chunks.
    """
    md = (markdown or "").strip()
    if not md:
        return (["## Introduction\n\n_Building your lesson…_", "## Practice\n\n_Stay tuned._"], ["Part 1", "Part 2"])

    parts: list[str] = []
    if "## " in md:
        lines = md.split("\n")
        chunks: list[str] = []
        buf: list[str] = []
        for line in lines:
            if line.startswith("## ") and buf:
                chunks.append("\n".join(buf).strip())
                buf = [line]
            else:
                buf.append(line)
        if buf:
            chunks.append("\n".join(buf).strip())
        parts = [c for c in chunks if c.strip()]
    else:
        paras = [p.strip() for p in md.split("\n\n") if p.strip()]
        if not paras:
            parts = [md]
        else:
            n = min(4, max(2, len(paras) // 3 + 1))
            step = max(1, len(paras) // n)
            for i in range(n):
                slice_ = paras[i * step :] if i == n - 1 else paras[i * step : (i + 1) * step]
                parts.append("\n\n".join(slice_))

    n = len(parts)
    if n < 2:
        parts = [md[: max(1, len(md) // 2)], md[max(1, len(md) // 2) :]]
    if n > 4:
        merged: list[str] = []
        step = (n + 3) // 4
        for i in range(4):
            seg = parts[i * step :] if i == 3 else parts[i * step : (i + 1) * step]
            merged.append("\n\n".join(seg))
        parts = merged

    titles: list[str] = []
    for i, p in enumerate(parts):
        title_line = ""
        for line in p.split("\n"):
            if line.startswith("## "):
                title_line = line[3:].strip()
                break
        titles.append(title_line or f"Part {i + 1}")

    return (parts, titles)


def assessable_sequence_ids(blocks: list[_Block]) -> list[int]:
    """Lesson ids that receive assessments, in progression order."""
    ids: list[int] = []
    for b in blocks:
        if b.kind == "parent":
            ids.extend(L.id for L in b.children)
        else:
            ids.append(b.root.id)
    return ids


def predecessor_assessable_id(blocks: list[_Block], lesson_id: int) -> int | None:
    seq = assessable_sequence_ids(blocks)
    try:
        idx = seq.index(lesson_id)
    except ValueError:
        return None
    if idx == 0:
        return None
    return seq[idx - 1]


def block_for_lesson(blocks: list[_Block], lesson_id: int) -> _Block | None:
    for b in blocks:
        if b.kind == "parent":
            if b.root.id == lesson_id or any(c.id == lesson_id for c in b.children):
                return b
        elif b.root.id == lesson_id:
            return b
    return None


def is_block_fully_passed(block: _Block, passed_map: dict[int, bool]) -> bool:
    if block.kind == "parent":
        return all(passed_map.get(c.id, False) for c in block.children)
    return bool(passed_map.get(block.root.id, False))


def can_user_access_lesson(
    *,
    lesson_id: int,
    blocks: list[_Block],
    passed_map: dict[int, bool],
) -> bool:
    """Parents with sub-lessons are overview hubs; assessable leaves chain on prior sibling or prior block."""
    block = block_for_lesson(blocks, lesson_id)
    if block is None:
        return False
    if block.kind == "parent" and block.root.id == lesson_id:
        pred = predecessor_assessable_id(blocks, block.children[0].id) if block.children else None
        if pred is None:
            return True
        pred_block = block_for_lesson(blocks, pred)
        if pred_block is None:
            return False
        return is_block_fully_passed(pred_block, passed_map)
    assessable = assessable_sequence_ids(blocks)
    if lesson_id not in assessable:
        return False
    pred = predecessor_assessable_id(blocks, lesson_id)
    if pred is None:
        return True
    pred_block = block_for_lesson(blocks, pred)
    cur_block = block_for_lesson(blocks, lesson_id)
    if (
        pred_block is not None
        and cur_block is not None
        and pred_block.kind == "parent"
        and cur_block.kind == "parent"
        and pred_block.root.id == cur_block.root.id
    ):
        return bool(passed_map.get(pred, False))
    if pred_block is None:
        return False
    return is_block_fully_passed(pred_block, passed_map)
