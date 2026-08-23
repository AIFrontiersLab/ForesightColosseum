from __future__ import annotations

import uuid
from statistics import median

from rapidfuzz import fuzz

from app.config.settings import get_settings
from app.prediction_tournament.models import (
    ConsensusCluster,
    ConsensusLevel,
    ForecasterOutput,
    RawPrediction,
    classify_consensus,
)
from app.utils.logging import get_logger

log = get_logger("consensus")


def prediction_similarity(a: RawPrediction, b: RawPrediction) -> float:
    text_a = f"{a.title} {a.prediction_statement} {a.category}".lower()
    text_b = f"{b.title} {b.prediction_statement} {b.category}".lower()
    return fuzz.token_set_ratio(text_a, text_b) / 100.0


def cluster_predictions(
    forecaster_outputs: list[ForecasterOutput],
    threshold: float | None = None,
) -> list[ConsensusCluster]:
    settings = get_settings()
    threshold = threshold if threshold is not None else settings.consensus_similarity_threshold
    total_forecasters = len(forecaster_outputs)

    indexed: list[tuple[str, str, RawPrediction]] = []
    for output in forecaster_outputs:
        for pred in output.predictions:
            indexed.append((output.forecaster_id, output.forecaster_name, pred))

    clusters: list[ConsensusCluster] = []
    assigned: set[int] = set()

    for i, (fid_i, fname_i, pred_i) in enumerate(indexed):
        if i in assigned:
            continue
        members = [(fid_i, pred_i)]
        assigned.add(i)
        for j, (fid_j, _fname_j, pred_j) in enumerate(indexed):
            if j in assigned or j == i:
                continue
            if prediction_similarity(pred_i, pred_j) >= threshold:
                members.append((fid_j, pred_j))
                assigned.add(j)

        confidences = [p.confidence_probability for _, p in members]
        forecaster_ids = list(dict.fromkeys(fid for fid, _ in members))
        level = classify_consensus(len(forecaster_ids), total_forecasters)

        clusters.append(
            ConsensusCluster(
                cluster_id=f"CLUSTER-{uuid.uuid4().hex[:8].upper()}",
                representative_title=pred_i.title,
                representative_statement=pred_i.prediction_statement,
                category=pred_i.category,
                forecaster_ids=forecaster_ids,
                mean_confidence=sum(confidences) / len(confidences),
                median_confidence=median(confidences),
                confidence_range=(min(confidences), max(confidences)),
                areas_of_agreement=[pred_i.category, pred_i.expected_future_state[:120]],
                areas_of_disagreement=[
                    f"Confidence spread: {min(confidences):.0%}–{max(confidences):.0%}"
                ]
                if max(confidences) - min(confidences) > 0.15
                else [],
                consensus_level=level,
            )
        )

    log.stage("consensus clustering complete", clusters=len(clusters))
    return clusters


def find_cluster_for_prediction(
    prediction: RawPrediction,
    forecaster_id: str,
    clusters: list[ConsensusCluster],
    threshold: float | None = None,
) -> ConsensusCluster | None:
    settings = get_settings()
    threshold = threshold if threshold is not None else settings.consensus_similarity_threshold
    for cluster in clusters:
        if forecaster_id in cluster.forecaster_ids:
            rep = RawPrediction(
                title=cluster.representative_title,
                prediction_statement=cluster.representative_statement,
                category=cluster.category,
                confidence_probability=0.5,
                measurable_success_criteria=["x"],
            )
            if prediction_similarity(prediction, rep) >= threshold:
                return cluster
    return None
