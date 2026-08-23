from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class PredictionState(StrEnum):
    OPEN = "OPEN"
    EARLY_SIGNAL = "EARLY_SIGNAL"
    TRENDING_TOWARD_TRUE = "TRENDING_TOWARD_TRUE"
    TRENDING_TOWARD_FALSE = "TRENDING_TOWARD_FALSE"
    TRUE = "TRUE"
    PARTIALLY_TRUE = "PARTIALLY_TRUE"
    FALSE = "FALSE"
    INCONCLUSIVE = "INCONCLUSIVE"
    EXPIRED = "EXPIRED"
    WITHDRAWN = "WITHDRAWN"


class ConsensusLevel(StrEnum):
    HIGH = "HIGH CONSENSUS"
    MODERATE = "MODERATE CONSENSUS"
    LOW = "LOW CONSENSUS"
    CONTRARIAN = "CONTRARIAN"


PREDICTION_CATEGORIES = [
    "Agentic AI",
    "Multi-Agent Systems",
    "Agent Protocols",
    "MCP",
    "Agent-to-Agent Communication",
    "Agent Identity",
    "Agent Security",
    "AI Authorization",
    "Agent Memory",
    "AI Observability",
    "AI Evaluation",
    "AI Governance",
    "AI Runtime Infrastructure",
    "AI Browsers",
    "Computer-Using Agents",
    "Coding Agents",
    "Voice AI",
    "Multimodal AI",
    "RAG",
    "GraphRAG",
    "Knowledge Graphs",
    "Vector Databases",
    "Small Language Models",
    "Local AI",
    "Edge AI",
    "Inference Infrastructure",
    "GPU Infrastructure",
    "Inference Economics",
    "Model Routing",
    "LLM Gateways",
    "Semantic Caching",
    "Prompt Caching",
    "Synthetic Data",
    "AI Hardware",
    "Robotics",
    "Embodied AI",
    "AI Data Platforms",
    "AI Security",
    "Enterprise AI",
    "Open Source AI",
    "AI Developer Tools",
    "AI Standards",
    "AI Regulation Technology",
    "Human-AI Collaboration",
]


class EvidenceItem(BaseModel):
    title: str
    source: str
    url: str = ""
    published_at: str = ""
    summary: str
    relevance: str = ""
    retrieved_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class ForecastQuestion(BaseModel):
    question: str
    horizon_years: int = 3
    evaluation_deadline: str = ""

    def default_deadline(self) -> str:
        if self.evaluation_deadline:
            return self.evaluation_deadline
        year = date.today().year + self.horizon_years
        return f"{year}-12-31"


class RawPrediction(BaseModel):
    title: str
    prediction_statement: str
    category: str
    time_horizon: str = ""
    evaluation_deadline: str = ""
    current_state: str = ""
    expected_future_state: str = ""
    why_it_will_happen: str = ""
    technical_drivers: list[str] = Field(default_factory=list)
    economic_drivers: list[str] = Field(default_factory=list)
    enterprise_drivers: list[str] = Field(default_factory=list)
    developer_ecosystem_drivers: list[str] = Field(default_factory=list)
    evidence_supporting: list[str] = Field(default_factory=list)
    evidence_against: list[str] = Field(default_factory=list)
    key_assumptions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    potential_blockers: list[str] = Field(default_factory=list)
    signals_to_watch: list[str] = Field(default_factory=list)
    measurable_success_criteria: list[str] = Field(default_factory=list)
    failure_criteria: list[str] = Field(default_factory=list)
    confidence_probability: float = Field(ge=0.0, le=1.0)

    @field_validator("confidence_probability", mode="before")
    @classmethod
    def normalize_confidence(cls, value: object) -> float:
        if value is None:
            return 0.5
        if isinstance(value, str):
            value = value.strip().rstrip("%")
            v = float(value)
            return v / 100.0 if v > 1.0 else v
        v = float(value)
        return v / 100.0 if v > 1.0 else v

    def is_vague(self) -> bool:
        vague_patterns = [
            r"\bAI will (get|become) better\b",
            r"\bAI agents will become important\b",
            r"\bRAG will improve\b",
            r"\bAI security will matter\b",
            r"\bMultimodal AI will grow\b",
            r"\bAI agents will become mainstream\b",
        ]
        text = f"{self.title} {self.prediction_statement}".lower()
        if len(self.measurable_success_criteria) < 1:
            return True
        return any(re.search(p, text, re.I) for p in vague_patterns)


