from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from app.config.settings import Settings, get_settings
from app.prediction_tournament.models import (
    ChallengeResult,
    EvidenceItem,
    ForecastQuestion,
    ForecasterScore,
    JudgeReview,
    LockedPrediction,
    PredictionState,
    RawPrediction,
    RebuttalResult,
    VerificationResult,
    generate_prediction_id,
    generate_tournament_id,
)
from app.utils.logging import get_logger

log = get_logger("store")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tournaments (
    tournament_id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    horizon_years INTEGER,
    evaluation_deadline TEXT,
    created_at TEXT NOT NULL,
    partial_tournament INTEGER DEFAULT 0,
    config_json TEXT,
    output_dir TEXT
);

CREATE TABLE IF NOT EXISTS forecasters (
    forecaster_id TEXT NOT NULL,
    tournament_id TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT,
    success INTEGER DEFAULT 1,
    error TEXT,
    model TEXT,
    PRIMARY KEY (forecaster_id, tournament_id),
    FOREIGN KEY (tournament_id) REFERENCES tournaments(tournament_id)
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT,
    url TEXT,
    published_at TEXT,
    summary TEXT,
    relevance TEXT,
    retrieved_at TEXT,
    FOREIGN KEY (tournament_id) REFERENCES tournaments(tournament_id)
);

CREATE TABLE IF NOT EXISTS predictions (
    prediction_id TEXT PRIMARY KEY,
    tournament_id TEXT NOT NULL,
    forecaster_id TEXT NOT NULL,
    forecaster_name TEXT,
    cluster_id TEXT,
    consensus_level TEXT,
    title TEXT NOT NULL,
    prediction_statement TEXT NOT NULL,
    category TEXT,
    time_horizon TEXT,
    evaluation_deadline TEXT,
    current_state TEXT,
    expected_future_state TEXT,
    why_it_will_happen TEXT,
    technical_drivers_json TEXT,
    economic_drivers_json TEXT,
    enterprise_drivers_json TEXT,
    developer_ecosystem_drivers_json TEXT,
    key_assumptions_json TEXT,
    dependencies_json TEXT,
    potential_blockers_json TEXT,
    signals_to_watch_json TEXT,
    measurable_success_criteria_json TEXT,
    failure_criteria_json TEXT,
    original_confidence REAL,
    challenger_adjusted_confidence REAL,
    judge_confidence REAL,
    final_calibrated_confidence REAL,
    prediction_quality_score REAL,
    strategic_importance REAL,
    state TEXT DEFAULT 'OPEN',
    payload_hash TEXT NOT NULL,
    original_prediction_json TEXT,
    created_at TEXT NOT NULL,
    locked_at TEXT,
    evaluation_start TEXT,
    model TEXT,
    prompt_version TEXT,
    withdrawn INTEGER DEFAULT 0,
    FOREIGN KEY (tournament_id) REFERENCES tournaments(tournament_id)
);

CREATE TABLE IF NOT EXISTS prediction_revisions (
    revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id TEXT NOT NULL,
    revision_type TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id)
);

CREATE TABLE IF NOT EXISTS challenges (
    challenge_id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id TEXT NOT NULL,
    challenge_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id)
);

CREATE TABLE IF NOT EXISTS rebuttals (
    rebuttal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id TEXT NOT NULL,
    rebuttal_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id)
);

CREATE TABLE IF NOT EXISTS judge_reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id TEXT NOT NULL,
    review_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id)
);

CREATE TABLE IF NOT EXISTS verification_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    predictions_checked INTEGER,
    predictions_updated INTEGER,
    report_path TEXT
);

CREATE TABLE IF NOT EXISTS verification_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    prediction_id TEXT,
    evidence_json TEXT,
    criteria_supported_json TEXT,
    criteria_contradicted_json TEXT,
    confidence REAL,
    FOREIGN KEY (run_id) REFERENCES verification_runs(run_id),
    FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id)
);

CREATE TABLE IF NOT EXISTS prediction_outcomes (
    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id TEXT NOT NULL,
    state TEXT NOT NULL,
    confidence REAL,
    outcome_value REAL,
    brier_score REAL,
    reasoning_summary TEXT,
    closed_at TEXT,
    FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id)
);

