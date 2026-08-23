from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.prediction_tournament.models import (
    ConsensusCluster,
    ConsensusLevel,
    ForecastQuestion,
    LockedPrediction,
    TournamentResult,
)
from app.utils.logging import get_logger

log = get_logger("reports")


def output_path_for_date(base_dir: Path, run_day: str | None = None) -> Path:
    day = run_day or date.today().isoformat()
    path = base_dir / day
    path.mkdir(parents=True, exist_ok=True)
    return path


def compute_surprise_index(pred: LockedPrediction, cluster: ConsensusCluster | None) -> float:
    consensus_factor = {
        ConsensusLevel.HIGH: 0.2,
        ConsensusLevel.MODERATE: 0.5,
        ConsensusLevel.LOW: 0.7,
        ConsensusLevel.CONTRARIAN: 1.0,
    }.get(pred.consensus_level, 0.5)
    impact = pred.strategic_importance / 10.0
    evidence = pred.prediction_quality_score / 10.0
    confidence = pred.final_calibrated_confidence
    return round(consensus_factor * 0.3 + impact * 0.3 + evidence * 0.2 + confidence * 0.2, 3)


def rank_predictions(
    predictions: list[LockedPrediction],
    clusters: list[ConsensusCluster],
    weights: dict[str, float],
) -> list[LockedPrediction]:
    cluster_map = {c.cluster_id: c for c in clusters}

    def score(p: LockedPrediction) -> float:
        cluster = cluster_map.get(p.cluster_id)
        consensus_score = (cluster.forecaster_count / 5.0) if cluster else 0.2
        return (
            p.final_calibrated_confidence * weights.get("calibrated_confidence", 0.25)
            + (p.strategic_importance / 10.0) * weights.get("strategic_importance", 0.20)
            + (p.prediction_quality_score / 10.0) * weights.get("prediction_quality", 0.20)
            + consensus_score * weights.get("consensus", 0.15)
            + (p.judge_review.scores.novelty / 10.0 if p.judge_review else 0.5)
            * weights.get("novelty", 0.10)
            + (p.judge_review.scores.evidence_quality / 10.0 if p.judge_review else 0.5)
            * weights.get("evidence_strength", 0.10)
        )

    return sorted(predictions, key=score, reverse=True)


def generate_morning_summary(
    result: TournamentResult,
    predictions: list[LockedPrediction],
    clusters: list[ConsensusCluster],
    output_dir: Path,
) -> str:
    high_consensus = sum(1 for c in clusters if c.consensus_level == ConsensusLevel.HIGH)
    contrarian = [p for p in predictions if p.consensus_level == ConsensusLevel.CONTRARIAN]
    top = max(predictions, key=lambda p: p.final_calibrated_confidence) if predictions else None
    strongest = max(clusters, key=lambda c: c.forecaster_count) if clusters else None
    best_contrarian = max(contrarian, key=lambda p: p.final_calibrated_confidence) if contrarian else None
    biggest_disagreement = max(clusters, key=lambda c: c.confidence_range[1] - c.confidence_range[0]) if clusters else None

    lines = [
        "🔮 TECHNOLOGY PREDICTION TOURNAMENT",
        "",
        f"Question:\n{result.question.question}",
        "",
        f"{len(result.failed_forecasters) and 5 - len(result.failed_forecasters) or 5} forecasters",
        f"{result.raw_predictions_count} raw predictions",
        f"{result.unique_predictions_count} unique prediction clusters",
        f"{high_consensus} high-consensus predictions",
        f"{len(contrarian)} contrarian bets",
        "",
    ]
    if top:
        lines.append(f"🏆 Highest Confidence\n{top.title} — {top.final_calibrated_confidence:.0%}")
        lines.append("")
    if strongest:
        lines.append(f"🔥 Strongest Consensus\n{strongest.representative_title} — {strongest.forecaster_count}/5")
        lines.append("")
    if best_contrarian:
        lines.append(f"🎲 Best Contrarian Bet\n{best_contrarian.title} — {best_contrarian.final_calibrated_confidence:.0%}")
        lines.append("")
    if biggest_disagreement:
        lines.append(f"⚔️ Biggest Disagreement\n{biggest_disagreement.representative_title}")
        lines.append("")
    lines.append(f"📊 Tournament report:\n{output_dir}")
    return "\n".join(lines)


