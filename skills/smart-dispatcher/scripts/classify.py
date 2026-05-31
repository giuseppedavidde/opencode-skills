#!/usr/bin/env python3
"""
classify.py — Natural language → orchestrator command translation.
Prende una richiesta in italiano/inglese e restituisce intent + parametri + comando orchestrator.
"""

import re
import json
import sys
import argparse

# ── Intent Keywords ──────────────────────────────────────────

INTENT_KEYWORDS = {
    "market_scan": {
        "it": [r'scan\w*', r'screening', r'mercat\w+', r'cerca ticker',
               r'ticker da (comprare|analizzare)', r'accumulazion\w+',
               r'setup', r'opportunit'],
        "en": [r'market scan', r'scan\w*', r'screening', r'find stocks',
               r'accumulation', r'setups?', r'tickers? to (watch|buy|analyze)',
               r'what to buy'],
        "boost": 0.5
    },
    "deep_dive": {
        "it": [r'analizz\w+', r'deep dive', r'cosa far\w+',
               r'cosa fare (con|di|su)', r'verdict', r'parere\w+',
               r'giudizi\w+', r'investment thesis', r'dovrei (comprare|vendere|tenere)'],
        "en": [r'analy\w+', r'deep dive', r'what to do with',
               r'verdict', r'opinion on', r'should i (buy|sell|hold)',
               r'investment thesis'],
        "boost": 0.5
    },
    "options_suggest": {
        "it": [r'opzioni\w*', r'opzioni su', r'strategia opzioni',
               r'covered call', r'(put|call)\w*'],
        "en": [r'options?\s+on', r'options?\s+strategy',
               r'suggest options?', r'covered call', r'\bput\b', r'\bcall\b'],
        "boost": 0.6
    },
    "wsb_detect": {
        "it": [r'\bwsb\b', r'wallstreetbets', r'pump\w*', r'pomp\w+',
               r'meme stock', r'meme', r'\bfomo\b', r'radar wsb',
               r'cosa pompano'],
        "en": [r'\bwsb\b', r'wallstreetbets', r'pump\w*', r'meme stock',
               r'meme', r'\bfomo\b', r'wsb radar', r"what's pumping",
               r'squeeze'],
        "boost": 0.6
    },
    "data_fetch": {
        "it": [r'fetch', r'prendi (dati|quotazion\w+|prezz\w+)',
               r'dati (di|su)', r'quotazion\w+', r'prezz\w+ (di|azione)'],
        "en": [r'fetch', r'get (data|price|quote)',
               r'price of', r'quote', r'stock price', r'market data',
               r'financial data'],
        "boost": 0.5
    },
    "full_pipeline": {
        "it": [r'cosa (comprare|acquistare) (oggi|ora)',
               r'migliori occasioni', r'migliori setup',
               r'wsb.*analisi', r'wallstreetbets.*analizz'],
        "en": [r'what to buy (today|now)',
               r'best opportunities? (today|now)',
               r'best setups? today',
               r'wsb.*analyz', r'wallstreetbets.*analyz'],
        "boost": 0.7
    }
}

# ── Market Aliases ───────────────────────────────────────────

