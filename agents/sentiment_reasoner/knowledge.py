# # knowledge.py
# # Minimal in-code MeTTa KB (no external .metta files)

# from typing import Optional, Dict
# from hyperon import MeTTa, E, S, ValueAtom

# def initialize_knowledge_graph(m: MeTTa) -> None:
#     """
#     Seed a tiny domain KB the agent can query for thresholds, policies,
#     and notable events. We avoid external .metta files to keep the repo
#     one-command runnable for judges.
#     """

#     sp = m.space()

#     # --- Policy knobs (numbers kept readable for judges) ---
#     # target base weight, max tilt from base (absolute), clamp bounds
#     sp.add_atom(E(S("tilt-base"),      ValueAtom(0.50)))
#     sp.add_atom(E(S("tilt-max"),       ValueAtom(0.10)))
#     sp.add_atom(E(S("weight-min"),     ValueAtom(0.20)))
#     sp.add_atom(E(S("weight-max"),     ValueAtom(0.80)))

#     # how much sentiment contributes when present (0..1)
#     sp.add_atom(E(S("sentiment-weight"), ValueAtom(0.30)))

#     # liquidity gate: if |quote-1.0| > threshold -> halve tilt
#     sp.add_atom(E(S("liq-gate-threshold"), ValueAtom(0.003)))

#     # regime thresholds based on worst combined risk
#     sp.add_atom(E(S("regime-threshold"), S("YELLOW"), ValueAtom(0.35)))
#     sp.add_atom(E(S("regime-threshold"), S("RED"),    ValueAtom(0.60)))

#     # --- Example knowledge of past stablecoin incidents (illustrative) ---
#     # These are not used directly in math yet, but demonstrate how we’d
#     # keep “explanations”/context the agent can cite in rationale.
#     sp.add_atom(E(S("event"), S("DAI_2020_03_12"), S("depeg")))
#     sp.add_atom(E(S("event-note"),
#                   S("DAI_2020_03_12"),
#                   ValueAtom("Black Thursday: market crash, auctions backlog, premium >1.02")))

#     sp.add_atom(E(S("event"), S("USDC_2023_03_SVB"), S("depeg")))
#     sp.add_atom(E(S("event-note"),
#                   S("USDC_2023_03_SVB"),
#                   ValueAtom("SVB exposure scare; rapid depeg/repeg over weekend")))

# def _first_number(m: MeTTa, pattern: str) -> Optional[float]:
#     """
#     Query a single numeric value from the KB.
#     Example: pattern = "(tilt-max ?x)"
#     """
#     try:
#         res = m.run(pattern)
#         if not res:
#             return None
#         # typical string form like: "(tilt-max 0.1)" or "[[(tilt-max 0.1)]]"
#         txt = str(res[0])
#         # Pick last token and strip trailing ')'
#         val = float(txt.replace(')', ' ').split()[-1])
#         return val
#     except Exception:
#         return None

# def read_policy(m: MeTTa) -> Dict[str, float]:
#     """Fetch all numeric policy values with safe fallbacks."""
#     return {
#         "tilt_base":          _first_number(m, "(tilt-base ?x)") or 0.50,
#         "tilt_max":           _first_number(m, "(tilt-max ?x)") or 0.10,
#         "weight_min":         _first_number(m, "(weight-min ?x)") or 0.20,
#         "weight_max":         _first_number(m, "(weight-max ?x)") or 0.80,
#         "sentiment_weight":   _first_number(m, "(sentiment-weight ?x)") or 0.30,
#         "liq_gate_threshold": _first_number(m, "(liq-gate-threshold ?x)") or 0.003,
#         "thr_yellow":         _first_number(m, "(regime-threshold YELLOW ?x)") or 0.35,
#         "thr_red":            _first_number(m, "(regime-threshold RED ?x)") or 0.60,
#     }

# knowledge.py
# Minimal in-code MeTTa KB (no external .metta files)
# Expanded to a 10-coin universe + helpers to push/read peg-risk & sentiment.

from typing import Optional, Dict, Tuple, List
from hyperon import MeTTa, E, S, ValueAtom

# -------- 10-coin universe (shared by all agents) --------
COINS: Tuple[str, ...] = (
    "USDC", "USDT", "DAI", "FDUSD", "BUSD",
    "TUSD", "USDP", "PYUSD", "USDD", "GUSD"
)

