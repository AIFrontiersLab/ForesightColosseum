from __future__ import annotations

import json
from pathlib import Path

from app.prediction_tournament.models import (
    ConsensusLevel,
    ForecasterScore,
    LockedPrediction,
    PredictionState,
    compute_brier_score,
    outcome_value,
)
from app.prediction_tournament.prediction_store import PredictionStore
from app.utils.logging import get_logger

log = get_logger("scorecard")

RESOLVED_STATES = {
    PredictionState.TRUE,
    PredictionState.FALSE,
    PredictionState.PARTIALLY_TRUE,
    PredictionState.INCONCLUSIVE,
}


def compute_forecaster_scores(
    predictions: list[LockedPrediction],
    partial_values: dict[str, float] | None = None,
) -> list[ForecasterScore]:
    by_forecaster: dict[str, list[LockedPrediction]] = {}
    for pred in predictions:
        by_forecaster.setdefault(pred.forecaster_id, []).append(pred)

    scores: list[ForecasterScore] = []
    for fid, preds in by_forecaster.items():
        resolved = [p for p in preds if p.state in RESOLVED_STATES]
        brier_scores: list[float] = []
        correct = incorrect = partial = 0
        high_conf_success = high_conf_fail = low_conf_success = 0

        for p in resolved:
            ov = outcome_value(p.state, partial_values)
            if ov is None:
                continue
            brier_scores.append(compute_brier_score(p.final_calibrated_confidence, ov))
            if p.state == PredictionState.TRUE:
                correct += 1
                if p.final_calibrated_confidence >= 0.7:
                    high_conf_success += 1
                elif p.final_calibrated_confidence < 0.4:
                    low_conf_success += 1
            elif p.state == PredictionState.FALSE:
                incorrect += 1
                if p.final_calibrated_confidence >= 0.7:
                    high_conf_fail += 1
            elif p.state == PredictionState.PARTIALLY_TRUE:
                partial += 1

        avg_conf = sum(p.final_calibrated_confidence for p in preds) / len(preds) if preds else 0.0
        avg_quality = sum(p.prediction_quality_score for p in preds) / len(preds) if preds else 0.0
        accuracy = correct / len(resolved) if resolved else 0.0
        avg_brier = sum(brier_scores) / len(brier_scores) if brier_scores else None

        scores.append(
            ForecasterScore(
                forecaster_id=fid,
                forecaster_name=preds[0].forecaster_name if preds else fid,
                predictions_made=len(preds),
                predictions_resolved=len(resolved),
                correct=correct,
                incorrect=incorrect,
                partially_correct=partial,
                accuracy=accuracy,
                average_confidence=avg_conf,
                brier_score=avg_brier,
                calibration_error=avg_brier,
                high_confidence_successes=high_conf_success,
                high_confidence_failures=high_conf_fail,
                low_confidence_successes=low_conf_success,
                novel_predictions_true=sum(
                    1
                    for p in resolved
                    if p.consensus_level == ConsensusLevel.CONTRARIAN and p.state == PredictionState.TRUE
                ),
                consensus_predictions=sum(1 for p in preds if p.consensus_level == ConsensusLevel.HIGH),
                contrarian_predictions=sum(1 for p in preds if p.consensus_level == ConsensusLevel.CONTRARIAN),
                average_prediction_quality=avg_quality,
            )
        )

    return sorted(scores, key=lambda s: s.brier_score if s.brier_score is not None else 999)


def generate_leaderboard_markdown(scores: list[ForecasterScore]) -> str:
    lines = [
        "# TECHNOLOGY PREDICTION TOURNAMENT — LEADERBOARD",
        "",
        "Forecaster           Brier      Accuracy    Calibration",
        "-------------------------------------------------------",
    ]
    for s in scores:
        brier = f"{s.brier_score:.2f}" if s.brier_score is not None else "N/A"
        cal = "Good" if s.brier_score is not None and s.brier_score < 0.20 else "Fair" if s.brier_score else "Pending"
        lines.append(
            f"{s.forecaster_name:<20} {brier:<10} {s.accuracy:.0%}          {cal}"
        )
    return "\n".join(lines)


def export_scorecard(store: PredictionStore, partial_values: dict[str, float] | None = None) -> Path:
    predictions = store.list_predictions()
    scores = compute_forecaster_scores(predictions, partial_values)
    for score in scores:
        store.save_forecaster_score(score)

    data = {
        "leaderboard": [s.model_dump() for s in scores],
        "predictions_total": len(predictions),
        "predictions_resolved": sum(1 for p in predictions if p.state in RESOLVED_STATES),
    }
    path = store.data_dir / "scorecard.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    md_path = store.data_dir / "leaderboard.md"
    md_path.write_text(generate_leaderboard_markdown(scores), encoding="utf-8")
    log.stage("scorecard exported", path=str(path))
    return path
