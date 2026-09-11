"""Classifier that replicates the OpenCode router's keyword-based routing rules.

Input: user text (Italian or English).
Output: RoutingLabel + reason (triggering keyword).
"""

# pylint: disable=duplicate-code

from __future__ import annotations

import re

from src.models import RoutingLabel, RoutingDecision


TICKER_PATTERN = re.compile(r"\b[A-Z]{1,5}(?:\.[A-Z]{2})?\b")

WELL_KNOWN_TICKERS: set[str] = {
    "LHX", "HPQ", "AAPL", "TSLA", "MSFT", "GOOGL", "GOOG", "AMZN", "META",
    "NVDA", "SPY", "QQQ", "IWM", "DIA", "VIX", "DXY",
    "GME", "AMC", "BB", "NOK", "PLTR", "SOFI", "RIVN",
    "ENI", "STLA", "ISP", "UCG", "RACE", "LUXO",
    "BTC", "ETH", "SOL", "XRP", "ADA", "DOGE",
    "ENI.MI", "STLA.MI", "ISP.MI", "UCG.MI", "RACE.MI", "LUXO.MI",
}

TRADE_KEYWORDS: list[str] = [
    "stock", "ticker", "opzioni", "options", "strike", "call ", "put ",
    "spread", "greche", "greeks", "delta", "gamma", "theta", "vega",
    "posizione", "position", "analisi tecnica", "technical analysis",
    "portfolio", "mercato", "market", "long/short", "long ", "short ",
    "scadenza", "expiry", "DTE", " IV ", "volatility", "volatilità",
    "macro", "VIX", "DXY", "buy/", "sell/", "buy ", "sell ",
    "prezzo", "price", "entry/", "exit/", "entry ", "exit ",
    "roll/", "rolling", "hedge/", "hedging", "repair", "riparare",
    "strategy", "strategia", "analizza ", "analisi di ",
    "scan ", "scanner", "scan del mercato", "scansione",
    "what to do with", "cosa faccio con", "come gestire",
    "chart", "grafico", "candlestick", "supporto", "resistenza",
    "RSI", "MACD", "EMA", "SMA", "Bollinger", "volume profile",
    "Wyckoff", "VPA", "order flow", "orderflow",
    "trade", "trading", "trader",
    "Bali", "TS-MOM", "Bakshi", "LGBM",
    "fetch stock", "fetch data", "fetch market",
    "option chain", "option data",
    "what options strategy",
]

TRADE_EXACT: list[str] = [
    "dxy",
    "vix",
    "iv rank",
    "iv percentile",
    "ivr",
    "nvda",
]

CODER_KEYWORDS: list[str] = [
    "refactoring", "refactor", "implementa", "implement ",
    "add feature", "new feature", "multi-file", "multiple files",
    "architecture change", "architectur", "new module",
    "write test", "scrivi test", "debug this", "debugga",
    "algorithm implementation", "implementazione algoritm",
    "fix this ", "fix bug",
    "refactoring del file", "write unit test",
    "crea modulo", "add module",
    "scrivi codice", "write code",
]

GRAPHIFY_KEYWORDS: list[str] = [
    "graph ", "grafo", "graphify", "knowledge graph",
    "mappa ", "visualizza", "mappa del codice",
    "graph this", "build graph", "analyze repo",
    "analizza codice", "/graphify", "query",
    "path between", "explain node", "community detection",
    "god nodes", "surprising connections", "graph query",
    "knowledge graph",
]

GRAPHIFY_EXACT: list[str] = [
    "graphify",
    "knowledge graph",
    "/graphify",
]

SKILL_UPDATER_KEYWORDS: list[str] = [
    "aggiorna skill", "update skill", "skill update",
    "skill updater", "sync skill", "skill sync",
    "sync all skills",
    "update book-to-skill", "update graphify",
    "update quant-mind", "aggiorna quant-mind",
    "aggiorna graphify", "submodule update",
    "git submodule update", "allinea skill",
    "skill aggiornamento", "skill upgrade",
    "update the skill", "aggiorna la skill",
    "update my skills", "aggiorna le skill",
    "update all skills", "aggiorna tutte le skill",
    "refresh skill", "skill refresh",
]

