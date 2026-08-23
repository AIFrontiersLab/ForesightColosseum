from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.prediction_tournament.models import EvidenceItem, ForecastQuestion
from app.utils.logging import get_logger

log = get_logger("researcher")


class ResearchContext(BaseModel):
    items: list[EvidenceItem]
    research_available: bool
    summary: str
    cutoff: str


def gather_evidence(question: ForecastQuestion, *, max_sources: int = 25, dry_run: bool = False) -> ResearchContext:
    """
    Gather current evidence context for forecasting.
    Without external browsing APIs, records that research was limited to model knowledge
    and does NOT fabricate sources.
    """
    cutoff = datetime.utcnow().isoformat() + "Z"
    if dry_run:
        return ResearchContext(
            items=[],
            research_available=False,
            summary="Dry run — no evidence collection performed.",
            cutoff=cutoff,
        )

    note = EvidenceItem(
        title="Research limitation notice",
        source="system",
        url="",
        published_at=cutoff,
        summary=(
            "External evidence browsing is not configured for this run. "
            "Forecasters must rely on training knowledge and clearly distinguish "
            "known facts from assumptions. No fabricated citations."
        ),
        relevance=f"Forecast question: {question.question}",
        retrieved_at=cutoff,
    )
    log.stage("evidence collection limited — no external research API configured")
    return ResearchContext(
        items=[note],
        research_available=False,
        summary=note.summary,
        cutoff=cutoff,
    )


def format_evidence_for_prompt(context: ResearchContext) -> str:
    if not context.items:
        return "No external evidence was collected. Do not invent citations."
    lines = [f"Research cutoff: {context.cutoff}", f"External research available: {context.research_available}", ""]
    for item in context.items:
        lines.append(f"- {item.title} ({item.source})")
        lines.append(f"  Summary: {item.summary}")
        if item.url:
            lines.append(f"  URL: {item.url}")
        lines.append(f"  Relevance: {item.relevance}")
        lines.append("")
    return "\n".join(lines)
