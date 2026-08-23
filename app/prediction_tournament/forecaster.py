from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, Field

from app.config.settings import ForecasterConfig, TournamentYamlConfig
from app.prediction_tournament.llm import TournamentLLM, load_prompt
from app.prediction_tournament.models import ForecastQuestion, ForecasterOutput, RawPrediction, deadline_from_horizon
from app.prediction_tournament.researcher import ResearchContext, format_evidence_for_prompt
from app.utils.logging import get_logger

log = get_logger("forecaster")


class ForecasterResponse(BaseModel):
    predictions: list[RawPrediction] = Field(default_factory=list)


def _render_prompt(
    template: str,
    *,
    role: str,
    focus: list[str],
    question: ForecastQuestion,
    evidence: ResearchContext,
    predictions_count: int,
) -> str:
    return (
        template.replace("{{ROLE}}", role)
        .replace("{{FOCUS}}", "\n".join(f"- {f}" for f in focus))
        .replace("{{QUESTION}}", question.question)
        .replace("{{HORIZON_YEARS}}", str(question.horizon_years))
        .replace("{{DEADLINE}}", question.default_deadline())
        .replace("{{EVIDENCE}}", format_evidence_for_prompt(evidence))
        .replace("{{PREDICTIONS_COUNT}}", str(predictions_count))
    )


def run_forecaster(
    forecaster: ForecasterConfig,
    question: ForecastQuestion,
    evidence: ResearchContext,
    llm: TournamentLLM,
    config: TournamentYamlConfig,
) -> ForecasterOutput:
    log.stage(f"forecaster starting: {forecaster.name}", id=forecaster.id)
    template = load_prompt("forecast")
    system = (
        "You are a rigorous technology forecaster. Return valid JSON only. "
        "Never fabricate citations or statistics."
    )
    user = _render_prompt(
        template,
        role=forecaster.role,
        focus=forecaster.focus,
        question=question,
        evidence=evidence,
        predictions_count=config.predictions_each,
    )

    f_llm = TournamentLLM(
        provider=forecaster.provider or llm.provider,
        model=forecaster.model or llm.model,
        temperature=llm.temperature,
    )

    try:
        response = f_llm.complete_model(system, user, ForecasterResponse)
        valid: list[RawPrediction] = []
        for pred in response.predictions[: config.cost_controls.get("max_predictions_per_forecaster", 10)]:
            if pred.is_vague():
                log.warning(f"vague prediction rejected: {pred.title}")
                continue
            if not pred.evaluation_deadline:
                pred.evaluation_deadline = deadline_from_horizon(pred.time_horizon, question.horizon_years)
            valid.append(pred)
        log.stage(f"forecaster complete: {forecaster.name}", predictions=len(valid))
        return ForecasterOutput(
            forecaster_id=forecaster.id,
            forecaster_name=forecaster.name,
            predictions=valid,
            success=True,
            model=f_llm.model,
            temperature=f_llm.temperature,
        )
    except Exception as exc:
        log.exception(f"forecaster failed: {forecaster.name}")
        return ForecasterOutput(
            forecaster_id=forecaster.id,
            forecaster_name=forecaster.name,
            predictions=[],
            success=False,
            error=str(exc),
            model=f_llm.model,
        )


def run_all_forecasters(
    forecasters: list[ForecasterConfig],
    question: ForecastQuestion,
    evidence: ResearchContext,
    llm: TournamentLLM,
    config: TournamentYamlConfig,
) -> list[ForecasterOutput]:
    results: list[ForecasterOutput] = []
    for forecaster in forecasters:
        # Independent calls — each forecaster runs separately
        results.append(run_forecaster(forecaster, question, evidence, llm, config))
    return results