BOOK_TO_SKILL_KEYWORDS: list[str] = [
    "converti libro", "crea skill da libro",
    "book-to-skill", "processa libro", "genera skill",
    "skill da pdf", "skill da epub", "skill da file",
    "convert book to skill", "generate skill from book",
    "processing book", "crea skill", "trasforma in skill",
    "converti questo pdf", "converti pdf in skill",
    "questo libro in", "questo pdf in",
    "convert book", "transform book",
    "book to skill", "da libro a skill",
    ".pdf in skill", ".epub in skill",
    "converti documento in skill",
    "process book into skill",
]


def _word_boundary_match(keyword: str, text: str) -> bool:
    """Verifica match con confine di parola per keyword a parola singola."""
    kw_lower = keyword.strip().lower()
    text_lower = text.lower()
    if " " in kw_lower:
        return kw_lower in text_lower
    if re.search(r"(?:^|\W)" + re.escape(kw_lower) + r"(?:\W|$)", text_lower):
        return True
    return False


def _find_tickers(text: str) -> list[str]:
    found = TICKER_PATTERN.findall(text)
    return [t for t in found if t.upper() in WELL_KNOWN_TICKERS
            or t.upper().replace(".", "") in WELL_KNOWN_TICKERS]


def classify(text: str) -> RoutingDecision:  # pylint: disable=too-many-return-statements
    """Classifica una richiesta utente nella label di routing appropriata.

    Priorità: ticker > skill_updater > book_to_skill > trade > graphify > coder > simple.
    """
    tickers = _find_tickers(text)
    if tickers:
        return RoutingDecision(
            label=RoutingLabel.TRADE,
            reason=f"ticker detected: {', '.join(tickers)}",
        )

    text_lower = text.lower()

    for kw in TRADE_EXACT:
        if kw in text_lower:
            return RoutingDecision(
                label=RoutingLabel.TRADE, reason=f"trade exact keyword: {kw}"
            )

    result = _check_keyword_group(
        SKILL_UPDATER_KEYWORDS, text_lower, RoutingLabel.SKILL_UPDATER,
        "skill updater keyword",
    )
    if result:
        return result

    result = _check_keyword_group(
        BOOK_TO_SKILL_KEYWORDS, text_lower, RoutingLabel.BOOK_TO_SKILL,
        "book-to-skill keyword",
    )
    if result:
        return result

    for kw in TRADE_KEYWORDS:
        if _word_boundary_match(kw, text):
            return RoutingDecision(
                label=RoutingLabel.TRADE, reason=f"trade keyword: {kw}"
            )

    result = _check_keyword_group(
        GRAPHIFY_EXACT, text_lower, RoutingLabel.GRAPHIFY,
        "graphify exact keyword",
    )
    if result:
        return result

    result = _check_keyword_group(
        GRAPHIFY_KEYWORDS, text_lower, RoutingLabel.GRAPHIFY,
        "graphify keyword",
    )
    if result:
        return result

    result = _check_keyword_group(
        CODER_KEYWORDS, text_lower, RoutingLabel.CODER, "coder keyword",
    )
    if result:
        return result

    return RoutingDecision(
        label=RoutingLabel.SIMPLE, reason="no routing keyword matched — handle directly"
    )


def _check_keyword_group(
    keywords: list[str],
    text_lower: str,
    label: RoutingLabel,
    reason_prefix: str,
) -> RoutingDecision | None:
    """Cerca match di keyword in un gruppo; restituisce la decisione o None."""
    for kw in keywords:
        if kw.lower() in text_lower:
            return RoutingDecision(label=label, reason=f"{reason_prefix}: {kw}")
    return None


class RouterClassifier:
    """Classificatore che replica le regole keyword-based del router di OpenCode."""

    def classify(self, text: str) -> RoutingDecision:
        """Classifica una richiesta utente e restituisce label + motivazione."""
        return classify(text)

    def batch_classify(self, texts: list[str]) -> list[RoutingDecision]:
        """Classifica una lista di richieste in batch."""
        return [self.classify(t) for t in texts]