class ForecasterOutput(BaseModel):
    forecaster_id: str
    forecaster_name: str
    predictions: list[RawPrediction] = Field(default_factory=list)
    success: bool = True
    error: str = ""
    model: str = ""
    prompt_version: str = "1.0"
    temperature: float = 0.4
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class ChallengeResult(BaseModel):
    challenge_strength: int = Field(ge=1, le=10)
    critical_objections: list[str] = Field(default_factory=list)
    hidden_assumptions: list[str] = Field(default_factory=list)
    competing_outcomes: list[str] = Field(default_factory=list)
    failure_scenarios: list[str] = Field(default_factory=list)
    recommended_confidence_adjustment: float = 0.0


class RebuttalAction(StrEnum):
    DEFEND = "DEFEND"
    MODIFY = "MODIFY"
    LOWER = "LOWER"
    INCREASE = "INCREASE"
    WITHDRAW = "WITHDRAW"


class RebuttalResult(BaseModel):
    action: RebuttalAction
    rebuttal_text: str = ""
    final_prediction: RawPrediction | None = None
    final_confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""


class JudgeScores(BaseModel):
    specificity: float = Field(ge=0, le=10)
    falsifiability: float = Field(ge=0, le=10)
    evidence_quality: float = Field(ge=0, le=10)
    reasoning_quality: float = Field(ge=0, le=10)
    novelty: float = Field(ge=0, le=10)
    strategic_importance: float = Field(ge=0, le=10)
    measurability: float = Field(ge=0, le=10)
    time_horizon_clarity: float = Field(ge=0, le=10)

    @property
    def prediction_quality_score(self) -> float:
        values = [
            self.specificity,
            self.falsifiability,
            self.evidence_quality,
            self.reasoning_quality,
            self.novelty,
            self.strategic_importance,
            self.measurability,
            self.time_horizon_clarity,
        ]
        return sum(values) / len(values)


class JudgeReview(BaseModel):
    scores: JudgeScores
    judge_probability: float = Field(ge=0.0, le=1.0)
    confidence_quality: str = ""
    prediction_quality_score: float = 0.0
    success_criteria_recommendations: list[str] = Field(default_factory=list)
    reasoning_summary: str = ""

    def finalize(self) -> JudgeReview:
        self.prediction_quality_score = self.scores.prediction_quality_score
        return self


class ConsensusCluster(BaseModel):
    cluster_id: str
    representative_title: str
    representative_statement: str
    category: str
    forecaster_ids: list[str] = Field(default_factory=list)
    prediction_ids: list[str] = Field(default_factory=list)
    mean_confidence: float = 0.0
    median_confidence: float = 0.0
    confidence_range: tuple[float, float] = (0.0, 0.0)
    areas_of_agreement: list[str] = Field(default_factory=list)
    areas_of_disagreement: list[str] = Field(default_factory=list)
    consensus_level: ConsensusLevel = ConsensusLevel.CONTRARIAN

    @property
    def forecaster_count(self) -> int:
        return len(self.forecaster_ids)


