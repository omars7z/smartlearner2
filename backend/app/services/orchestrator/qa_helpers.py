from app.core.placement_rubric import normalize_track


def qa_track_scope_envelope(track: str) -> dict:
    """No LLM call: question looks unrelated to selected-track chunks (saves tokens)."""
    if normalize_track(track) in {"deep_learning", "dl"}:
        msg = (
            "I'm only the **Deep Learning** chatbot for this course - I help with deep learning "
            "book and lecture-note material plus your lessons. Ask something about deep learning topics."
        )
    else:
        msg = (
            "I'm only the **Python for Everybody (PY4E)** chatbot for this course - I help with the "
            "book material and your lessons. Ask something about PY4E or your course topics."
        )
    return {
        "status": "ok",
        "intent": "qa_py4e_scope",
        "result": {
            "status": "ok",
            "explanation": {
                "core_explanation": msg,
            },
            "rag": {
                "chunks_used": 0,
                "selected_chunks": [],
                "skipped_llm": True,
            },
        },
        "routing": {"steps": ["sanitize", "book_relevance_gate"]},
    }


def qa_envelope(generated: dict) -> dict:
    """Shape expected by frontend QAResponse (result.explanation.core_explanation + result.rag)."""
    answer = str(generated.get("answer", ""))
    rag = generated.get("rag") or {}
    suggestions = generated.get("suggestions")
    if not isinstance(suggestions, list):
        suggestions = []
    return {
        "status": "ok",
        "intent": "qa_rag",
        "result": {
            "status": "ok",
            "explanation": {
                "core_explanation": answer,
            },
            "rag": rag,
            "suggestions": [str(s).strip() for s in suggestions if str(s).strip()][:3],
        },
        "routing": {"steps": ["sanitize", "rag_retrieve", "qa_generator", "qa_validator"]},
    }


def build_failure_context(questions: list[dict], answer_map: dict[int, int]) -> str:
    lines: list[str] = []
    for idx, q in enumerate(questions):
        if idx not in answer_map or not isinstance(q, dict):
            continue
        choices = q.get("choices") or []
        if not isinstance(choices, list):
            continue
        ci = answer_map[idx]
        if not isinstance(ci, int) or ci < 0 or ci >= len(choices):
            continue
        selected = str(choices[ci]).strip()
        correct = str(q.get("correct_answer") or "").strip()
        if selected == correct:
            continue
        q_text = str(q.get("question") or "").strip()
        concept = str(q.get("concept") or "").strip()
        lines.append(f"- Q{idx + 1}: {q_text}")
        if concept:
            lines.append(f"  Concept: {concept}")
        lines.append(f"  Student selected: {selected}")
        lines.append(f"  Correct answer: {correct}")
        lines.append("  Remediation focus: explain why selected is tempting but wrong, then show the correct reasoning.")
    return "\n".join(lines[:40])
