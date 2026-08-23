from __future__ import annotations

import argparse
import json
import sys

from app.config.settings import ensure_directories, get_settings
from app.prediction_tournament.orchestrator import run_tournament
from app.prediction_tournament.prediction_store import PredictionStore
from app.prediction_tournament.scorecard import export_scorecard, generate_leaderboard_markdown
from app.prediction_tournament.verifier import run_verification
from app.utils.logging import setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Technology Prediction Tournament")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run a prediction tournament")
    run_p.add_argument("--question", help="Override forecasting question")
    run_p.add_argument("--dry-run", action="store_true", help="Validate without LLM calls")
    run_p.add_argument("--date", help="Output date folder (YYYY-MM-DD)")

    verify_p = sub.add_parser("verify", help="Run monthly verification cycle")
    verify_p.add_argument("--dry-run", action="store_true")

    sub.add_parser("scorecard", help="Generate forecaster scorecard")

    show_p = sub.add_parser("show", help="Show a locked prediction")
    show_p.add_argument("prediction_id", help="Prediction ID e.g. PRED-2026-0001")

    # Backward-compatible top-level flags
    parser.add_argument("--question", help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--date", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = get_settings()
    setup_logging(settings.log_level)
    ensure_directories(settings)

    command = args.command
    if not command:
        command = "run"

    try:
        if command == "run":
            result = run_tournament(
                question=getattr(args, "question", None),
                dry_run=getattr(args, "dry_run", False),
                run_date=getattr(args, "date", None),
                settings=settings,
            )
            if result.dry_run:
                print("🔮 TECHNOLOGY PREDICTION TOURNAMENT — DRY RUN")
                print("")
                print(f"Question: {result.question.question}")
                print(f"Output path: {result.output_dir}")
                print(result.message)
                return 0
            if result.status == "DISABLED":
                print(result.message)
                return 0
            if result.status != "SUCCESS":
                print(f"Tournament failed: {result.message}")
                return 1
            print(result.morning_summary)
            return 0

        if command == "verify":
            result = run_verification(dry_run=getattr(args, "dry_run", False), settings=settings)
            print(json.dumps(result, indent=2))
            return 0 if result.get("status") != "ERROR" else 1

        if command == "scorecard":
            store = PredictionStore(settings=settings)
            path = export_scorecard(store)
            leaderboard_path = store.data_dir / "leaderboard.md"
            if leaderboard_path.exists():
                print(leaderboard_path.read_text(encoding="utf-8"))
            else:
                from app.prediction_tournament.scorecard import compute_forecaster_scores

                scores = compute_forecaster_scores(store.list_predictions())
                print(generate_leaderboard_markdown(scores))
            print(f"\nScorecard: {path}")
            return 0

        if command == "show":
            store = PredictionStore(settings=settings)
            pred = store.get_prediction(args.prediction_id)
            if not pred:
                print(f"Prediction not found: {args.prediction_id}", file=sys.stderr)
                return 1
            print(json.dumps(pred.model_dump(mode="json"), indent=2))
            print(f"\nHash integrity: {store.verify_hash_integrity(args.prediction_id)}")
            return 0

    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
