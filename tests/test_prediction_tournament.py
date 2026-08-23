from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config.settings import Settings, clear_settings_cache
from app.prediction_tournament.calibration import calibrate_prediction, challenger_adjusted_confidence
from app.prediction_tournament.consensus import cluster_predictions, prediction_similarity
from app.prediction_tournament.models import (
    ChallengeResult,
    ConsensusLevel,
    ForecasterOutput,
    JudgeReview,
    JudgeScores,
    LockedPrediction,
    PredictionState,
    RawPrediction,
    RebuttalAction,
    RebuttalResult,
    classify_consensus,
    compute_brier_score,
    compute_calibrated_confidence,
)
from app.prediction_tournament.prediction_store import PredictionStore
from app.prediction_tournament.scorecard import compute_forecaster_scores


@pytest.fixture
def tmp_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    clear_settings_cache()
    monkeypatch.setenv("PREDICTION_TOURNAMENT_DB", str(tmp_path / "data" / "tournament.db"))
    monkeypatch.setenv("PREDICTION_TOURNAMENT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PREDICTION_TOURNAMENT_OUTPUT_DIR", str(tmp_path / "outputs"))
    clear_settings_cache()
    return Settings(base_dir=tmp_path)


def _raw_prediction(**overrides) -> RawPrediction:
    base = {
        "title": "Agent Identity Infrastructure",
        "prediction_statement": "By 2028, agent identity becomes an enterprise category.",
        "category": "Agent Identity",
        "evaluation_deadline": "2028-12-31",
        "measurable_success_criteria": ["Two cloud providers offer agent identity", "10 OSS projects"],
        "failure_criteria": ["Fewer than two conditions met"],
        "confidence_probability": 0.72,
    }
    base.update(overrides)
    return RawPrediction(**base)


def test_prediction_schema_validation():
    pred = _raw_prediction()
    assert pred.confidence_probability == pytest.approx(0.72)
    assert not pred.is_vague()


def test_vague_prediction_detection():
    vague = _raw_prediction(
        title="AI agents will become important",
        prediction_statement="AI agents will become mainstream.",
        measurable_success_criteria=[],
    )
    assert vague.is_vague()


def test_confidence_normalization():
    pred = RawPrediction(
        title="Test",
        prediction_statement="Test statement with criteria.",
        category="RAG",
        confidence_probability="80%",
        measurable_success_criteria=["criterion 1", "criterion 2"],
    )
    assert pred.confidence_probability == pytest.approx(0.80)


def test_duplicate_prediction_clustering():
    outputs = [
        ForecasterOutput(
            forecaster_id="architect",
            forecaster_name="Architect",
            predictions=[_raw_prediction(title="Agent identity becomes infrastructure")],
        ),
        ForecasterOutput(
            forecaster_id="enterprise",
            forecaster_name="Enterprise",
            predictions=[
                _raw_prediction(
                    title="Enterprise IAM expands to autonomous agents",
                    prediction_statement="By 2028, enterprise IAM expands to autonomous agents with delegated auth.",
                )
            ],
        ),
    ]
    clusters = cluster_predictions(outputs, threshold=0.35)
    assert len(clusters) >= 1
    assert clusters[0].forecaster_count >= 1


def test_prediction_similarity():
    a = _raw_prediction(title="MCP becomes mainstream integration layer")
    b = _raw_prediction(title="MCP adoption as enterprise integration standard")
    assert prediction_similarity(a, b) > 0.4


def test_confidence_calibration_formula():
    result = compute_calibrated_confidence(0.8, 0.6, 0.7)
    expected = 0.50 * 0.8 + 0.20 * 0.6 + 0.30 * 0.7
    assert result == pytest.approx(expected)


def test_challenger_adjusted_confidence():
    challenge = ChallengeResult(challenge_strength=8, recommended_confidence_adjustment=-0.10)
    adj = challenger_adjusted_confidence(0.75, challenge)
    assert adj < 0.75


def test_full_calibration_pipeline():
    original = _raw_prediction()
    challenge = ChallengeResult(challenge_strength=6, recommended_confidence_adjustment=-0.05)
    rebuttal = RebuttalResult(action=RebuttalAction.LOWER, final_confidence=0.65, reasoning="Valid concerns")
    judge = JudgeReview(
        scores=JudgeScores(
            specificity=8,
            falsifiability=9,
            evidence_quality=6,
            reasoning_quality=7,
            novelty=7,
            strategic_importance=8,
            measurability=9,
            time_horizon_clarity=8,
        ),
        judge_probability=0.68,
    ).finalize()
    f, c, j, final = calibrate_prediction(original, challenge, rebuttal, judge)
    assert final > 0


def test_prediction_locking_and_hash_integrity(tmp_settings: Settings):
    store = PredictionStore(settings=tmp_settings)
    tournament_id = store.create_tournament(
        __import__("app.prediction_tournament.models", fromlist=["ForecastQuestion"]).ForecastQuestion(
            question="Test?"
        ),
        config_json={},
        output_dir="/tmp/out",
    )
    raw = _raw_prediction()
    pred = LockedPrediction(
        prediction_id=store.next_prediction_id(),
        tournament_id=tournament_id,
        forecaster_id="architect",
        forecaster_name="Architect",
        title=raw.title,
        prediction_statement=raw.prediction_statement,
        category=raw.category,
        time_horizon="36 months",
        evaluation_deadline="2028-12-31",
        measurable_success_criteria=raw.measurable_success_criteria,
        failure_criteria=raw.failure_criteria,
        original_confidence=0.72,
        challenger_adjusted_confidence=0.65,
        judge_confidence=0.68,
        final_calibrated_confidence=0.69,
        original_prediction=raw,
    )
    store.lock_prediction(pred)
    assert store.verify_hash_integrity(pred.prediction_id)


