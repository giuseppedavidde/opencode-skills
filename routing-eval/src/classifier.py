"""Classifier che replica le regole di routing keyword-based del router OpenCode.

v5: Standalone verb refinement — i verbi generici (scrivi/write, crea/create,
     aggiungi/add, sviluppa/develop) attivano CODER SOLO con oggetto code-ish
     (script, modulo, funzione, file, test, backtest, API, codice, estensione).
     "scrivi una mail" e "crea un appuntamento" restano SIMPLE.

v4: Action-verb discriminator — il verbo d'azione (implementa/modiﬁca/scrivi)
    determina la priorità, non la forza della keyword trading.
    BUILD intent vince su TUTTE le keyword trading, forti incluse.

Priorità:
  1. SKILL_UPDATER
  2. BOOK_TO_SKILL
  3. GRAPHIFY
  4. BUILD_CODER (verbi di coding — vince su ticker + trade_strong)
     - Frasi build e verbi forti: incondizionati
     - Verbi standalone: richiedono oggetto code-ish
  5. Ticker detection → TRADE
  6. TRADE_EXACT → TRADE
  7. ANALYSIS_TRADE (verbi analisi + trade_strong senza build verb) → TRADE
  8. Web research + non-ticker → SIMPLE
  9. TRADE_GENERIC → TRADE
 10. CODER_GENERIC → CODER
 11. SIMPLE

Input: user text (Italian or English).
Output: RoutingLabel + reason (triggering keyword + rule che ha vinto).
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

# --- Phase 1: SKILL_UPDATER (prima di GRAPHIFY per catturare "aggiorna graphify") ---

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

# --- Phase 2: BOOK_TO_SKILL ---

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

# --- Phase 3: GRAPHIFY (sopra coding — graph vince su "nel mio codice") ---

GRAPHIFY_KEYWORDS: list[str] = [
    "graph ", "grafo", "graphify", "knowledge graph",
    "mappa ", "visualizza", "mappa del codice",
    "graph this", "build graph", "analyze repo",
    "analizza codice", "/graphify",
    "path between", "explain node", "community detection",
    "god nodes", "surprising connections", "graph query",
    "knowledge graph",
]

GRAPHIFY_EXACT: list[str] = [
    "graphify",
    "knowledge graph",
    "/graphify",
]

# --- Phase 4: BUILD_CODER — verbi di coding che vincono su TUTTO il trading ---
# Il discriminatore è il VERBO D'AZIONE: se l'utente chiede di IMPLEMENTARE/
# MODIFICARE/SCRIVERE codice, è CODER anche su Greeks/delta/opzioni/hedging.

BUILD_CODER_PHRASES: list[str] = [
    "fai in modo che",
    "nel mio codice",
    "nel tuo codice",
    "nel file",
    "al file",
    "a file",
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

# Verbi FORTI: incondizionati, sempre CODER.
STRONG_BUILD_VERBS: list[str] = [
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
    "scrivi codice",
    "write code",
    "scrivi test",
    "write test",
    "scrivi unit test",
    "write unit test",
    "aggiungi feature",
    "add feature",
]

# Verbi STANDALONE: richiedono OGGETTO CODE-ISH per attivare CODER.
STANDALONE_BUILD_VERBS: list[str] = [
    "crea ",
    "create ",
    "scrivi ",
    "write ",
    "aggiungi ",
    "add ",
    "sviluppa ",
    "develop ",
]

CODE_ISH_OBJECTS: list[str] = [
    "script", "scripts",
    "modulo", "moduli", "module", "modules",
    "funzione", "funzioni", "function", "functions",
    "classe", "classi", "class", "classes",
    "file", "files",
    "test", "tests",
    "backtest", "backtests",
    "api", "apis",
    "codice", "code",
    "libreria", "librerie", "library", "libraries",
    "plugin", "plugins",
    "applicazione", "applicazioni", "application", "applications",
    "programma", "programmi", "program", "programs",
    "algoritmo", "algoritmi", "algorithm", "algorithms",
    "web app", "web apps",
    ".py", ".ts", ".js", ".sh", ".go", ".rs", ".java", ".sql",
    ".json", ".yml", ".yaml", ".toml",
]

# --- Phase 7: ANALYSIS_TRADE ---
# Verbi di analisi + keyword trading forti (solo se nessun build verb prima).

ANALYSIS_KEYWORDS: list[str] = [
    "analizza ",
    "analisi di ",
    "valuta ",
    "cosa faccio con",
    "what to do with",
    "gestisci la mia posizione",
    "roll della mia",
    "strategia opzioni",
    "what options strategy",
    "long/short su",
    "long su ",
    "short su ",
    "scan del mercato",
    "prezzo di ",
    "price of ",
    "verifica la mia",
]

ANALYSIS_TRADE_STRONG: list[str] = [
    "opzioni",
    "options",
    "strike",
    "call ",
    "put ",
    "spread",
    "greche",
    "greeks",
    "delta",
    "gamma",
    "theta",
    "vega",
    "scadenza",
    "expiry",
    "DTE",
    "roll ",
    "rolling",
    "hedging",
    "option chain",
    "option data",
    "iv rank",
    "iv percentile",
    "ivr",
]

# --- Phase 8: WEB RESEARCH ---

WEB_RESEARCH_PHRASES: list[str] = [
    "cerca su web",
    "cerca su internet",
    "cerca online",
    "ricerca su web",
    "ricerca online",
    "web search",
    "search the web",
    "search online",
    "look up online",
    "find online",
    "cerca il prezzo di",
    "ricerca il prezzo di",
]

WEB_COMMODITIES: set[str] = {
    "petrolio", "oro", "gas naturale", "gas",
    "oil", "gold", "natural gas",
    "argento", "silver", "rame", "copper",
    "grano", "wheat", "mais", "corn",
    "platino", "platinum", "palladio", "palladium",
}

# --- Phase 9: TRADE_GENERIC ---

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
    "scan ", "scanner", "scansione",
    "come gestire",
    "repair", "riparare",
    "chart", "grafico", "candlestick", "supporto", "resistenza",
    "RSI", "MACD", "EMA", "SMA", "Bollinger", "volume profile",
    "Wyckoff", "VPA", "order flow", "orderflow",
    "trade", "trading", "trader",
    "Bali", "TS-MOM", "Bakshi", "LGBM",
    "fetch stock", "fetch data", "fetch market",
]

# --- Phase 10: CODER_GENERIC (fallback) ---

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


def _has_code_ish_object(text: str) -> bool:
    """Check if text contains a code-ish object (script, module, function, etc.).

    For file extensions (e.g. .py, .ts): literal substring match.
    For multi-word objects (e.g. "web app"): literal substring match.
    For single-word objects: word-boundary match with optional plural suffix.
    """
    text_lower = text.lower()
    for obj in CODE_ISH_OBJECTS:
        if obj.startswith("."):
            if obj in text_lower:
                return True
        elif " " in obj:
            if obj in text_lower:
                return True
        else:
            pattern = r"(?:^|\W)" + re.escape(obj) + r"(?:\w*)(?:\W|$)"
            if re.search(pattern, text_lower):
                return True
    return False


def _has_build_coder_signal(text: str) -> tuple[bool, str]:
    """Check for BUILD/MODIFY code intent — vince su TUTTE le keyword trading.

    Priorità:
      1. Frasi build (BUILD_CODER_PHRASES) → incondizionate
      2. Verbi forti (STRONG_BUILD_VERBS) → incondizionati
      3. Verbi standalone (STANDALONE_BUILD_VERBS) → solo con oggetto code-ish
    """
    text_lower = text.lower()

    matched, kw = _match_any(BUILD_CODER_PHRASES, text_lower)
    if matched:
        return True, f"build_phrase:{kw}"

    matched, kw = _match_any_word(STRONG_BUILD_VERBS, text)
    if matched:
        return True, f"build_strong:{kw.strip()}"

    matched, kw = _match_any_word(STANDALONE_BUILD_VERBS, text)
    if matched:
        if _has_code_ish_object(text):
            return True, f"build_standalone+obj:{kw.strip()}"
        return False, ""

    return False, ""


def _has_web_research_intent(text_lower: str) -> tuple[bool, str]:
    """Check for web research intent and target type."""
    for phrase in WEB_RESEARCH_PHRASES:
        if phrase in text_lower:
            for commodity in WEB_COMMODITIES:
                if _word_boundary_match(commodity, text_lower):
                    return True, f"commodity:{commodity}"
            return True, "generic"
    return False, ""


SKILL_NAMES: set[str] = {
    "graphify", "quant-mind", "book-to-skill",
    "wyckoff-2-0", "volume-profile", "volume-price-analysis",
    "trading-against-the-crowd", "trading-in-the-zone",
    "way-of-the-turtle", "price-action-volman",
    "trades-about-to-happen", "options-playbook",
    "options-course-workbook", "options-crash-course",
    "option-volatility-pricing", "evidence-based-technical-analysis",
    "crypto-technical-analysis", "crypto-crash-course",
    "machine-learning-for-asset-managers",
    "advances-in-financial-machine-learning",
    "asset-management-factor-investing",
    "liotta-smartfood", "lgbm-trader-skill",
    "market-accumulation-scanner", "market-data-fetch",
    "options-analysis", "options-strategy-suggestions",
    "stock-crypto-analysis", "smart-dispatcher",
    "subatomic-orchestrator", "system-info",
    "pdf-ingest",
}

CONJUNCTION_PATTERN = re.compile(
    r"\b(?:e|ed|and)\b|\s*,\s*(?=[a-z])", re.IGNORECASE
)


def _count_objects(text: str, label: RoutingLabel) -> int:
    """Count independent objects in the request for multiplicity detection.

    Uses category-specific detection:
      - TRADE: count well-known tickers
      - SKILL_UPDATER: count skill names
      - CODER: count code-ish objects
      - BOOK_TO_SKILL: count file references
      - GRAPHIFY: default 1 (repos are singular)
      - SIMPLE: default 1
    """
    text_lower = text.lower()

    if label == RoutingLabel.TRADE:
        tickers = _find_tickers(text)
        return max(len(tickers), 1)

    if label == RoutingLabel.SKILL_UPDATER:
        found = [s for s in SKILL_NAMES if _word_boundary_match(s, text)]
        names = set(found)
        return max(len(names), 1)

    if label == RoutingLabel.CODER:
        count = 0
        for obj in CODE_ISH_OBJECTS:
            if obj.startswith("."):
                if obj in text_lower:
                    count += 1
            elif _word_boundary_match(obj, text):
                count += 1
        return max(count, 1)

    if label == RoutingLabel.BOOK_TO_SKILL:
        count = 0
        if ".pdf" in text_lower:
            count += 1
        if ".epub" in text_lower:
            count += 1
        if ".docx" in text_lower:
            count += 1
        if ".mobi" in text_lower:
            count += 1
        return max(count, 1)

    return 1


def _detect_multiplicity(text: str, label: RoutingLabel) -> int:
    """Detect multiplicity of independent objects in a request."""
    count = _count_objects(text, label)
    return count if count > 1 else 1


def _fmt_reason(base: str, multi: int) -> str:
    """Append multi:N flag to reason if multiplicity > 1."""
    if multi > 1:
        return f"{base} \u2192 multi:{multi}"
    return base


# pylint: disable=too-many-return-statements
def classify(text: str) -> RoutingDecision:
    """Classifica con discriminatore ACTION VERB + standalone refinement + multiplicity.

    Priorità (router reale allineato):
      1. SKILL_UPDATER
      2. BOOK_TO_SKILL
      3. GRAPHIFY
      4. BUILD_CODER \u2014 frasi/verbi forti: incondizionati;
         verbi standalone (scrivi/crea/aggiungi/sviluppa):
         SOLO con oggetto code-ish (script, modulo, funzione, file, .py...)
      5. Ticker detection \u2192 TRADE
      6. TRADE_EXACT \u2192 TRADE
      7. ANALYSIS_TRADE (verbi analisi + trade_strong senza build verb)
      8. Web research + non-ticker \u2192 SIMPLE
      9. TRADE_GENERIC \u2192 TRADE
     10. CODER_GENERIC \u2192 CODER
     11. SIMPLE
    """
    text_lower = text.lower()

    # 1. SKILL_UPDATER \u2014 prima di GRAPHIFY per "aggiorna graphify"
    matched, kw = _match_any(SKILL_UPDATER_KEYWORDS, text_lower)
    if matched:
        multi = _detect_multiplicity(text, RoutingLabel.SKILL_UPDATER)
        return RoutingDecision(
            label=RoutingLabel.SKILL_UPDATER,
            reason=_fmt_reason(f"skill_updater: {kw}", multi),
            multiplicity=multi,
        )

    # 2. BOOK_TO_SKILL
    matched, kw = _match_any(BOOK_TO_SKILL_KEYWORDS, text_lower)
    if matched:
        multi = _detect_multiplicity(text, RoutingLabel.BOOK_TO_SKILL)
        return RoutingDecision(
            label=RoutingLabel.BOOK_TO_SKILL,
            reason=_fmt_reason(f"book_to_skill: {kw}", multi),
            multiplicity=multi,
        )

    # 3. GRAPHIFY \u2014 sopra coding (graph vince su "nel mio codice")
    result = _check_group(
        RoutingLabel.GRAPHIFY, GRAPHIFY_EXACT, text_lower,
        "graphify_exact",
    )
    if result:
        multi = _detect_multiplicity(text, RoutingLabel.GRAPHIFY)
        result.multiplicity = multi
        result.reason = _fmt_reason(result.reason, multi)
        return result

    result = _check_group(
        RoutingLabel.GRAPHIFY, GRAPHIFY_KEYWORDS, text_lower,
        "graphify_kw",
    )
    if result:
        multi = _detect_multiplicity(text, RoutingLabel.GRAPHIFY)
        result.multiplicity = multi
        result.reason = _fmt_reason(result.reason, multi)
        return result

    # 4. BUILD_CODER \u2014 vince su TUTTE le keyword trading (ticker + trade_strong)
    is_coder, coder_reason = _has_build_coder_signal(text)
    if is_coder:
        multi = _detect_multiplicity(text, RoutingLabel.CODER)
        base = coder_reason + " > all_trading"
        return RoutingDecision(
            label=RoutingLabel.CODER,
            reason=_fmt_reason(base, multi),
            multiplicity=multi,
        )

    # 5. Ticker detection
    tickers = _find_tickers(text)
    if tickers:
        multi = _detect_multiplicity(text, RoutingLabel.TRADE)
        return RoutingDecision(
            label=RoutingLabel.TRADE,
            reason=_fmt_reason(f"ticker: {', '.join(tickers)}", multi),
            multiplicity=multi,
        )

    # 6. TRADE_EXACT
    matched, kw = _match_any(TRADE_EXACT, text_lower)
    if matched:
        multi = _detect_multiplicity(text, RoutingLabel.TRADE)
        return RoutingDecision(
            label=RoutingLabel.TRADE,
            reason=_fmt_reason(f"trade_exact: {kw}", multi),
            multiplicity=multi,
        )

    # 7. ANALYSIS_TRADE \u2014 verbi analisi + keyword trading forti
    matched, kw = _match_any(ANALYSIS_KEYWORDS, text_lower)
    if matched:
        multi = _detect_multiplicity(text, RoutingLabel.TRADE)
        return RoutingDecision(
            label=RoutingLabel.TRADE,
            reason=_fmt_reason(f"analysis_verb: {kw}", multi),
            multiplicity=multi,
        )

    matched, kw = _match_any_word(ANALYSIS_TRADE_STRONG, text)
    if matched:
        multi = _detect_multiplicity(text, RoutingLabel.TRADE)
        return RoutingDecision(
            label=RoutingLabel.TRADE,
            reason=_fmt_reason(f"trade_strong: {kw} (no build verb)", multi),
            multiplicity=multi,
        )

    # 8. Web research + non-ticker \u2192 SIMPLE
    is_web, web_target = _has_web_research_intent(text_lower)
    if is_web:
        return RoutingDecision(
            label=RoutingLabel.SIMPLE,
            reason=f"web_research(target={web_target}) \u2192 SIMPLE",
            multiplicity=1,
        )

    # 9. TRADE_GENERIC
    matched, kw = _match_any_word(TRADE_GENERIC_KEYWORDS, text)
    if matched:
        multi = _detect_multiplicity(text, RoutingLabel.TRADE)
        return RoutingDecision(
            label=RoutingLabel.TRADE,
            reason=_fmt_reason(f"trade_generic: {kw}", multi),
            multiplicity=multi,
        )

    # 10. CODER_GENERIC fallback
    result = _check_group(
        RoutingLabel.CODER, CODER_KEYWORDS, text_lower,
        "coder_kw",
    )
    if result:
        multi = _detect_multiplicity(text, RoutingLabel.CODER)
        result.multiplicity = multi
        result.reason = _fmt_reason(result.reason, multi)
        return result

    # 11. SIMPLE
    return RoutingDecision(
        label=RoutingLabel.SIMPLE,
        reason="no routing keyword \u2014 handle directly",
        multiplicity=1,
    )


class RouterClassifier:
    """Classificatore con discriminatore action-verb + standalone refinement + multiplicity (v6)."""

    def classify(self, text: str) -> RoutingDecision:
        """Classifica una richiesta utente e restituisce label + motivazione."""
        return classify(text)

    def batch_classify(self, texts: list[str]) -> list[RoutingDecision]:
        """Classifica una lista di richieste in batch."""
        return [self.classify(t) for t in texts]