CREATE TABLE IF NOT EXISTS forecaster_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    forecaster_id TEXT NOT NULL,
    forecaster_name TEXT,
    tournament_id TEXT,
    score_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta_counters (
    name TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
"""


class PredictionStore:
    def __init__(self, db_path: Path | None = None, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self.db_path = db_path or s.resolved_db_path
        self.data_dir = s.resolved_data_dir
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def next_tournament_id(self) -> str:
        year = datetime.utcnow().year
        with self._conn() as conn:
            key = f"tournament_{year}"
            row = conn.execute("SELECT value FROM meta_counters WHERE name = ?", (key,)).fetchone()
            seq = (row["value"] if row else 0) + 1
            conn.execute(
                "INSERT INTO meta_counters(name, value) VALUES(?, ?) "
                "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
                (key, seq),
            )
        return generate_tournament_id(year, seq)

    def next_prediction_id(self) -> str:
        year = datetime.utcnow().year
        with self._conn() as conn:
            key = f"prediction_{year}"
            row = conn.execute("SELECT value FROM meta_counters WHERE name = ?", (key,)).fetchone()
            seq = (row["value"] if row else 0) + 1
            conn.execute(
                "INSERT INTO meta_counters(name, value) VALUES(?, ?) "
                "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
                (key, seq),
            )
        return generate_prediction_id(year, seq)

    def create_tournament(
        self,
        question: ForecastQuestion,
        *,
        config_json: dict[str, Any],
        output_dir: str,
        partial: bool = False,
    ) -> str:
        tournament_id = self.next_tournament_id()
        now = datetime.utcnow().isoformat() + "Z"
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO tournaments
                (tournament_id, question, horizon_years, evaluation_deadline, created_at,
                 partial_tournament, config_json, output_dir)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tournament_id,
                    question.question,
                    question.horizon_years,
                    question.default_deadline(),
                    now,
                    int(partial),
                    json.dumps(config_json),
                    output_dir,
                ),
            )
        return tournament_id

    def save_evidence(self, tournament_id: str, items: list[EvidenceItem]) -> None:
        with self._conn() as conn:
            for item in items:
                conn.execute(
                    """
                    INSERT INTO evidence
                    (tournament_id, title, source, url, published_at, summary, relevance, retrieved_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tournament_id,
                        item.title,
                        item.source,
                        item.url,
                        item.published_at,
                        item.summary,
                        item.relevance,
                        item.retrieved_at,
                    ),
                )

    def lock_prediction(self, prediction: LockedPrediction) -> None:
        prediction.payload_hash = prediction.compute_hash()
        now = datetime.utcnow().isoformat() + "Z"
        prediction.locked_at = now
        if not prediction.created_at:
            prediction.created_at = now
        if not prediction.evaluation_start:
            prediction.evaluation_start = now

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO predictions (
                    prediction_id, tournament_id, forecaster_id, forecaster_name, cluster_id,
                    consensus_level, title, prediction_statement, category, time_horizon,
                    evaluation_deadline, current_state, expected_future_state, why_it_will_happen,
                    technical_drivers_json, economic_drivers_json, enterprise_drivers_json,
                    developer_ecosystem_drivers_json, key_assumptions_json, dependencies_json,
                    potential_blockers_json, signals_to_watch_json, measurable_success_criteria_json,
                    failure_criteria_json, original_confidence, challenger_adjusted_confidence,
                    judge_confidence, final_calibrated_confidence, prediction_quality_score,
                    strategic_importance, state, payload_hash, original_prediction_json,
                    created_at, locked_at, evaluation_start, model, prompt_version, withdrawn
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    prediction.prediction_id,
                    prediction.tournament_id,
                    prediction.forecaster_id,
                    prediction.forecaster_name,
                    prediction.cluster_id,
                    prediction.consensus_level.value,
                    prediction.title,
                    prediction.prediction_statement,
                    prediction.category,
                    prediction.time_horizon,
                    prediction.evaluation_deadline,
                    prediction.current_state,
                    prediction.expected_future_state,
                    prediction.why_it_will_happen,
                    json.dumps(prediction.technical_drivers),
                    json.dumps(prediction.economic_drivers),
                    json.dumps(prediction.enterprise_drivers),
                    json.dumps(prediction.developer_ecosystem_drivers),
                    json.dumps(prediction.key_assumptions),
                    json.dumps(prediction.dependencies),
                    json.dumps(prediction.potential_blockers),
                    json.dumps(prediction.signals_to_watch),
                    json.dumps(prediction.measurable_success_criteria),
                    json.dumps(prediction.failure_criteria),
                    prediction.original_confidence,
                    prediction.challenger_adjusted_confidence,
                    prediction.judge_confidence,
                    prediction.final_calibrated_confidence,
                    prediction.prediction_quality_score,
                    prediction.strategic_importance,
                    prediction.state.value,
                    prediction.payload_hash,
                    prediction.original_prediction.model_dump_json(),
                    prediction.created_at,
                    prediction.locked_at,
                    prediction.evaluation_start,
                    prediction.model,
                    prediction.prompt_version,
                    int(prediction.withdrawn),
                ),
            )
            if prediction.challenge:
                conn.execute(
                    "INSERT INTO challenges (prediction_id, challenge_json, created_at) VALUES (?, ?, ?)",
                    (prediction.prediction_id, prediction.challenge.model_dump_json(), now),
                )
            if prediction.rebuttal:
                conn.execute(
                    "INSERT INTO rebuttals (prediction_id, rebuttal_json, created_at) VALUES (?, ?, ?)",
                    (prediction.prediction_id, prediction.rebuttal.model_dump_json(), now),
                )
            if prediction.judge_review:
                conn.execute(
                    "INSERT INTO judge_reviews (prediction_id, review_json, created_at) VALUES (?, ?, ?)",
                    (prediction.prediction_id, prediction.judge_review.model_dump_json(), now),
                )

    def get_prediction(self, prediction_id: str) -> LockedPrediction | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM predictions WHERE prediction_id = ?", (prediction_id,)).fetchone()
            if not row:
                return None
            return self._row_to_prediction(row, conn)

    def list_predictions(
        self,
        *,
        tournament_id: str | None = None,
        state: PredictionState | None = None,
        open_only: bool = False,
    ) -> list[LockedPrediction]:
        query = "SELECT * FROM predictions WHERE 1=1"
        params: list[Any] = []
        if tournament_id:
            query += " AND tournament_id = ?"
            params.append(tournament_id)
        if state:
            query += " AND state = ?"
            params.append(state.value)
        if open_only:
            query += " AND state NOT IN ('TRUE', 'FALSE', 'PARTIALLY_TRUE', 'INCONCLUSIVE', 'EXPIRED', 'WITHDRAWN')"
        query += " ORDER BY final_calibrated_confidence DESC"
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_prediction(row, conn) for row in rows]

    def update_prediction_state(
        self,
        prediction_id: str,
        state: PredictionState,
        *,
        reasoning: str = "",
        outcome_value: float | None = None,
        brier: float | None = None,
    ) -> None:
        now = datetime.utcnow().isoformat() + "Z"
        with self._conn() as conn:
            conn.execute("UPDATE predictions SET state = ? WHERE prediction_id = ?", (state.value, prediction_id))
            conn.execute(
                """
                INSERT INTO prediction_outcomes
                (prediction_id, state, confidence, outcome_value, brier_score, reasoning_summary, closed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (prediction_id, state.value, None, outcome_value, brier, reasoning, now),
            )
            conn.execute(
                """
                INSERT INTO prediction_revisions (prediction_id, revision_type, payload_json, created_at)
                VALUES (?, 'state_change', ?, ?)
                """,
                (prediction_id, json.dumps({"state": state.value, "reasoning": reasoning}), now),
            )

    def verify_hash_integrity(self, prediction_id: str) -> bool:
        pred = self.get_prediction(prediction_id)
        if not pred:
            return False
        return pred.payload_hash == pred.compute_hash()

    def export_jsonl(self, tournament_id: str | None = None) -> Path:
        predictions = self.list_predictions(tournament_id=tournament_id)
        path = self.data_dir / "predictions.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for pred in predictions:
                fh.write(pred.model_dump_json() + "\n")
        return path

    def export_evidence_jsonl(self, tournament_id: str) -> Path:
        path = self.data_dir / "evidence.jsonl"
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM evidence WHERE tournament_id = ? ORDER BY evidence_id",
                (tournament_id,),
            ).fetchall()
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(dict(row)) + "\n")
        return path

    def save_forecaster_score(self, score: ForecasterScore, tournament_id: str = "") -> None:
        now = datetime.utcnow().isoformat() + "Z"
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO forecaster_scores (forecaster_id, forecaster_name, tournament_id, score_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (score.forecaster_id, score.forecaster_name, tournament_id, score.model_dump_json(), now),
            )

    def record_verification_run(
        self,
        *,
        predictions_checked: int,
        predictions_updated: int,
        report_path: str,
    ) -> int:
        now = datetime.utcnow().isoformat() + "Z"
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO verification_runs (run_at, predictions_checked, predictions_updated, report_path)
                VALUES (?, ?, ?, ?)
                """,
                (now, predictions_checked, predictions_updated, report_path),
            )
            return int(cur.lastrowid)

    def _row_to_prediction(self, row: sqlite3.Row, conn: sqlite3.Connection) -> LockedPrediction:
        from app.prediction_tournament.models import ConsensusLevel

        challenge_row = conn.execute(
            "SELECT challenge_json FROM challenges WHERE prediction_id = ? ORDER BY challenge_id DESC LIMIT 1",
            (row["prediction_id"],),
        ).fetchone()
        rebuttal_row = conn.execute(
            "SELECT rebuttal_json FROM rebuttals WHERE prediction_id = ? ORDER BY rebuttal_id DESC LIMIT 1",
            (row["prediction_id"],),
        ).fetchone()
        judge_row = conn.execute(
            "SELECT review_json FROM judge_reviews WHERE prediction_id = ? ORDER BY review_id DESC LIMIT 1",
            (row["prediction_id"],),
        ).fetchone()

        return LockedPrediction(
            prediction_id=row["prediction_id"],
            tournament_id=row["tournament_id"],
            forecaster_id=row["forecaster_id"],
            forecaster_name=row["forecaster_name"] or "",
            cluster_id=row["cluster_id"] or "",
            consensus_level=ConsensusLevel(row["consensus_level"] or "CONTRARIAN"),
            title=row["title"],
            prediction_statement=row["prediction_statement"],
            category=row["category"] or "",
            time_horizon=row["time_horizon"] or "",
            evaluation_deadline=row["evaluation_deadline"] or "",
            current_state=row["current_state"] or "",
            expected_future_state=row["expected_future_state"] or "",
            why_it_will_happen=row["why_it_will_happen"] or "",
            technical_drivers=json.loads(row["technical_drivers_json"] or "[]"),
            economic_drivers=json.loads(row["economic_drivers_json"] or "[]"),
            enterprise_drivers=json.loads(row["enterprise_drivers_json"] or "[]"),
            developer_ecosystem_drivers=json.loads(row["developer_ecosystem_drivers_json"] or "[]"),
            key_assumptions=json.loads(row["key_assumptions_json"] or "[]"),
            dependencies=json.loads(row["dependencies_json"] or "[]"),
            potential_blockers=json.loads(row["potential_blockers_json"] or "[]"),
            signals_to_watch=json.loads(row["signals_to_watch_json"] or "[]"),
            measurable_success_criteria=json.loads(row["measurable_success_criteria_json"] or "[]"),
            failure_criteria=json.loads(row["failure_criteria_json"] or "[]"),
            original_confidence=row["original_confidence"] or 0.0,
            challenger_adjusted_confidence=row["challenger_adjusted_confidence"] or 0.0,
            judge_confidence=row["judge_confidence"] or 0.0,
            final_calibrated_confidence=row["final_calibrated_confidence"] or 0.0,
            prediction_quality_score=row["prediction_quality_score"] or 0.0,
            strategic_importance=row["strategic_importance"] or 0.0,
            state=PredictionState(row["state"]),
            original_prediction=RawPrediction.model_validate_json(row["original_prediction_json"]),
            challenge=ChallengeResult.model_validate_json(challenge_row["challenge_json"]) if challenge_row else None,
            rebuttal=RebuttalResult.model_validate_json(rebuttal_row["rebuttal_json"]) if rebuttal_row else None,
            judge_review=JudgeReview.model_validate_json(judge_row["review_json"]).finalize() if judge_row else None,
            payload_hash=row["payload_hash"],
            created_at=row["created_at"],
            locked_at=row["locked_at"] or "",
            evaluation_start=row["evaluation_start"] or "",
            model=row["model"] or "",
            prompt_version=row["prompt_version"] or "",
            withdrawn=bool(row["withdrawn"]),
        )
