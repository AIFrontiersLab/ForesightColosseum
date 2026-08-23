from __future__ import annotations

import json

from app.prediction_tournament.llm import TournamentLLM, load_prompt
from app.prediction_tournament.models import ChallengeResult, JudgeReview, RawPrediction, RebuttalResult
from app.utils.logging import get_logger

log = get_logger("judge")


def judge_prediction(
    prediction: RawPrediction,
    *,
    challenge: ChallengeResult,
    rebuttal: RebuttalResult,
    llm: TournamentLLM,
) -> JudgeReview:
    template = load_prompt("judge")
    record = {
        "prediction": prediction.model_dump(),
        "challenge": challenge.model_dump(),
        "rebuttal": rebuttal.model_dump(),
    }
    user = template.replace("{{PREDICTION_RECORD}}", json.dumps(record, indent=2))
    system = "You are an independent tournament judge. Return valid JSON only."
    log.stage(f"judging prediction: {prediction.title}")
    review = llm.complete_model(system, user, JudgeReview)
    return review.finalize()
