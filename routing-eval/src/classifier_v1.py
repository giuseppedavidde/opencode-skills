"""Classifier that replicates the OpenCode router's keyword-based routing rules.

v2: Contextual disambiguation — coding intent overrides generic trade keywords.

Input: user text (Italian or English).
Output: RoutingLabel + reason (triggering keyword + rule that won).
"""

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

TRADE_EXACT: list[str] = [
    "dxy",
    "vix",
    "iv rank",
    "iv percentile",
    "ivr",
    "nvda",
]

# --- Phase 1: TRADE_STRONG (options/Greeks/explicit trading actions) ---
# These are trading terms that are NEVER generic — they only appear in trading context

TRADE_STRONG_KEYWORDS: list[str] = [
    "opzioni", "options",
    "strike",
    "call ",
    "put ",
    "spread",
    "greche", "greeks",
    "delta", "gamma", "theta", "vega",
    "scadenza", "expiry",
    "DTE",
    "roll ",
    "rolling",
    "hedging",
    "repair", "riparare",
    "cosa faccio con", "what to do with",
    "strategia opzioni", "what options strategy",
    "option chain", "option data",
    "long/short su", "long su", "short su",
    "iv rank", "iv percentile", "ivr",
]

# --- Phase 2: STRONG CODER signals ---
# These override ALL trade keywords (including TRADE_STRONG) when the
# overall intent is to write/modify code. The keywords must be specific
# enough to not match general conversation.

STRONG_CODER_PHRASES: list[str] = [
    "fai in modo che",
    "nel codice",
    "nel mio codice",
    "nel tuo codice",
    "nel file",
    "in questo file",
    "nel progetto",
    "devi modificare",
    "devi implementare",
    "devi scrivere",
    "devi creare",
    "devi aggiungere",
    "devi fixare",
    "passa al punto",
    "passiamo al punto",
    "partiamo con il punto",
    "procedi con il punto",
    "procedi con punto",
    "procediamo a implementare",
    "prepara la modifica",
    "lavora sul file",
    "modifica il file",
    "modifica il codice",
    "crea un modulo",
    "crea un file",
    "crea un sistema",
    "scrivi un backtest",
    "scrivere un backtest",
    "backtest di",
    "backtest della",
    "backtest del",
    "backtest per",
    "integralo questo",
    "integrarlo questo",
]

STRONG_CODER_VERBS: list[str] = [
    "implementa ",
    "implement ",
    "refactoring",
    "refactor",
    "modifica ",
    "modify ",
    "debugga",
    "debug this",
    "fix this ",
    "fix bug",
    "fixa ",
    "aggiungi feature",
    "add feature",
    "scrivi test",
    "write test",
    "scrivi unit test",
    "write unit test",
    "scrivi codice",
    "write code",
]

# --- Phase 3: TRADE_GENERIC (overridden by strong coding) ---

TRADE_GENERIC_KEYWORDS: list[str] = [
    "stock", "ticker",
    "posizione", "position",
    "analisi tecnica", "technical analysis",
    "portfolio",
    "mercato", "market",
    "macro", "buy ", "sell ",
    "prezzo", "price",
    "entry ", "exit ",
    "strategy", "strategia",
    "analizza ", "analisi di ",
    "scan ", "scanner", "scan del mercato", "scansione",
    "come gestire",
    "chart", "grafico", "candlestick", "supporto", "resistenza",
    "RSI", "MACD", "EMA", "SMA", "Bollinger", "volume profile",
    "Wyckoff", "VPA", "order flow", "orderflow",
    "trade", "trading", "trader",
    "Bali", "TS-MOM", "Bakshi", "LGBM",
    "fetch stock", "fetch data", "fetch market",
]

# --- Phase 4: GRAPHIFY (unchanged) ---

GRAPHIFY_KEYWORDS: list[str] = [
    "graph ", "grafo", "graphify", "knowledge graph",
    "mappa ", "visualizza", "mappa del codice",
    "graph this", "build graph", "analyze repo",
    "analizza codice", "/graphify",
    "path between", "explain node", "community detection",
    "god nodes", "surprising connections", "graph query",
]

GRAPHIFY_EXACT: list[str] = [
    "graphify",
    "knowledge graph",
    "/graphify",
]

# --- SKILL_UPDATER (unchanged) ---

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

# --- BOOK_TO_SKILL (unchanged) ---

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

# --- Phase 5: CODER_GENERIC (fallback) ---