MARKET_ALIASES = {
    # Italian → English → universe
    "nasdaq": "us_tech",
    "qqq": "us_tech",
    "tecnologici": "us_tech",
    "tech": "us_tech",
    "nyse": "us_large",
    "s&p": "us_large",
    "sp500": "us_large",
    "usa": "us_large",
    "america": "us_large",
    "americano": "us_large",
    "americani": "us_large",
    "stati uniti": "us_large",
    "united states": "us_large",
    "us": "us_large",
    "italia": "italy",
    "italy": "italy",
    "italiano": "italy",
    "milano": "italy",
    "milan": "italy",
    "mib": "italy",
    "ftse mib": "italy",
    "piazza affari": "italy",
    "germania": "germany",
    "germany": "germany",
    "tedesco": "germany",
    "german": "germany",
    "dax": "germany",
    "francoforte": "germany",
    "frankfurt": "germany",
    "francia": "france",
    "france": "france",
    "francese": "france",
    "parigi": "france",
    "paris": "france",
    "cac": "france",
    "cac 40": "france",
    "inghilterra": "uk",
    "uk": "uk",
    "londra": "uk",
    "london": "uk",
    "ftse": "uk",
    "ftse 100": "uk",
    "spagna": "spain",
    "spain": "spain",
    "spagnolo": "spain",
    "madrid": "spain",
    "ibex": "spain",
    "ibex 35": "spain",
    "europa": "all_eu",
    "europe": "all_eu",
    "europeo": "all_eu",
    "europei": "all_eu",
    "eu": "all_eu",
    "mondo": "all",
    "world": "all",
    "globale": "all",
    "global": "all",
    "tutto": "all",
    "all": "all",
    "tutti": "all",
    "mercati globali": "all",
}

UNIVERSE_EXPANSION = {
    "all_eu": ["italy", "germany", "france", "uk", "spain"],
    "all": ["us_large", "us_tech", "italy", "germany", "france", "uk", "spain"],
}

# ── Regex Patterns ───────────────────────────────────────────

TOP_RE = re.compile(
    r'(?:top|best|migliori?|primi?|prime?|miglior)\s*(\d+)',
    re.IGNORECASE
)

TICKER_RE = re.compile(
    r'\b([A-Za-z]{1,5}(?:\.(?:MI|DE|PA|L|MC))?)\b'
)

MARKET_WORDS = set(MARKET_ALIASES.keys())


def normalize(text: str) -> str:
    """Lowercase, normalize spaces."""
    return re.sub(r'\s+', ' ', text.lower().strip())


def extract_top(text: str) -> int:
    """Extract top N from text. Returns 15 if not found."""
    m = TOP_RE.search(text)
    if m:
        return int(m.group(1))
    return 15


def extract_tickers(text: str) -> list[str]:
    """Extract stock ticker symbols from text."""
    found = TICKER_RE.findall(text.upper())
    # Filter out common words that match ticker pattern
    skip_words = {
        # Italian
        'A', 'I', 'O', 'U', 'DE', 'PA', 'L', 'MC',
        'PER', 'CON', 'CHE', 'UNA', 'DUE', 'TRE', 'SONO', 'DEL',
        'DELLA', 'DEGLI', 'DELLE', 'SUL', 'COSA', 'FARE', 'SU',
        'NON', 'MA', 'SE', 'TI', 'SI', 'MI', 'LO', 'LA', 'LE',
        'GLI', 'NE', 'CI', 'VI', 'HA', 'HO', 'HANNO', 'HAI',
        'DI', 'E', 'ED', 'IL', 'UN', 'UNA', 'UNO',
        'DATI', 'PREZZO', 'QUOTAZIONE', 'OGGI', 'ORA', 'COME',
        'QUALI', 'QUANTO', 'DOVE', 'QUANDO', 'MEGLIO', 'SOLO',
        'ANCHE', 'PIU', 'POI', 'GIA', 'TUTTI', 'TUTTO', 'MOLTO',
        'TROPPO', 'ALTRO', 'QUESTO', 'QUELLO', 'STESSO', 'PRIMO',
        'ULTIMO', 'NUOVO', 'VECCHIO', 'GRANDE', 'PICCOLO',
        # English
        'A', 'AN', 'THE', 'OF', 'IN', 'ON', 'AT', 'TO', 'FOR',
        'BY', 'WITH', 'FROM', 'UP', 'ABOUT', 'INTO', 'OVER',
        'ALL', 'TOP', 'BEST', 'NEW', 'OLD', 'BIG', 'LOW', 'HIGH',
        'BUY', 'SELL', 'GET', 'SET', 'RUN', 'TOP', 'BEST', 'PER',
        'AND', 'OR', 'NOT', 'BUT', 'YET', 'SO', 'IF', 'AS',
        'NOW', 'HERE', 'THERE', 'WHEN', 'WHAT', 'WHY', 'HOW',
        'MANY', 'MORE', 'SOME', 'SUCH', 'ONLY', 'VERY', 'JUST',
        'ALSO', 'EVEN', 'STILL', 'ALREADY', 'ALWAYS', 'NEVER',
        'NASDAQ', 'NYSE', 'DAX', 'CAC', 'MIB', 'FTSE', 'IBEX',
        'WSB', 'SPA', 'USA', 'EUROPA', 'MONDO', 'GLOBALE',
        'ITALY', 'GERMANY', 'FRANCE', 'SPAIN', 'UK',
        'ITALIA', 'GERMANIA', 'FRANCIA', 'SPAGNA',
    }
    suffix_pattern = re.compile(r'\.(MI|DE|PA|L|MC)$')
    filtered = []
    for t in found:
        has_suffix = bool(suffix_pattern.search(t))
        bare = suffix_pattern.sub('', t)
        if len(bare) == 1 and not has_suffix:
            continue
        if t in skip_words or bare in skip_words:
            continue
        filtered.append(t)
    return filtered