class LockedPrediction(BaseModel):
    prediction_id: str
    tournament_id: str
    forecaster_id: str
    forecaster_name: str
    cluster_id: str = ""
    consensus_level: ConsensusLevel = ConsensusLevel.CONTRARIAN
    title: str
    prediction_statement: str
    category: str
    time_horizon: str
    evaluation_deadline: str
    current_state: str = ""
    expected_future_state: str = ""
    why_it_will_happen: str = ""
    technical_drivers: list[str] = Field(default_factory=list)
    economic_drivers: list[str] = Field(default_factory=list)
    enterprise_drivers: list[str] = Field(default_factory=list)
    developer_ecosystem_drivers: list[str] = Field(default_factory=list)
    key_assumptions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    potential_blockers: list[str] = Field(default_factory=list)
    signals_to_watch: list[str] = Field(default_factory=list)
    measurable_success_criteria: list[str] = Field(default_factory=list)
    failure_criteria: list[str] = Field(default_factory=list)
    original_confidence: float
    challenger_adjusted_confidence: float
    judge_confidence: float
    final_calibrated_confidence: float
    prediction_quality_score: float = 0.0
    strategic_importance: float = 0.0
    state: PredictionState = PredictionState.OPEN
    original_prediction: RawPrediction
    challenge: ChallengeResult | None = None
    rebuttal: RebuttalResult | None = None
    judge_review: JudgeReview | None = None
    payload_hash: str = ""
    created_at: str = ""
    locked_at: str = ""
    evaluation_start: str = ""
    model: str = ""
    prompt_version: str = ""
    withdrawn: bool = False

    def immutable_payload(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "prediction_statement": self.prediction_statement,
            "category": self.category,
            "evaluation_deadline": self.evaluation_deadline,
            "measurable_success_criteria": self.measurable_success_criteria,
            "failure_criteria": self.failure_criteria,
            "original_confidence": self.original_confidence,
        }

    def compute_hash(self) -> str:
        payload = json.dumps(self.immutable_payload(), sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()


class VerificationResult(BaseModel):
    state: PredictionState
    confidence: float = Field(ge=0.0, le=1.0)
    criteria_met: list[str] = Field(default_factory=list)
    criteria_not_met: list[str] = Field(default_factory=list)
    criteria_uncertain: list[str] = Field(default_factory=list)
    reasoning_summary: str = ""
    should_close_prediction: bool = False
    new_evidence: list[EvidenceItem] = Field(default_factory=list)


class ForecasterScore(BaseModel):
    forecaster_id: str
    forecaster_name: str
    predictions_made: int = 0
    predictions_resolved: int = 0
    correct: int = 0
    incorrect: int = 0
    partially_correct: int = 0
    accuracy: float = 0.0
    average_confidence: float = 0.0
    brier_score: float | None = None
    calibration_error: float | None = None
    high_confidence_successes: int = 0
    high_confidence_failures: int = 0
    low_confidence_successes: int = 0
    novel_predictions_true: int = 0
    consensus_predictions: int = 0
    contrarian_predictions: int = 0
    average_prediction_quality: float = 0.0


class TournamentResult(BaseModel):
    status: str
    tournament_id: str
    question: ForecastQuestion
    output_dir: str
    raw_predictions_count: int = 0
    unique_predictions_count: int = 0
    locked_predictions_count: int = 0
    partial_tournament: bool = False
    failed_forecasters: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    research_available: bool = False
    dry_run: bool = False
    message: str = ""
    morning_summary: str = ""
    highest_confidence_prediction: str = ""
    strongest_consensus_prediction: str = ""
    best_contrarian_prediction: str = ""


def generate_prediction_id(year: int, sequence: int) -> str:
    return f"PRED-{year}-{sequence:04d}"


def generate_tournament_id(year: int, sequence: int) -> str:
    return f"TOUR-{year}-{sequence:04d}"


def classify_consensus(forecaster_count: int, total_forecasters: int = 5) -> ConsensusLevel:
    if forecaster_count >= total_forecasters:
        return ConsensusLevel.HIGH
    if forecaster_count >= 3:
        return ConsensusLevel.MODERATE
    if forecaster_count >= 2:
        return ConsensusLevel.LOW
    return ConsensusLevel.CONTRARIAN


def compute_brier_score(probability: float, outcome_value: float) -> float:
    return (probability - outcome_value) ** 2


def compute_calibrated_confidence(
    forecaster: float,
    challenger_adjusted: float,
    judge: float,
    weights: dict[str, float] | None = None,
) -> float:
    w = weights or {"forecaster": 0.50, "challenger": 0.20, "judge": 0.30}
    total = sum(w.values()) or 1.0
    result = (
        forecaster * w.get("forecaster", 0.5)
        + challenger_adjusted * w.get("challenger", 0.2)
        + judge * w.get("judge", 0.3)
    ) / total
    return max(0.0, min(1.0, result))


def outcome_value(state: PredictionState, partial_values: dict[str, float] | None = None) -> float | None:
    mapping = partial_values or {"TRUE": 1.0, "PARTIALLY_TRUE": 0.5, "FALSE": 0.0}
    if state == PredictionState.TRUE:
        return mapping.get("TRUE", 1.0)
    if state == PredictionState.PARTIALLY_TRUE:
        return mapping.get("PARTIALLY_TRUE", 0.5)
    if state == PredictionState.FALSE:
        return mapping.get("FALSE", 0.0)
    return None


def deadline_from_horizon(horizon: str, default_years: int = 3) -> str:
    if re.match(r"\d{4}-\d{2}-\d{2}", horizon or ""):
        return horizon
    today = date.today()
    for months in (6, 12, 24, 36, 60):
        if str(months) in horizon or f"{months // 12}" in horizon:
            return (today + timedelta(days=months * 30)).isoformat()
    return f"{today.year + default_years}-12-31"