def coins() -> Tuple[str, ...]:
    """Expose the coin universe to callers that don't import from other files."""
    return COINS


def initialize_knowledge_graph(m: MeTTa) -> None:
    """
    Seed a tiny domain KB the agent can query for thresholds, policies,
    assets, and notable events. We avoid external .metta files to keep the repo
    one-command runnable for judges.
    """
    sp = m.space()

    # --- Asset list (10 coins) ---
    for c in COINS:
        sp.add_atom(E(S("asset"), S(c)))

    # --- Policy knobs (numbers kept readable for judges) ---
    # target base weight, max tilt from base (absolute), clamp bounds
    sp.add_atom(E(S("tilt-base"),      ValueAtom(0.50)))
    sp.add_atom(E(S("tilt-max"),       ValueAtom(0.10)))
    sp.add_atom(E(S("weight-min"),     ValueAtom(0.20)))
    sp.add_atom(E(S("weight-max"),     ValueAtom(0.80)))

    # how much sentiment contributes when present (0..1)
    sp.add_atom(E(S("sentiment-weight"), ValueAtom(0.30)))

    # liquidity gate: if |quote-1.0| > threshold -> halve tilt
    sp.add_atom(E(S("liq-gate-threshold"), ValueAtom(0.003)))

    # regime thresholds based on worst combined risk
    sp.add_atom(E(S("regime-threshold"), S("YELLOW"), ValueAtom(0.35)))
    sp.add_atom(E(S("regime-threshold"), S("RED"),    ValueAtom(0.60)))

    # --- Example knowledge of past stablecoin incidents (illustrative) ---
    # These are not used directly in math yet, but demonstrate how we’d
    # keep “explanations”/context the agent can cite in rationale.
    sp.add_atom(E(S("event"), S("DAI_2020_03_12"), S("depeg")))
    sp.add_atom(E(S("event-note"),
                  S("DAI_2020_03_12"),
                  ValueAtom("Black Thursday: market crash, auctions backlog, premium >1.02")))

    sp.add_atom(E(S("event"), S("USDC_2023_03_SVB"), S("depeg")))
    sp.add_atom(E(S("event-note"),
                  S("USDC_2023_03_SVB"),
                  ValueAtom("SVB exposure scare; rapid depeg/repeg over weekend")))
    # PATCH A — add explicit links & severities (paste under existing event atoms)
    sp.add_atom(E(S("event-on"), S("DAI_2020_03_12"), S("DAI")))
    sp.add_atom(E(S("event-severity"), S("DAI_2020_03_12"), ValueAtom(0.25)))

    sp.add_atom(E(S("event-on"), S("USDC_2023_03_SVB"), S("USDC")))
    sp.add_atom(E(S("event-severity"), S("USDC_2023_03_SVB"), ValueAtom(0.20)))


# ------------------------------
# Safe numeric readers (single)
# ------------------------------
def _first_number(m: MeTTa, pattern: str) -> Optional[float]:
    """
    Query a single numeric value from the KB.
    Example: pattern = "(tilt-max ?x)"
    """
    try:
        res = m.run(pattern)
        if not res:
            return None
        # typical forms look like: "(tilt-max 0.1)" or "[[(tilt-max 0.1)]]"
        txt = str(res[0])
        # Pick last token and strip trailing ')'
        val = float(txt.replace(')', ' ').split()[-1])
        return val
    except Exception:
        return None


def _first_number_for_coin(m: MeTTa, head: str, coin: str) -> Optional[float]:
    """
    Query a single numeric value keyed by coin.
    Example: head='peg-risk' -> pattern "(peg-risk USDC ?x)"
    """
    try:
        res = m.run(f"({head} {coin} ?x)")
        if not res:
            return None
        txt = str(res[0])
        val = float(txt.replace(')', ' ').split()[-1])
        return val
    except Exception:
        return None


