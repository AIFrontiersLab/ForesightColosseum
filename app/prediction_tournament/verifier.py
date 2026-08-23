from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from app.config.settings import Settings, get_settings, load_tournament_config
from app.prediction_tournament.llm import TournamentLLM, load_prompt
from app.prediction_tournament.models import PredictionState, VerificationResult, compute_brier_score, outcome_value
from app.prediction_tournament.prediction_store import PredictionStore
from app.prediction_tournament.researcher import gather_evidence
from app.prediction_tournament.models import ForecastQuestion
from app.prediction_tournament.scorecard import export_scorecard
from app.utils.logging import get_logger

log = get_logger("verifier")

TERMINAL_STATES = {
    PredictionState.TRUE,
    PredictionState.FALSE,
    PredictionState.PARTIALLY_TRUE,
    PredictionState.INCONCLUSIVE,
    PredictionState.EXPIRED,
    PredictionState.WITHDRAWN,
}


def run_verification(
    *,
    dry_run: bool = False,
    settings: Settings | None = None,
) -> dict[str, object]:
    s = settings or get_settings()
    store = PredictionStore(settings=s)
    config = load_tournament_config(s)
    out_dir = s.resolved_output_dir / f"verification-{date.today().isoformat()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    open_predictions = store.list_predictions(open_only=True)
    log.stage("verification starting", open_count=len(open_predictions))

    if dry_run:
        return {
            "status": "DRY_RUN",
            "open_predictions": len(open_predictions),
            "report_path": str(out_dir),
            "message": f"Would verify {len(open_predictions)} open predictions",
        }

    llm = TournamentLLM()
    if not llm.available():
        return {
            "status": "ERROR",
            "message": "No LLM available for verification",
        }

    updated = 0
    results: list[dict] = []
    template = load_prompt("verification")

    for pred in open_predictions:
        if pred.state in TERMINAL_STATES:
            continue

        # Check deadline expiry
        if pred.evaluation_deadline and pred.evaluation_deadline < date.today().isoformat():
            if pred.state not in TERMINAL_STATES:
                store.update_prediction_state(pred.prediction_id, PredictionState.EXPIRED, reasoning="Deadline passed")
                updated += 1
            continue

        evidence_ctx = gather_evidence(
            ForecastQuestion(question=pred.title, horizon_years=3),
            max_sources=config.cost_controls.get("max_verification_searches", 10),
        )
        user = (
            template.replace("{{PREDICTION}}", pred.model_dump_json(indent=2))
            .replace("{{SUCCESS_CRITERIA}}", json.dumps(pred.measurable_success_criteria))
            .replace("{{FAILURE_CRITERIA}}", json.dumps(pred.failure_criteria))
            .replace("{{DEADLINE}}", pred.evaluation_deadline)
            .replace("{{CURRENT_EVIDENCE}}", evidence_ctx.summary)
            .replace("{{PREVIOUS_STATE}}", pred.state.value)
        )
        system = "You are an outcome verification judge. Return valid JSON only. Do not modify the original claim."

        try:
            result = llm.complete_model(system, user, VerificationResult)
        except Exception as exc:
            log.warning(f"verification failed for {pred.prediction_id}: {exc}")
            continue

        if result.state != pred.state:
            ov = outcome_value(result.state, config.partial_outcome_values)
            brier = compute_brier_score(pred.final_calibrated_confidence, ov) if ov is not None else None
            store.update_prediction_state(
                pred.prediction_id,
                result.state,
                reasoning=result.reasoning_summary,
                outcome_value=ov,
                brier=brier,
            )
            updated += 1

        results.append(
            {
                "prediction_id": pred.prediction_id,
                "title": pred.title,
                "previous_state": pred.state.value,
                "new_state": result.state.value,
                "should_close": result.should_close_prediction,
            }
        )

    report_path = out_dir / "verification-report.json"
    report_path.write_text(json.dumps({"results": results, "updated": updated}, indent=2), encoding="utf-8")
    store.record_verification_run(
        predictions_checked=len(open_predictions),
        predictions_updated=updated,
        report_path=str(report_path),
    )
    export_scorecard(store, config.partial_outcome_values)

    monthly_md = out_dir / "monthly-report.md"
    monthly_md.write_text(
        f"# Monthly Verification Report — {date.today().isoformat()}\n\n"
        f"Checked: {len(open_predictions)} | Updated: {updated}\n",
        encoding="utf-8",
    )

    log.stage("verification complete", updated=updated)
    return {
        "status": "SUCCESS",
        "checked": len(open_predictions),
        "updated": updated,
        "report_path": str(report_path),
    }