def extract_markets(text: str) -> list[str]:
    """Extract market/universe names from text."""
    found = set()
    lowered = text.lower()

    # Check for multi-word aliases first
    for phrase, universe in MARKET_ALIASES.items():
        if phrase in lowered:
            found.add(universe)

    if not found:
        return []

    # Expand compound universes
    expanded = []
    for u in found:
        if u in UNIVERSE_EXPANSION:
            expanded.extend(UNIVERSE_EXPANSION[u])
        else:
            expanded.append(u)

    # Deduplicate while preserving order
    seen = set()
    result = []
    for u in expanded:
        if u not in seen:
            seen.add(u)
            result.append(u)

    return result


def classify_intent(text: str) -> tuple[str, float]:
    """
    Classify intent from text. Returns (intent, confidence).
    """
    lowered = text.lower()
    scores = {}

    for intent, keywords in INTENT_KEYWORDS.items():
        score = 0.0
        for lang in ["it", "en"]:
            for pattern in keywords[lang]:
                if re.search(pattern, lowered):
                    score += keywords["boost"]
        if score > 0:
            scores[intent] = score

    if not scores:
        return "unknown", 0.0

    # Pick highest scoring intent
    best = max(scores, key=scores.get)
    return best, min(scores[best], 1.0)


def classify(text: str) -> dict:
    """
    Main classification function.

    Args:
        text: User's natural language request

    Returns:
        dict with intent, params, confidence, orchestrator_cmd
    """
    normalized = normalize(text)
    intent, confidence = classify_intent(text)

    markets = extract_markets(text)
    tickers = extract_tickers(text)
    top = extract_top(text)

    params = {}
    orchestrator_cmd = None

    if intent == "market_scan":
        if not markets and tickers:
            # If user passed tickers instead of market names, use custom tickers
            params["custom_tickers"] = tickers
            items = ",".join(tickers)
            split_by = "ticker"
        elif markets:
            params["markets"] = markets
            items = ",".join(markets)
            split_by = "market"
        else:
            params["markets"] = ["all"]
            items = "all"
            split_by = "market"
            confidence = max(confidence, 0.4)

        params["top"] = top
        orchestrator_cmd = (
            f"--skills market-accumulation-scanner "
            f"--items {items} --split-by {split_by} --top {top}"
        )

    elif intent == "deep_dive":
        if not tickers:
            # Maybe they mentioned markets but want analysis
            if markets:
                return {
                    "intent": "market_scan",
                    "params": {"markets": markets, "top": top},
                    "confidence": 0.6,
                    "orchestrator_cmd": (
                        f"--skills market-accumulation-scanner "
                        f"--items {','.join(markets)} --split-by market --top {top}"
                    ),
                    "note": "Reclassified as market_scan (no tickers found)"
                }
            return {
                "intent": "deep_dive",
                "params": {},
                "confidence": 0.0,
                "orchestrator_cmd": None,
                "error": "No tickers found. Please specify tickers."
            }

        params["tickers"] = tickers
        params["top"] = min(top, len(tickers))
        orchestrator_cmd = (
            f"--skills stock-crypto-analysis "
            f"--items {','.join(tickers)} --split-by ticker --top {params['top']}"
        )

    elif intent == "options_suggest":
        if not tickers:
            return {
                "intent": "options_suggest",
                "params": {},
                "confidence": 0.0,
                "error": "No tickers found. Please specify a ticker."
            }
        params["tickers"] = tickers
        orchestrator_cmd = (
            f"--skills options-strategy-suggestions "
            f"--items {','.join(tickers)} --split-by ticker"
        )

    elif intent == "wsb_detect":
        params = {}
        orchestrator_cmd = "--skills wallstreetbets-pump-detect"

    elif intent == "data_fetch":
        if not tickers:
            return {
                "intent": "data_fetch",
                "params": {},
                "confidence": 0.0,
                "error": "No tickers found. Please specify tickers."
            }
        params["tickers"] = tickers
        orchestrator_cmd = (
            f"--skills market-data-fetch "
            f"--items {','.join(tickers)} --split-by ticker --merge concat"
        )

    elif intent == "full_pipeline":
        params["top"] = top
        orchestrator_cmd = (
            f"--pipeline "
            f"--phase-1 \"wallstreetbets-pump-detect --top {top}\" "
            f"--phase-2 \"stock-crypto-analysis --split-by ticker\" "
            f"--phase-3 \"options-strategy-suggestions --split-by ticker\""
        )

    else:
        # Fallback: try to detect what user wants from keywords
        if tickers and not markets:
            # Probably wants deep dive
            intent = "deep_dive"
            confidence = 0.4
            params["tickers"] = tickers
            params["top"] = min(top, len(tickers))
            orchestrator_cmd = (
                f"--skills stock-crypto-analysis "
                f"--items {','.join(tickers)} --split-by ticker --top {params['top']}"
            )
        elif markets:
            intent = "market_scan"
            confidence = 0.4
            params["markets"] = markets
            params["top"] = top
            orchestrator_cmd = (
                f"--skills market-accumulation-scanner "
                f"--items {','.join(markets)} --split-by market --top {top}"
            )
        else:
            return {
                "intent": "unknown",
                "params": {},
                "confidence": 0.0,
                "error": "Could not determine intent. Try: 'scan NASDAQ', 'analyze DBK.DE', 'options on AAPL'"
            }

    return {
        "intent": intent,
        "params": params,
        "confidence": round(confidence, 2),
        "orchestrator_cmd": orchestrator_cmd,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Classify a natural language request into orchestrator command"
    )
    parser.add_argument("prompt", nargs="*", help="User prompt (or use --pipe)")
    parser.add_argument("--pipe", action="store_true",
                        help="Read prompt from stdin")
    parser.add_argument("--format", choices=["json", "text"], default="json",
                        help="Output format")

    args = parser.parse_args()

    if args.pipe or not args.prompt:
        text = sys.stdin.read().strip()
    else:
        text = " ".join(args.prompt)

    if not text:
        print(json.dumps({
            "error": "No input provided.",
            "intent": "unknown",
            "confidence": 0.0,
            "orchestrator_cmd": None
        }))
        sys.exit(1)

    result = classify(text)

    if args.format == "text":
        print(f"Intent:       {result['intent']}")
        print(f"Confidence:   {result['confidence']}")
        print(f"Params:       {json.dumps(result.get('params', {}))}")
        print(f"Error:        {result.get('error', '—')}")
        print(f"Orchestrator: {result.get('orchestrator_cmd', '—')}")
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
