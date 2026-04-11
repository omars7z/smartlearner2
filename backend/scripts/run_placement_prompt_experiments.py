"""
Run placement generator for each prompt variant in a JSON manifest and save results under experiments/.

From the backend directory:
  python scripts/run_placement_prompt_experiments.py
  python scripts/run_placement_prompt_experiments.py --manifest experiments/placement_prompts/my_manifest.json

User prompt template: Python str.format fields — lvl, chunk_text, rubric_concept, slot (1-based), question_count.
Use {{ and }} for literal braces in the template.

Optional rubric evaluation (LLM scores criteria in experiments/placement_prompts/evaluation_rubric.json):
  python scripts/run_placement_prompt_experiments.py --evaluate
  or set \"run_rubric_eval\": true in the manifest. Use --no-evaluate to force off.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

_spec = importlib.util.spec_from_file_location(
    "placement_rubric_evaluator",
    SCRIPT_DIR / "placement_rubric_evaluator.py",
)
assert _spec and _spec.loader
_rubric_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rubric_mod)
evaluate_placement_questions = _rubric_mod.evaluate_placement_questions
load_evaluation_rubric = _rubric_mod.load_evaluation_rubric

from app.core.placement_rubric import concepts_for_level, normalize_level
from app.services.agents import (
    AgentValidationError,
    PlacementGeneratorAgent,
    PlacementValidatorAgent,
)
from app.services.llm_client import LLMClient
from app.services.rag_service import RAGService


def _load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("Manifest must be a JSON object")
    if "variants" not in data or not isinstance(data["variants"], list) or not data["variants"]:
        raise SystemExit("Manifest must contain a non-empty \"variants\" array")
    return data


def _variant_prompts(entry: dict) -> tuple[str | None, str | None]:
    sys_p = entry.get("system_prompt")
    user_tpl = entry.get("user_prompt_template")
    if sys_p is not None and not isinstance(sys_p, str):
        raise SystemExit(f"Variant {entry.get('id')}: system_prompt must be a string or omitted")
    if user_tpl is not None and not isinstance(user_tpl, str):
        raise SystemExit(f"Variant {entry.get('id')}: user_prompt_template must be a string or omitted")
    s = sys_p.strip() if isinstance(sys_p, str) and sys_p.strip() else None
    u = user_tpl.strip() if isinstance(user_tpl, str) and user_tpl.strip() else None
    return s, u


def main() -> None:
    parser = argparse.ArgumentParser(description="Save placement MCQ runs per prompt variant for comparison.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=BACKEND_ROOT / "experiments" / "placement_prompts" / "manifest.json",
        help="JSON manifest path (copy manifest.example.json to manifest.json and edit)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=BACKEND_ROOT / "experiments" / "placement_prompts" / "runs",
        help="Directory for output JSON files",
    )
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="Run LLM rubric scoring (see experiments/placement_prompts/evaluation_rubric.json); uses extra API calls",
    )
    parser.add_argument(
        "--no-evaluate",
        action="store_true",
        help="Disable rubric evaluation even if manifest sets run_rubric_eval",
    )
    parser.add_argument(
        "--rubric-path",
        type=Path,
        default=BACKEND_ROOT / "experiments" / "placement_prompts" / "evaluation_rubric.json",
        help="JSON file defining criteria (id, name, description) and scale_max",
    )
    args = parser.parse_args()

    manifest_path: Path = args.manifest
    if not manifest_path.is_file():
        raise SystemExit(
            f"Manifest not found: {manifest_path}\n"
            f"Copy {manifest_path.parent / 'manifest.example.json'} to manifest.json and edit."
        )

    manifest = _load_manifest(manifest_path)
    level_raw = manifest.get("level") or "beginner"
    lvl = normalize_level(str(level_raw))
    run_validator = bool(manifest.get("run_validator", True))
    forced = concepts_for_level(lvl)
    question_count = len(forced)

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    gen = PlacementGeneratorAgent(LLMClient(), RAGService())
    val = PlacementValidatorAgent(LLMClient(use_validator_key=True)) if run_validator else None

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    rubric_path: Path = args.rubric_path
    do_rubric_eval = (bool(args.evaluate) or bool(manifest.get("run_rubric_eval"))) and not bool(
        args.no_evaluate
    )
    rubric_doc: dict | None = None
    if do_rubric_eval:
        if not rubric_path.is_file():
            print(f"Warning: rubric file missing ({rubric_path}); skipping rubric evaluation.")
            do_rubric_eval = False
        else:
            try:
                rubric_doc = load_evaluation_rubric(rubric_path)
            except Exception as exc:
                print(f"Warning: could not load rubric ({exc}); skipping rubric evaluation.")
                do_rubric_eval = False

    eval_llm = LLMClient() if do_rubric_eval else None

    for entry in manifest["variants"]:
        if not isinstance(entry, dict):
            continue
        vid = str(entry.get("id") or "unnamed").strip() or "unnamed"
        sys_override, user_override = _variant_prompts(entry)

        record: dict = {
            "variant_id": vid,
            "note": entry.get("note"),
            "level": lvl,
            "question_count": question_count,
            "manifest_path": str(manifest_path.as_posix()),
            "run_validator": run_validator,
            "system_prompt_override": sys_override,
            "user_prompt_template_override": user_override,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "rubric_evaluation_path": str(rubric_path.as_posix()) if do_rubric_eval else None,
        }

        try:
            raw = gen.generate(
                lvl,
                question_count,
                system_prompt=sys_override,
                user_prompt_template=user_override,
            )
            record["generation"] = raw
            record["generation_error"] = None
        except Exception as exc:
            record["generation"] = None
            record["generation_error"] = f"{type(exc).__name__}: {exc}"
            out_path = out_dir / f"{stamp}_{vid}.json"
            out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Wrote (generation failed): {out_path}")
            continue

        if val is not None:
            try:
                validated = val.validate(raw, lvl, question_count)
                record["validation"] = validated
                record["validation_error"] = None
            except AgentValidationError as exc:
                record["validation"] = None
                record["validation_error"] = str(exc)
        else:
            record["validation"] = None
            record["validation_error"] = "skipped"

        record["rubric_evaluation"] = None
        if do_rubric_eval and eval_llm is not None and rubric_doc is not None:
            payload = record.get("validation") or record.get("generation")
            qlist = payload.get("questions") if isinstance(payload, dict) else None
            if isinstance(qlist, list) and qlist:
                try:
                    record["rubric_evaluation"] = evaluate_placement_questions(
                        eval_llm,
                        level=lvl,
                        questions=qlist,
                        rubric=rubric_doc,
                    )
                except Exception as exc:
                    record["rubric_evaluation"] = {"error": f"{type(exc).__name__}: {exc}"}

        out_path = out_dir / f"{stamp}_{vid}.json"
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
