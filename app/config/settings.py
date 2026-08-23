from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_BASE_DIR = Path("/Users/aiserver/Workspace_New/TechPrediction")


class ForecasterConfig(BaseModel):
    id: str
    name: str
    role: str
    focus: list[str] = Field(default_factory=list)
    provider: str = ""
    model: str = ""


class TournamentYamlConfig(BaseModel):
    question: str = (
        "What AI technologies, architectures, protocols, infrastructure layers, "
        "and engineering practices are most likely to become strategically important "
        "during the next three years?"
    )
    horizon_years: int = 3
    forecaster_count: int = 5
    predictions_each: int = 7
    mode: str = "standard"

    research: dict[str, int | bool] = Field(default_factory=lambda: {"max_sources": 25, "enabled": True})
    forecasters: list[ForecasterConfig] = Field(default_factory=list)
    calibration_weights: dict[str, float] = Field(
        default_factory=lambda: {"forecaster": 0.50, "challenger": 0.20, "judge": 0.30}
    )
    ranking_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "calibrated_confidence": 0.25,
            "strategic_importance": 0.20,
            "prediction_quality": 0.20,
            "consensus": 0.15,
            "novelty": 0.10,
            "evidence_strength": 0.10,
        }
    )
    partial_outcome_values: dict[str, float] = Field(
        default_factory=lambda: {"TRUE": 1.0, "PARTIALLY_TRUE": 0.5, "FALSE": 0.0}
    )
    cost_controls: dict[str, int | float] = Field(
        default_factory=lambda: {
            "max_predictions_per_forecaster": 10,
            "max_research_sources": 25,
            "max_verification_searches": 10,
            "token_limit_hint": 8000,
        }
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(DEFAULT_BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    prediction_env: str = "development"
    base_dir: Path = DEFAULT_BASE_DIR
    timezone: str = "America/Los_Angeles"
    log_level: str = "INFO"

    prediction_tournament_enabled: bool = True
    prediction_tournament_config: Path = Path("config/tournament.yaml")
    prediction_tournament_output_dir: Path = Path("outputs/prediction_tournament")
    prediction_tournament_data_dir: Path = Path("data/prediction_tournament")
    prediction_tournament_db: Path = Path("data/prediction_tournament/tournament.db")

    prediction_llm_provider: str = "ollama"
    prediction_llm_model: str = "qwen3.6:27b"
    prediction_llm_base_url: str = "http://10.0.0.40:11434/v1"
    prediction_llm_temperature: float = 0.4
    prediction_llm_timeout_seconds: int = 300
    prediction_llm_max_retries: int = 2
    openai_api_key: str = ""

    whatsapp_enabled: bool = False
    whatsapp_group_id: str = ""

    calibration_weight_forecaster: float = 0.50
    calibration_weight_challenger: float = 0.20
    calibration_weight_judge: float = 0.30
    consensus_similarity_threshold: float = 0.72

    @model_validator(mode="after")
    def _apply_ollama_env_aliases(self) -> Settings:
        env = os.environ

        # Support standard Ollama env names when the app-specific variables
        # are not set, so local verification can use an existing Ollama setup.
        if "PREDICTION_LLM_PROVIDER" not in env and (env.get("OLLAMA_HOST") or env.get("OLLAMA_MODEL")):
            self.prediction_llm_provider = "ollama"
        if "PREDICTION_LLM_MODEL" not in env and env.get("OLLAMA_MODEL"):
            self.prediction_llm_model = env["OLLAMA_MODEL"]
        if "PREDICTION_LLM_BASE_URL" not in env and env.get("OLLAMA_HOST"):
            self.prediction_llm_base_url = env["OLLAMA_HOST"].rstrip("/") + "/v1"

        return self

    @field_validator(
        "base_dir",
        "prediction_tournament_config",
        "prediction_tournament_output_dir",
        "prediction_tournament_data_dir",
        "prediction_tournament_db",
        mode="before",
    )
    @classmethod
    def _expand_path(cls, value: object) -> Path:
        return Path(str(value)).expanduser()

    @property
    def resolved_output_dir(self) -> Path:
        path = self.prediction_tournament_output_dir
        return path if path.is_absolute() else self.base_dir / path

    @property
    def resolved_data_dir(self) -> Path:
        path = self.prediction_tournament_data_dir
        return path if path.is_absolute() else self.base_dir / path

    @property
    def resolved_db_path(self) -> Path:
        path = self.prediction_tournament_db
        return path if path.is_absolute() else self.base_dir / path

    @property
    def prompts_dir(self) -> Path:
        return self.base_dir / "app" / "prediction_tournament" / "prompts"

    @property
    def calibration_weights(self) -> dict[str, float]:
        return {
            "forecaster": self.calibration_weight_forecaster,
            "challenger": self.calibration_weight_challenger,
            "judge": self.calibration_weight_judge,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()


def ensure_directories(settings: Settings | None = None) -> None:
    s = settings or get_settings()
    for path in (
        s.base_dir,
        s.resolved_data_dir,
        s.resolved_output_dir,
        s.resolved_db_path.parent,
        s.base_dir / "logs",
        s.base_dir / "config",
    ):
        path.mkdir(parents=True, exist_ok=True)


def load_tournament_config(settings: Settings | None = None) -> TournamentYamlConfig:
    s = settings or get_settings()
    path = s.prediction_tournament_config
    if not path.is_absolute():
        path = s.base_dir / path
    if not path.exists():
        return default_tournament_config()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    tournament = raw.get("tournament", raw)
    cfg = TournamentYamlConfig.model_validate(tournament)
    if not cfg.forecasters:
        cfg.forecasters = default_forecasters()
    return cfg


def default_forecasters() -> list[ForecasterConfig]:
    return [
        ForecasterConfig(
            id="architect",
            name="Technology Architect",
            role="FORECASTER 1 — Technology Architect",
            focus=[
                "technical architecture",
                "scalability",
                "developer adoption",
                "platform evolution",
            ],
        ),
        ForecasterConfig(
            id="researcher",
            name="Research Analyst",
            role="FORECASTER 2 — Research Analyst",
            focus=[
                "research momentum",
                "papers",
                "benchmarks",
                "academic developments",
                "technical breakthroughs",
            ],
        ),
        ForecasterConfig(
            id="enterprise",
            name="Enterprise Strategist",
            role="FORECASTER 3 — Enterprise Strategist",
            focus=[
                "enterprise adoption",
                "security",
                "governance",
                "ROI",
                "operational requirements",
            ],
        ),
        ForecasterConfig(
            id="developer",
            name="Developer Ecosystem Analyst",
            role="FORECASTER 4 — Developer Ecosystem Analyst",
            focus=[
                "GitHub",
                "open source",
                "SDKs",
                "developer activity",
                "tooling ecosystems",
                "standards",
            ],
        ),
        ForecasterConfig(
            id="contrarian",
            name="Contrarian Futurist",
            role="FORECASTER 5 — Contrarian Futurist",
            focus=[
                "underestimated technologies",
                "second-order effects",
                "non-obvious shifts",
                "technologies the market may currently undervalue",
            ],
        ),
    ]


def default_tournament_config() -> TournamentYamlConfig:
    return TournamentYamlConfig(forecasters=default_forecasters())
