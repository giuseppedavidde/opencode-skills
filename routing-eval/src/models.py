"""Pydantic v2 data models for the routing evaluation harness."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RoutingLabel(str, Enum):
    """Label di routing: a quale subagent il router dovrebbe delegare."""

    TRADE = "TRADE"
    CODER = "CODER"
    GRAPHIFY = "GRAPHIFY"
    SKILL_UPDATER = "SKILL_UPDATER"
    BOOK_TO_SKILL = "BOOK_TO_SKILL"
    SIMPLE = "SIMPLE"
    OTHER = "OTHER"


SUBAGENT_MAP: dict[str, RoutingLabel] = {
    "trade": RoutingLabel.TRADE,
    "coder": RoutingLabel.CODER,
    "graphify_helper": RoutingLabel.GRAPHIFY,
    "skill_updater": RoutingLabel.SKILL_UPDATER,
    "book-to-skill-agent": RoutingLabel.BOOK_TO_SKILL,
}


class SessionRecord(BaseModel):
    """Record estratto dal DB: sessione utente con query e decisione di routing reale."""

    session_id: str
    title: str
    agent: str
    model: str
    time_created: int
    user_query: str
    actual_routing: RoutingLabel
    actual_subagent: Optional[str] = None
    query_truncated: bool = False


class RoutingDecision(BaseModel):
    """Decisione del classificatore: label + motivazione (keyword trigger)."""

    label: RoutingLabel
    reason: str
    multiplicity: int = 1


class GoldenCase(BaseModel):
    """Caso curato del golden set di regressione."""

    id: int
    text: str
    expected: RoutingLabel
    note: str
    category: str


class EvalResult(BaseModel):
    """Risultato singolo di comparazione expected vs predicted."""

    query: str
    session_id: str = ""
    expected: RoutingLabel
    predicted: RoutingLabel
    correct: bool
    reason: str = ""


class ConfusionCounts(BaseModel):
    """Matrice di confusione e conteggi aggregati."""

    matrix: dict[str, dict[str, int]] = Field(default_factory=dict)
    total: int = 0
    correct: int = 0
    misrouted: int = 0
    by_category: dict[str, dict[str, float]] = Field(default_factory=dict)


class CategoryStats(BaseModel):
    """Statistiche per categoria: precision, recall, F1."""

    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    support: int = 0


class EvalReport(BaseModel):
    """Report completo di evaluation."""

    mode: str
    total_samples: int
    accuracy: float
    misrouting_rate: float
    confusion: ConfusionCounts
    per_category: dict[str, CategoryStats] = Field(default_factory=dict)
    misrouted: list[EvalResult] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
