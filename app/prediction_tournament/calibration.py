from __future__ import annotations

from app.prediction_tournament.models import (
    ChallengeResult,
    JudgeReview,
    RawPrediction,
    RebuttalAction,
    RebuttalResult,
    compute_calibrated_confidence,
)


def challenger_adjusted_confidence(
    forecaster_confidence: float,
    challenge: ChallengeResult,
) -> float:
    adjusted = forecaster_confidence + challenge.recommended_confidence_adjustment
    # Stronger challenges pull confidence down further
    strength_factor = (challenge.challenge_strength - 5) * 0.01
    adjusted -= strength_factor
    return max(0.0, min(1.0, adjusted))


def apply_rebuttal_confidence(
    original_confidence: float,
    challenger_adj: float,
    rebuttal: RebuttalResult,
) -> float:
    if rebuttal.action == RebuttalAction.WITHDRAW:
        return 0.0
    return rebuttal.final_confidence


def resolve_final_prediction(
    original: RawPrediction,
    rebuttal: RebuttalResult,
) -> RawPrediction:
    if rebuttal.action == RebuttalAction.MODIFY and rebuttal.final_prediction:
        return rebuttal.final_prediction
    return original


def calibrate_prediction(
    original: RawPrediction,
    challenge: ChallengeResult,
    rebuttal: RebuttalResult,
    judge: JudgeReview,
    weights: dict[str, float] | None = None,
) -> tuple[float, float, float, float]:
    forecaster_conf = original.confidence_probability
    challenger_adj = challenger_adjusted_confidence(forecaster_conf, challenge)
    if rebuttal.action != RebuttalAction.DEFEND:
        challenger_adj = apply_rebuttal_confidence(forecaster_conf, challenger_adj, rebuttal)
    judge_conf = judge.judge_probability
    final = compute_calibrated_confidence(forecaster_conf, challenger_adj, judge_conf, weights)
    return forecaster_conf, challenger_adj, judge_conf, final
