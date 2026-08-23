from __future__ import annotations

import json

from app.prediction_tournament.llm import TournamentLLM, load_prompt
from app.prediction_tournament.models import ChallengeResult, RawPrediction
from app.utils.logging import get_logger

log = get_logger("challenger")


def challenge_prediction(prediction: RawPrediction, llm: TournamentLLM) -> ChallengeResult:
    template = load_prompt("challenge")
    user = (
        template.replace("{{TITLE}}", prediction.title)
        .replace("{{STATEMENT}}", prediction.prediction_statement)
        .replace("{{CATEGORY}}", prediction.category)
        .replace("{{DEADLINE}}", prediction.evaluation_deadline)
        .replace("{{SUCCESS_CRITERIA}}", json.dumps(prediction.measurable_success_criteria))
        .replace("{{FAILURE_CRITERIA}}", json.dumps(prediction.failure_criteria))
        .replace("{{CONFIDENCE}}", str(prediction.confidence_probability))
        .replace("{{EVIDENCE_FOR}}", json.dumps(prediction.evidence_supporting))
        .replace("{{EVIDENCE_AGAINST}}", json.dumps(prediction.evidence_against))
        .replace("{{ASSUMPTIONS}}", json.dumps(prediction.key_assumptions))
    )
    system = "You are an adversarial but rational prediction challenger. Return valid JSON only."
    log.stage(f"challenging prediction: {prediction.title}")
    return llm.complete_model(system, user, ChallengeResult)
