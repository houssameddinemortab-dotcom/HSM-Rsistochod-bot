"""
capital_tracker.py
------------------
Gestion du capital réel entre les cycles de trading.
Le capital est sauvegardé dans un fichier JSON local (capital.json)
pour persister entre les redémarrages du bot (Railway inclus).

Fonctions principales :
  - get_capital()          → capital actuel
  - apply_tp(profit)       → met à jour après un Take Profit
  - apply_sl(loss)         → met à jour après un Stop Loss
  - get_history()          → historique des trades
  - reset_capital()        → remet à la valeur initiale
"""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Fichier de persistance ────────────────────────────────────────────────────
CAPITAL_FILE    = Path("capital.json")
INITIAL_CAPITAL = 100.0   # Capital de départ en USD


# ════════════════════════════════════════════════════════════════════════════
# INITIALISATION
# ════════════════════════════════════════════════════════════════════════════

def _default_state() -> dict:
    return {
        "capital":         INITIAL_CAPITAL,
        "initial_capital": INITIAL_CAPITAL,
        "total_trades":    0,
        "total_wins":      0,
        "total_losses":    0,
        "history":         [],   # liste des 20 derniers trades
    }


def _load() -> dict:
    """Charge l'état depuis capital.json, crée le fichier s'il n'existe pas."""
    if not CAPITAL_FILE.exists():
        state = _default_state()
        _save(state)
        return state
    try:
        with open(CAPITAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("capital_tracker : fichier corrompu → reset. (%s)", exc)
        state = _default_state()
        _save(state)
        return state


def _save(state: dict) -> None:
    """Sauvegarde l'état dans capital.json."""
    with open(CAPITAL_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ════════════════════════════════════════════════════════════════════════════
# LECTURE
# ════════════════════════════════════════════════════════════════════════════

def get_capital() -> float:
    """Retourne le capital actuel en USD."""
    return round(_load()["capital"], 2)


def get_state() -> dict:
    """Retourne l'état complet (capital, stats, historique)."""
    return _load()


def get_history(limit: int = 10) -> list[dict]:
    """Retourne les N derniers trades."""
    return _load()["history"][-limit:]


# ════════════════════════════════════════════════════════════════════════════
# MISE À JOUR APRÈS UN TRADE
# ════════════════════════════════════════════════════════════════════════════

def _record_trade(
    outcome:  str,    # "TP" ou "SL"
    signal:   str,    # "BUY" ou "SELL"
    entry:    float,
    sl:       float,
    tp:       float,
    pnl:      float,  # positif = gain, négatif = perte
    capital_before: float,
    capital_after:  float,
    datetime_str:   str,
) -> None:
    """Enregistre un trade dans l'historique et met à jour les stats."""
    state = _load()

    trade = {
        "datetime":       datetime_str,
        "outcome":        outcome,
        "signal":         signal,
        "entry":          entry,
        "sl":             sl,
        "tp":             tp,
        "pnl":            round(pnl, 2),
        "capital_before": round(capital_before, 2),
        "capital_after":  round(capital_after, 2),
    }

    state["capital"]      = round(capital_after, 2)
    state["total_trades"] += 1

    if outcome == "TP":
        state["total_wins"] += 1
    else:
        state["total_losses"] += 1

    # Garder les 20 derniers trades
    state["history"].append(trade)
    if len(state["history"]) > 20:
        state["history"] = state["history"][-20:]

    _save(state)
    logger.info(
        "Trade enregistré → %s %s | PnL=%.2f USD | Capital=%.2f USD",
        outcome, signal, pnl, capital_after,
    )


def apply_tp(
    signal:   str,
    entry:    float,
    sl:       float,
    tp:       float,
    profit:   float,
    dt:       str = "",
) -> dict:
    """
    Met à jour le capital après un Take Profit.

    Args:
        signal : "BUY" ou "SELL"
        entry  : Prix d'entrée
        sl     : Stop Loss
        tp     : Take Profit
        profit : Gain réalisé en USD (positif)
        dt     : Datetime du trade

    Returns:
        dict: {capital_before, capital_after, pnl, outcome}
    """
    state          = _load()
    capital_before = state["capital"]
    capital_after  = capital_before + profit
    dt             = dt or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    _record_trade("TP", signal, entry, sl, tp, profit, capital_before, capital_after, dt)

    return {
        "outcome":        "TP",
        "capital_before": round(capital_before, 2),
        "capital_after":  round(capital_after,  2),
        "pnl":            round(profit, 2),
    }


def apply_sl(
    signal:   str,
    entry:    float,
    sl:       float,
    tp:       float,
    loss:     float,
    dt:       str = "",
) -> dict:
    """
    Met à jour le capital après un Stop Loss.

    Args:
        loss : Perte réalisée en USD (valeur positive, sera soustraite)

    Returns:
        dict: {capital_before, capital_after, pnl, outcome}
    """
    state          = _load()
    capital_before = state["capital"]
    capital_after  = max(capital_before - loss, 0.0)   # ne descend pas sous 0
    dt             = dt or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    _record_trade("SL", signal, entry, sl, tp, -loss, capital_before, capital_after, dt)

    return {
        "outcome":        "SL",
        "capital_before": round(capital_before, 2),
        "capital_after":  round(capital_after,  2),
        "pnl":            round(-loss, 2),
    }


def reset_capital(new_capital: float = INITIAL_CAPITAL) -> None:
    """Remet le capital à la valeur initiale (ou à new_capital)."""
    state = _default_state()
    state["capital"] = round(new_capital, 2)
    _save(state)
    logger.info("Capital réinitialisé à %.2f USD", new_capital)


# ════════════════════════════════════════════════════════════════════════════
# STATS
# ════════════════════════════════════════════════════════════════════════════

def get_stats() -> dict:
    """
    Retourne les statistiques de performance du bot.

    Returns:
        dict: {capital, initial_capital, pnl_total, win_rate,
               total_trades, total_wins, total_losses}
    """
    state   = _load()
    capital = state["capital"]
    initial = state["initial_capital"]
    trades  = state["total_trades"]
    wins    = state["total_wins"]

    return {
        "capital":         round(capital, 2),
        "initial_capital": round(initial, 2),
        "pnl_total":       round(capital - initial, 2),
        "pnl_pct":         round((capital - initial) / initial * 100, 1) if initial else 0,
        "total_trades":    trades,
        "total_wins":      wins,
        "total_losses":    state["total_losses"],
        "win_rate":        round(wins / trades * 100, 1) if trades else 0.0,
    }