def generate_reports(
    *,
    result: TournamentResult,
    question: ForecastQuestion,
    predictions: list[LockedPrediction],
    clusters: list[ConsensusCluster],
    output_dir: Path,
    ranking_weights: dict[str, float],
    partial: bool,
) -> dict[str, Path]:
    ranked = rank_predictions(predictions, clusters, ranking_weights)
    paths: dict[str, Path] = {}

    summary_lines = [
        "# TECHNOLOGY PREDICTION TOURNAMENT — 2026",
        "",
        "## Executive Summary",
        "",
        f"**Question:** {question.question}",
        f"**Tournament ID:** {result.tournament_id}",
        f"**Raw predictions:** {result.raw_predictions_count}",
        f"**Unique clusters:** {result.unique_predictions_count}",
        f"**Locked predictions:** {result.locked_predictions_count}",
        f"**Partial tournament:** {partial}",
        "",
    ]
    if result.failed_forecasters:
        summary_lines.append(f"**Failed forecasters:** {', '.join(result.failed_forecasters)}")
        summary_lines.append("")

    paths["tournament-summary.md"] = output_dir / "tournament-summary.md"
    paths["tournament-summary.md"].write_text("\n".join(summary_lines), encoding="utf-8")

    # Top 10
    top_lines = ["# TOP 10 AI TECHNOLOGY PREDICTIONS", ""]
    for i, pred in enumerate(ranked[:10], 1):
        top_lines.extend(
            [
                f"## {i}. {pred.title}",
                f"**Confidence:** {pred.final_calibrated_confidence:.0%} | **Consensus:** {pred.consensus_level.value}",
                f"**Category:** {pred.category}",
                "",
                pred.prediction_statement,
                "",
                "**Success criteria:**",
            ]
        )
        top_lines.extend(f"- {c}" for c in pred.measurable_success_criteria)
        top_lines.append("")
    paths["top-predictions.md"] = output_dir / "top-predictions.md"
    paths["top-predictions.md"].write_text("\n".join(top_lines), encoding="utf-8")

    # Consensus map
    consensus_lines = ["# CONSENSUS MAP", ""]
    for cluster in sorted(clusters, key=lambda c: c.forecaster_count, reverse=True):
        consensus_lines.extend(
            [
                f"## {cluster.representative_title}",
                f"**Support:** {cluster.forecaster_count}/5 forecasters ({cluster.consensus_level.value})",
                f"**Mean confidence:** {cluster.mean_confidence:.0%}",
                f"**Forecasters:** {', '.join(cluster.forecaster_ids)}",
                "",
                cluster.representative_statement,
                "",
            ]
        )
    paths["consensus-map.md"] = output_dir / "consensus-map.md"
    paths["consensus-map.md"].write_text("\n".join(consensus_lines), encoding="utf-8")

    # Disagreements
    disagree_lines = ["# WHERE THE AGENTS DISAGREE", ""]
    for cluster in sorted(clusters, key=lambda c: c.confidence_range[1] - c.confidence_range[0], reverse=True):
        spread = cluster.confidence_range[1] - cluster.confidence_range[0]
        if spread < 0.15:
            continue
        disagree_lines.extend(
            [
                f"## {cluster.representative_title}",
                f"Confidence range: {cluster.confidence_range[0]:.0%} – {cluster.confidence_range[1]:.0%}",
                f"Forecasters: {', '.join(cluster.forecaster_ids)}",
                "",
                "Core disagreement likely reflects different adoption timelines or enterprise readiness assumptions.",
                "",
            ]
        )
    paths["disagreements.md"] = output_dir / "disagreements.md"
    paths["disagreements.md"].write_text("\n".join(disagree_lines), encoding="utf-8")

    # Contrarian bets
    contrarian_lines = ["# CONTRARIAN BETS", ""]
    for pred in sorted(
        [p for p in predictions if p.consensus_level == ConsensusLevel.CONTRARIAN],
        key=lambda p: p.final_calibrated_confidence,
        reverse=True,
    ):
        contrarian_lines.extend(
            [
                "## CONTRARIAN BET",
                "",
                f"**Prediction:** {pred.title}",
                f"**Support:** 1/5 forecasters ({pred.forecaster_name})",
                f"**Confidence:** {pred.final_calibrated_confidence:.0%}",
                "",
                pred.prediction_statement,
                "",
                "**Signals to watch:**",
            ]
        )
        contrarian_lines.extend(f"- {s}" for s in pred.signals_to_watch[:5])
        contrarian_lines.append("")
    paths["contrarian-bets.md"] = output_dir / "contrarian-bets.md"
    paths["contrarian-bets.md"].write_text("\n".join(contrarian_lines), encoding="utf-8")

    # Scorecard
    scorecard_lines = ["# AI TECHNOLOGY PREDICTION SCORECARD", ""]
    for pred in ranked:
        scorecard_lines.append(
            f"**{pred.title}** — Confidence: {pred.final_calibrated_confidence:.0%} | "
            f"Consensus: {pred.consensus_level.value} | Status: {pred.state.value} | "
            f"Deadline: {pred.evaluation_deadline}"
        )
    paths["scorecard.md"] = output_dir / "scorecard.md"
    paths["scorecard.md"].write_text("\n".join(scorecard_lines), encoding="utf-8")

    # JSON export
    paths["predictions.json"] = output_dir / "predictions.json"
    paths["predictions.json"].write_text(
        json.dumps([p.model_dump(mode="json") for p in predictions], indent=2),
        encoding="utf-8",
    )

    # Append methodology to summary
    methodology = [
        "",
        "## Tournament Methodology",
        "",
        "1. Five independent forecasters with distinct analytical lenses",
        "2. Adversarial challenger for each prediction",
        "3. One forecaster rebuttal preserving original record",
        "4. Independent judge scoring and calibration",
        "5. Immutable ledger with SHA-256 payload hash",
        "",
        "## All Locked Predictions",
        "",
    ]
    for pred in predictions:
        methodology.append(f"- `{pred.prediction_id}` — {pred.title} ({pred.final_calibrated_confidence:.0%})")
    paths["tournament-summary.md"].write_text(
        paths["tournament-summary.md"].read_text(encoding="utf-8") + "\n".join(methodology),
        encoding="utf-8",
    )

    log.stage("reports generated", dir=str(output_dir))
    return paths