# ------------------------------
# Policy snapshot
# ------------------------------
def read_policy(m: MeTTa) -> Dict[str, float]:
    """Fetch all numeric policy values with safe fallbacks."""
    return {
        "tilt_base":          _first_number(m, "(tilt-base ?x)") or 0.50,
        "tilt_max":           _first_number(m, "(tilt-max ?x)") or 0.10,
        "weight_min":         _first_number(m, "(weight-min ?x)") or 0.20,
        "weight_max":         _first_number(m, "(weight-max ?x)") or 0.80,
        "sentiment_weight":   _first_number(m, "(sentiment-weight ?x)") or 0.30,
        "liq_gate_threshold": _first_number(m, "(liq-gate-threshold ?x)") or 0.003,
        "thr_yellow":         _first_number(m, "(regime-threshold YELLOW ?x)") or 0.35,
        "thr_red":            _first_number(m, "(regime-threshold RED ?x)") or 0.60,
    }


# ------------------------------
# Peg-risk & sentiment I/O
# ------------------------------
def push_peg_snapshot(m: MeTTa, risk_map: Dict[str, float], regime: str) -> None:
    """
    Write per-coin peg risks and current regime into the KB.
    risk_map: coin -> 0..1
    """
    sp = m.space()
    sp.add_atom(E(S("peg-regime"), S(str(regime))))
    for c in COINS:
        r = float(risk_map.get(c, 0.40))  # fallback mid-ish
        sp.add_atom(E(S("peg-risk"), S(c), ValueAtom(r)))


def push_sentiment_scores(m: MeTTa, score_map: Dict[str, float]) -> None:
    """
    Write per-coin sentiment scores ([-1,1]) into the KB.
    """
    sp = m.space()
    for c in COINS:
        s = float(score_map.get(c, 0.0))
        sp.add_atom(E(S("sentiment"), S(c), ValueAtom(s)))


def read_peg_risk(m: MeTTa) -> Dict[str, float]:
    """
    Read per-coin peg risk from the KB; returns defaults if not present.
    """
    out: Dict[str, float] = {}
    for c in COINS:
        out[c] = _first_number_for_coin(m, "peg-risk", c) or 0.40
    return out


def read_sentiment(m: MeTTa) -> Dict[str, float]:
    """
    Read per-coin sentiment from the KB; returns 0 if not present.
    """
    out: Dict[str, float] = {}
    for c in COINS:
        out[c] = _first_number_for_coin(m, "sentiment", c) or 0.0
    return out


def read_regime(m: MeTTa) -> str:
    """
    Read latest peg regime string; UNKNOWN if absent.
    """
    try:
        res = m.run("(peg-regime ?x)")
        if not res:
            return "UNKNOWN"
        txt = str(res[0])
        # fetch the token after 'peg-regime'
        parts = txt.replace(')', ' ').replace('(', ' ').split()
        # e.g. ["peg-regime", "ALERT"]
        return parts[-1] if parts else "UNKNOWN"
    except Exception:
        return "UNKNOWN"
    
# PATCH B — helper to read per-coin event penalties (put near other readers)
def read_event_penalties(m: MeTTa) -> Dict[str, float]:
    """
    Sum per-coin penalties from historical events.
    Uses atoms: (event-on <EVENT> <COIN>) and (event-severity <EVENT> <float>)
    Returns coin -> [0..1] penalty. If no events, 0.0.
    """
    penalties: Dict[str, float] = {c: 0.0 for c in COINS}
    try:
        # Get all (event-on ?e ?c)
        on_pairs = m.run("(event-on ?e ?c)") or []
        # Normalize results to tuples of (event, coin)
        pairs: List[Tuple[str, str]] = []
        for r in on_pairs:
            txt = str(r).replace("(", " ").replace(")", " ").split()
            # expected: ["event-on", "<EVENT>", "<COIN>"]
            if len(txt) >= 3:
                pairs.append((txt[-2], txt[-1]))

        # Map severities for events
        sev_map: Dict[str, float] = {}
        for ev, _coin in pairs:
            res = m.run(f"(event-severity {ev} ?x)") or []
            if res:
                stxt = str(res[0]).replace(")", " ").split()
                try:
                    sev_map[ev] = float(stxt[-1])
                except Exception:
                    sev_map[ev] = 0.1  # safe default
            else:
                sev_map[ev] = 0.1

        # Accumulate per coin
        for ev, coin in pairs:
            if coin in penalties:
                penalties[coin] += sev_map.get(ev, 0.1)

        # Clamp 0..1
        for c in penalties:
            penalties[c] = max(0.0, min(1.0, penalties[c]))
    except Exception:
        pass
    return penalties