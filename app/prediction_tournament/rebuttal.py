from __future__ import annotations

import json

from app.prediction_tournament.llm import TournamentLLM, load_prompt
from app.prediction_tournament.models import ChallengeResult, RawPrediction, RebuttalResult
from app.utils.logging import get_logger

log = get_logger("rebuttal")


def run_rebuttal(
    original: RawPrediction,
    challenge: ChallengeResult,
    llm: TournamentLLM,
) -> RebuttalResult:
    template = load_prompt("rebuttal")
    user = template.replace("{{ORIGINAL_PREDICTION}}", original.model_dump_json(indent=2)).replace(
        "{{CHALLENGE}}", challenge.model_dump_json(indent=2)
    )
    system = "You are the original forecaster responding to a challenge. Return valid JSON only."
    log.stage(f"rebuttal for: {original.title}")
    result = llm.complete_model(system, user, RebuttalResult)
    result.final_confidence = max(0.0, min(1.0, result.final_confidence))
    return result