CODER_KEYWORDS: list[str] = [
    "refactoring", "refactor",
    "implementa ", "implement ",
    "add feature", "new feature",
    "multi-file", "multiple files",
    "architecture change", "architectur",
    "new module",
    "write test", "scrivi test",
    "debug this", "debugga",
    "algorithm implementation", "implementazione algoritm",
    "fix this ", "fix bug",
    "refactoring del file", "write unit test",
    "crea modulo", "add module",
    "scrivi codice", "write code",
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
    """Trova ticker noti nel testo."""
    found = TICKER_PATTERN.findall(text)
    return [t for t in found if t.upper() in WELL_KNOWN_TICKERS
            or t.upper().replace(".", "") in WELL_KNOWN_TICKERS]


def _match_any(keywords: list[str], text_lower: str) -> tuple[bool, str]:
    """Return (matched, first_matching_kw)."""
    for kw in keywords:
        if kw.lower() in text_lower:
            return True, kw
    return False, ""


def _match_any_word(keywords: list[str], text: str) -> tuple[bool, str]:
    """Return (matched, first_matching_kw) with word-boundary matching."""
    for kw in keywords:
        if _word_boundary_match(kw, text):
            return True, kw
    return False, ""


def _check_group(label: RoutingLabel, keywords: list[str],
                 text_lower: str, prefix: str) -> RoutingDecision | None:
    for kw in keywords:
        if kw.lower() in text_lower:
            return RoutingDecision(label=label, reason=f"{prefix}: {kw}")
    return None


def _has_strong_coder_signal(text: str) -> tuple[bool, str]:
    """Check for unambiguous coding intent signals."""
    text_lower = text.lower()

    matched, kw = _match_any(STRONG_CODER_PHRASES, text_lower)
    if matched:
        return True, f"coder_strong_phrase: {kw}"

    matched, kw = _match_any_word(STRONG_CODER_VERBS, text)
    if matched:
        return True, f"coder_strong_verb: {kw}"

    return False, ""


def classify(text: str) -> RoutingDecision:  # pylint: disable=too-many-return-statements
    """Classifica con disambiguazione contestuale coding vs trade.

    Priorità:
      1. Ticker detection              -> TRADE (always)
      2. TRADE_EXACT                   -> TRADE
      3. SKILL_UPDATER                 -> SKILL_UPDATER
      4. BOOK_TO_SKILL                 -> BOOK_TO_SKILL
      5. STRONG CODER intent           -> CODER (overrides ALL trade)
      6. TRADE_STRONG (options/Greeks) -> TRADE
      7. TRADE_GENERIC                 -> TRADE (if no coder context)
      8. GRAPHIFY                      -> GRAPHIFY
      9. CODER_GENERIC (fallback)      -> CODER
     10. SIMPLE
    """
    text_lower = text.lower()

    # 1. Ticker detection (always wins)
    tickers = _find_tickers(text)
    if tickers:
        return RoutingDecision(
            label=RoutingLabel.TRADE,
            reason=f"ticker detected: {', '.join(tickers)}",
        )

    # 2. TRADE_EXACT
    matched, kw = _match_any(TRADE_EXACT, text_lower)
    if matched:
        return RoutingDecision(
            label=RoutingLabel.TRADE,
            reason=f"trade exact keyword: {kw}",
        )

    # 3. SKILL_UPDATER
    matched, kw = _match_any(SKILL_UPDATER_KEYWORDS, text_lower)
    if matched:
        return RoutingDecision(
            label=RoutingLabel.SKILL_UPDATER,
            reason=f"skill updater keyword: {kw}",
        )

    # 4. BOOK_TO_SKILL
    matched, kw = _match_any(BOOK_TO_SKILL_KEYWORDS, text_lower)
    if matched:
        return RoutingDecision(
            label=RoutingLabel.BOOK_TO_SKILL,
            reason=f"book-to-skill keyword: {kw}",
        )

    # 5. STRONG CODER intent (overrides *all* trade keywords)
    is_coder, reason = _has_strong_coder_signal(text)
    if is_coder:
        return RoutingDecision(
            label=RoutingLabel.CODER,
            reason=reason + " > trade keywords",
        )

    # 6. TRADE_STRONG (options/Greeks/explicit trading)
    matched, kw = _match_any_word(TRADE_STRONG_KEYWORDS, text)
    if matched:
        return RoutingDecision(
            label=RoutingLabel.TRADE,
            reason=f"trade_strong: {kw}",
        )

    # 7. TRADE_GENERIC keywords
    matched, kw = _match_any_word(TRADE_GENERIC_KEYWORDS, text)
    if matched:
        return RoutingDecision(
            label=RoutingLabel.TRADE,
            reason=f"trade_generic: {kw}",
        )

    # 8. GRAPHIFY exact, then keywords
    result = _check_group(
        RoutingLabel.GRAPHIFY, GRAPHIFY_EXACT, text_lower,
        "graphify exact keyword",
    )
    if result:
        return result

    result = _check_group(
        RoutingLabel.GRAPHIFY, GRAPHIFY_KEYWORDS, text_lower,
        "graphify keyword",
    )
    if result:
        return result

    # 9. CODER_GENERIC fallback
    result = _check_group(
        RoutingLabel.CODER, CODER_KEYWORDS, text_lower,
        "coder keyword",
    )
    if result:
        return result

    # 10. SIMPLE
    return RoutingDecision(
        label=RoutingLabel.SIMPLE,
        reason="no routing keyword matched — handle directly",
    )


class RouterClassifier:
    """Classificatore con disambiguazione contestuale coding/trade."""

    def classify(self, text: str) -> RoutingDecision:
        """Classifica una richiesta utente e restituisce label + motivazione."""
        return classify(text)

    def batch_classify(self, texts: list[str]) -> list[RoutingDecision]:
        """Classifica una lista di richieste in batch."""
        return [self.classify(t) for t in texts]