def test_revision_on_state_change(tmp_settings: Settings):
    store = PredictionStore(settings=tmp_settings)
    tournament_id = store.create_tournament(
        __import__("app.prediction_tournament.models", fromlist=["ForecastQuestion"]).ForecastQuestion(
            question="Test?"
        ),
        config_json={},
        output_dir="/tmp/out",
    )
    raw = _raw_prediction()
    pred_id = store.next_prediction_id()
    pred = LockedPrediction(
        prediction_id=pred_id,
        tournament_id=tournament_id,
        forecaster_id="architect",
        forecaster_name="Architect",
        title=raw.title,
        prediction_statement=raw.prediction_statement,
        category=raw.category,
        time_horizon="36 months",
        evaluation_deadline="2028-12-31",
        measurable_success_criteria=raw.measurable_success_criteria,
        failure_criteria=raw.failure_criteria,
        original_confidence=0.72,
        challenger_adjusted_confidence=0.65,
        judge_confidence=0.68,
        final_calibrated_confidence=0.69,
        original_prediction=raw,
    )
    store.lock_prediction(pred)
    store.update_prediction_state(pred_id, PredictionState.EARLY_SIGNAL, reasoning="Signal detected")
    loaded = store.get_prediction(pred_id)
    assert loaded.state == PredictionState.EARLY_SIGNAL


def test_brier_score_calculation():
    assert compute_brier_score(0.8, 1.0) == pytest.approx(0.04)
    assert compute_brier_score(0.8, 0.0) == pytest.approx(0.64)


def test_consensus_classification():
    assert classify_consensus(5) == ConsensusLevel.HIGH
    assert classify_consensus(4) == ConsensusLevel.MODERATE
    assert classify_consensus(2) == ConsensusLevel.LOW
    assert classify_consensus(1) == ConsensusLevel.CONTRARIAN


def test_scorecard_ranking():
    raw = _raw_prediction()
    preds = [
        LockedPrediction(
            prediction_id="PRED-2026-0001",
            tournament_id="TOUR-2026-0001",
            forecaster_id="architect",
            forecaster_name="Architect",
            title=raw.title,
            prediction_statement=raw.prediction_statement,
            category=raw.category,
            time_horizon="36 months",
            evaluation_deadline="2028-12-31",
            measurable_success_criteria=raw.measurable_success_criteria,
            failure_criteria=raw.failure_criteria,
            original_confidence=0.9,
            challenger_adjusted_confidence=0.85,
            judge_confidence=0.88,
            final_calibrated_confidence=0.88,
            original_prediction=raw,
            state=PredictionState.TRUE,
        ),
        LockedPrediction(
            prediction_id="PRED-2026-0002",
            tournament_id="TOUR-2026-0001",
            forecaster_id="contrarian",
            forecaster_name="Contrarian",
            title="Local AI inference",
            prediction_statement="Local inference becomes enterprise standard.",
            category="Local AI",
            time_horizon="36 months",
            evaluation_deadline="2028-12-31",
            measurable_success_criteria=["c1", "c2"],
            failure_criteria=["f1"],
            original_confidence=0.6,
            challenger_adjusted_confidence=0.5,
            judge_confidence=0.55,
            final_calibrated_confidence=0.55,
            original_prediction=_raw_prediction(title="Local AI inference"),
            state=PredictionState.FALSE,
        ),
    ]
    scores = compute_forecaster_scores(preds)
    assert len(scores) == 2
    assert scores[0].brier_score is not None


def test_outcome_state_transitions():
    from app.prediction_tournament.models import outcome_value

    assert outcome_value(PredictionState.TRUE) == 1.0
    assert outcome_value(PredictionState.PARTIALLY_TRUE) == 0.5
    assert outcome_value(PredictionState.FALSE) == 0.0
    assert outcome_value(PredictionState.OPEN) is None


def test_verification_idempotency(tmp_settings: Settings, monkeypatch: pytest.MonkeyPatch):
    from app.prediction_tournament.verifier import run_verification

    result1 = run_verification(dry_run=True, settings=tmp_settings)
    result2 = run_verification(dry_run=True, settings=tmp_settings)
    assert result1["status"] == "DRY_RUN"
    assert result2["status"] == "DRY_RUN"


def test_partial_tournament_recovery():
    outputs = [
        ForecasterOutput(forecaster_id="a", forecaster_name="A", predictions=[_raw_prediction()], success=True),
        ForecasterOutput(forecaster_id="b", forecaster_name="B", predictions=[], success=False, error="timeout"),
        ForecasterOutput(forecaster_id="c", forecaster_name="C", predictions=[_raw_prediction()], success=True),
    ]
    successful = [o for o in outputs if o.success]
    assert len(successful) == 2
    assert sum(len(o.predictions) for o in successful) == 2


def test_cli_dry_run(monkeypatch: pytest.MonkeyPatch):
    from app.prediction_tournament.__main__ import main

    clear_settings_cache()
    monkeypatch.setenv("PREDICTION_TOURNAMENT_ENABLED", "true")
    clear_settings_cache()
    assert main(["run", "--dry-run"]) == 0
