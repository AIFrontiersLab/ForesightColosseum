from __future__ import annotations

from datetime import date

from app.config.settings import Settings, ensure_directories, get_settings, load_tournament_config
from app.prediction_tournament.calibration import calibrate_prediction, resolve_final_prediction
from app.prediction_tournament.challenger import challenge_prediction
from app.prediction_tournament.consensus import cluster_predictions, find_cluster_for_prediction
from app.prediction_tournament.forecaster import run_all_forecasters
from app.prediction_tournament.judge import judge_prediction
from app.prediction_tournament.llm import TournamentLLM
from app.prediction_tournament.models import (
    ConsensusLevel,
    ForecastQuestion,
    LockedPrediction,
    PredictionState,
    RebuttalAction,
    TournamentResult,
)
from app.prediction_tournament.prediction_store import PredictionStore
from app.prediction_tournament.rebuttal import run_rebuttal
from app.prediction_tournament.report_generator import (
    generate_morning_summary,
    generate_reports,
    output_path_for_date,
)
from app.prediction_tournament.researcher import gather_evidence
from app.utils.logging import get_logger, setup_logging

log = get_logger("orchestrator")


def _maybe_send_whatsapp(summary: str, settings: Settings) -> None:
    if not settings.whatsapp_enabled or not settings.whatsapp_group_id:
        return
    # Hermes WhatsApp delivery is environment-specific; log only unless configured
    log.stage("WhatsApp delivery configured", group=settings.whatsapp_group_id[:8] + "...")


