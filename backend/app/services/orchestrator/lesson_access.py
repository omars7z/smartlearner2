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


def _unit_key_for_block(block: _Block) -> str:
    ut = (getattr(block.root, "unit_title", None) or "").strip()
    return ut if ut else "__default_unit__"


def block_checkpoint_lesson_id(block: _Block) -> int | None:
    """Progression checkpoint for this block (quiz id for singles, last sub-lesson for parents)."""
    if block.kind == "parent":
        if not block.children:
            return None
        return block.children[-1].id
    return block.root.id


def unit_entry_checkpoint_ids(blocks: list[_Block]) -> frozenset[int]:
    """Checkpoints for the first topic in each unit — readable without passing the prior unit."""
    seen_units: set[str] = set()
    starters: set[int] = set()
    for b in blocks:
        key = _unit_key_for_block(b)
        if key in seen_units:
            continue
        seen_units.add(key)
        cid = block_checkpoint_lesson_id(b)
        if cid is not None:
            starters.add(cid)
    return frozenset(starters)


_MAX_SUB_LESSON_PARTS = 3


def _merge_into_n_parts(parts: list[str], target: int) -> list[str]:
    """Merge many sections into exactly ``target`` balanced snippets."""
    if len(parts) <= target:
        return parts
    merged: list[str] = []
    n_src = len(parts)
    for i in range(target):
        start = i * n_src // target
        end = (i + 1) * n_src // target if i < target - 1 else n_src
        merged.append("\n\n".join(parts[start:end]))
    return merged


def split_markdown_into_sub_focuses(markdown: str) -> tuple[list[str], list[str]]:
    """
    Returns (part_markdown_snippets, suggested_titles) for 2–3 sub-lessons.
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
        elif len(paras) >= 4:
            parts = _merge_into_n_parts(paras, _MAX_SUB_LESSON_PARTS)
        elif len(paras) >= 2:
            mid = max(1, len(paras) // 2)
            parts = ["\n\n".join(paras[:mid]), "\n\n".join(paras[mid:])]
        else:
            parts = [md]

    n = len(parts)
    if n < 2:
        parts = [md[: max(1, len(md) // 2)], md[max(1, len(md) // 2) :]]
    if n > _MAX_SUB_LESSON_PARTS:
        parts = _merge_into_n_parts(parts, _MAX_SUB_LESSON_PARTS)

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
    """Lesson ids that gate progression (quiz checkpoints), in course order.

    For a parent topic split into sub-lessons, only the **final** sub-lesson is
    assessable; earlier parts are readable without a quiz. Single-root blocks
    still use the root lesson as the checkpoint.
    """
    ids: list[int] = []
    for b in blocks:
        if b.kind == "parent":
            if not b.children:
                continue
            ids.append(b.children[-1].id)
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
        if not block.children:
            return False
        return bool(passed_map.get(block.children[-1].id, False))
    return bool(passed_map.get(block.root.id, False))


def can_user_access_lesson(
    *,
    lesson_id: int,
    blocks: list[_Block],
    passed_map: dict[int, bool],
) -> bool:
    """Parents with sub-lessons are overview hubs; all parts unlock together; only the last part gates the next topic.

    The first topic in each ``unit_title`` group is always reachable without finishing the previous unit.
    """
    unit_starters = unit_entry_checkpoint_ids(blocks)
    block = block_for_lesson(blocks, lesson_id)
    if block is None:
        return False
    if block.kind == "parent" and block.children:
        last_child_id = block.children[-1].id
        if lesson_id == block.root.id or any(c.id == lesson_id for c in block.children):
            if last_child_id in unit_starters:
                return True
            pred = predecessor_assessable_id(blocks, last_child_id)
            if pred is None:
                return True
            pred_block = block_for_lesson(blocks, pred)
            if pred_block is None:
                return False
            return is_block_fully_passed(pred_block, passed_map)
    assessable = assessable_sequence_ids(blocks)
    if lesson_id not in assessable:
        return False
    if lesson_id in unit_starters:
        return True
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