def run_tournament(
    *,
    question: str | None = None,
    dry_run: bool = False,
    run_date: str | None = None,
    settings: Settings | None = None,
) -> TournamentResult:
    s = settings or get_settings()
    setup_logging(s.log_level)
    ensure_directories(s)
    config = load_tournament_config(s)

    fq = ForecastQuestion(
        question=question or config.question,
        horizon_years=config.horizon_years,
    )
    run_day = run_date or date.today().isoformat()
    out_dir = output_path_for_date(s.resolved_output_dir, run_day)
    store = PredictionStore(settings=s)

    if not s.prediction_tournament_enabled:
        return TournamentResult(
            status="DISABLED",
            tournament_id="",
            question=fq,
            output_dir=str(out_dir),
            message="Prediction tournament is disabled",
        )

    log.stage("starting technology prediction tournament", question=fq.question[:80])

    if dry_run:
        forecasters = config.forecasters[: config.forecaster_count]
        planned_calls = (
            1  # research
            + len(forecasters)  # forecasters
            + len(forecasters) * config.predictions_each * 3  # challenge + rebuttal + judge per prediction (estimate)
        )
        return TournamentResult(
            status="DRY_RUN",
            tournament_id="DRY-RUN",
            question=fq,
            output_dir=str(out_dir),
            dry_run=True,
            message=(
                f"Would run tournament with {len(forecasters)} forecasters, "
                f"{config.predictions_each} predictions each (~{planned_calls} LLM calls). "
                f"Output: {out_dir}. DB: {s.resolved_db_path}"
            ),
        )

    llm = TournamentLLM()
    if not llm.available():
        raise RuntimeError(
            "No LLM available. Start Ollama or configure OPENAI_API_KEY with PREDICTION_LLM_PROVIDER=openai"
        )

    evidence = gather_evidence(
        fq,
        max_sources=int(config.research.get("max_sources", 25)),
    )
    forecasters = config.forecasters[: config.forecaster_count]
    forecaster_outputs = run_all_forecasters(forecasters, fq, evidence, llm, config)

    failed = [o.forecaster_id for o in forecaster_outputs if not o.success]
    partial = len(failed) > 0
    raw_count = sum(len(o.predictions) for o in forecaster_outputs)

    tournament_id = store.create_tournament(
        fq,
        config_json=config.model_dump(),
        output_dir=str(out_dir),
        partial=partial,
    )
    store.save_evidence(tournament_id, evidence.items)

    clusters = cluster_predictions(forecaster_outputs)
    locked: list[LockedPrediction] = []
    weights = config.calibration_weights or s.calibration_weights

    for output in forecaster_outputs:
        if not output.success:
            continue
        for raw_pred in output.predictions:
            try:
                challenge = challenge_prediction(raw_pred, llm)
                rebuttal = run_rebuttal(raw_pred, challenge, llm)
                judge = judge_prediction(raw_pred, challenge=challenge, rebuttal=rebuttal, llm=llm)
                final_pred = resolve_final_prediction(raw_pred, rebuttal)
                f_conf, c_adj, j_conf, final_conf = calibrate_prediction(
                    raw_pred, challenge, rebuttal, judge, weights
                )
                cluster = find_cluster_for_prediction(raw_pred, output.forecaster_id, clusters)
                pred_id = store.next_prediction_id()
                withdrawn = rebuttal.action == RebuttalAction.WITHDRAW

                locked_pred = LockedPrediction(
                    prediction_id=pred_id,
                    tournament_id=tournament_id,
                    forecaster_id=output.forecaster_id,
                    forecaster_name=output.forecaster_name,
                    cluster_id=cluster.cluster_id if cluster else "",
                    consensus_level=cluster.consensus_level if cluster else ConsensusLevel.CONTRARIAN,
                    title=final_pred.title,
                    prediction_statement=final_pred.prediction_statement,
                    category=final_pred.category,
                    time_horizon=final_pred.time_horizon,
                    evaluation_deadline=final_pred.evaluation_deadline or fq.default_deadline(),
                    current_state=final_pred.current_state,
                    expected_future_state=final_pred.expected_future_state,
                    why_it_will_happen=final_pred.why_it_will_happen,
                    technical_drivers=final_pred.technical_drivers,
                    economic_drivers=final_pred.economic_drivers,
                    enterprise_drivers=final_pred.enterprise_drivers,
                    developer_ecosystem_drivers=final_pred.developer_ecosystem_drivers,
                    key_assumptions=final_pred.key_assumptions,
                    dependencies=final_pred.dependencies,
                    potential_blockers=final_pred.potential_blockers,
                    signals_to_watch=final_pred.signals_to_watch,
                    measurable_success_criteria=final_pred.measurable_success_criteria,
                    failure_criteria=final_pred.failure_criteria,
                    original_confidence=f_conf,
                    challenger_adjusted_confidence=c_adj,
                    judge_confidence=j_conf,
                    final_calibrated_confidence=final_conf,
                    prediction_quality_score=judge.prediction_quality_score,
                    strategic_importance=judge.scores.strategic_importance,
                    state=PredictionState.WITHDRAWN if withdrawn else PredictionState.OPEN,
                    original_prediction=raw_pred,
                    challenge=challenge,
                    rebuttal=rebuttal,
                    judge_review=judge,
                    model=output.model,
                    prompt_version=output.prompt_version,
                    withdrawn=withdrawn,
                )
                store.lock_prediction(locked_pred)
                if cluster and pred_id not in cluster.prediction_ids:
                    cluster.prediction_ids.append(pred_id)
                locked.append(locked_pred)
            except Exception as exc:
                log.warning(f"pipeline failed for prediction '{raw_pred.title}': {exc}")

    generate_reports(
        result=TournamentResult(
            status="SUCCESS",
            tournament_id=tournament_id,
            question=fq,
            output_dir=str(out_dir),
            raw_predictions_count=raw_count,
            unique_predictions_count=len(clusters),
            locked_predictions_count=len(locked),
            partial_tournament=partial,
            failed_forecasters=failed,
            evidence_count=len(evidence.items),
            research_available=evidence.research_available,
        ),
        question=fq,
        predictions=locked,
        clusters=clusters,
        output_dir=out_dir,
        ranking_weights=config.ranking_weights,
        partial=partial,
    )
    store.export_jsonl(tournament_id)
    store.export_evidence_jsonl(tournament_id)
    import shutil

    evidence_src = store.data_dir / "evidence.jsonl"
    if evidence_src.exists():
        shutil.copy(evidence_src, out_dir / "evidence.json")

    result = TournamentResult(
        status="SUCCESS",
        tournament_id=tournament_id,
        question=fq,
        output_dir=str(out_dir),
        raw_predictions_count=raw_count,
        unique_predictions_count=len(clusters),
        locked_predictions_count=len(locked),
        partial_tournament=partial,
        failed_forecasters=failed,
        evidence_count=len(evidence.items),
        research_available=evidence.research_available,
    )

    if locked:
        top = max(locked, key=lambda p: p.final_calibrated_confidence)
        result.highest_confidence_prediction = top.title
        strong = max(clusters, key=lambda c: c.forecaster_count) if clusters else None
        if strong:
            result.strongest_consensus_prediction = strong.representative_title
        contrarian = [p for p in locked if p.consensus_level == ConsensusLevel.CONTRARIAN]
        if contrarian:
            result.best_contrarian_prediction = max(contrarian, key=lambda p: p.final_calibrated_confidence).title

    result.morning_summary = generate_morning_summary(result, locked, clusters, out_dir)
    _maybe_send_whatsapp(result.morning_summary, s)
    log.stage("tournament complete", locked=len(locked), clusters=len(clusters))
    return result
