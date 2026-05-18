"""
strategy.py
-----------
Logique d'analyse XAUUSD.
Signal émis UNIQUEMENT si confluence complète :
  ✅ RSI en zone de survente/surachat
  ✅ Stochastique %K ET %D en zone
  ✅ Prix sur un Order Block valide

Le calcul de l'entrée utilise le capital RÉEL actuel (via capital_tracker).
"""

import logging
from typing import Literal

import capital_tracker
from config import (
    RSI_PERIOD,
    STOCH_K_PERIOD, STOCH_D_PERIOD, STOCH_SLOWING,
    RSI_OVERSOLD, RSI_OVERBOUGHT,
    STOCH_OVERSOLD, STOCH_OVERBOUGHT,
)

logger = logging.getLogger(__name__)

Signal = Literal["BUY", "SELL", "NEUTRAL"]
Trend  = Literal["BULLISH", "BEARISH", "NEUTRAL"]

# ── Paramètres risk management ────────────────────────────────────────────────
RISK_PERCENT = 1.0    # % du capital risqué par trade
TP_RATIO     = 2.0    # Risk/Reward
SL_PIPS      = 15.0   # SL fallback en pips


# ════════════════════════════════════════════════════════════════════════════
# 1. INDICATEURS TECHNIQUES
# ════════════════════════════════════════════════════════════════════════════

def calculate_rsi(candles: list[dict], period: int = RSI_PERIOD) -> float | None:
    """RSI de Wilder sur les clôtures."""
    closes = [c["close"] for c in reversed(candles)]
    if len(closes) < period + 1:
        return None

    deltas   = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains    = [max(d, 0.0) for d in deltas]
    losses   = [abs(min(d, 0.0)) for d in deltas]
    avg_gain = sum(gains[:period])  / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i])  / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    return round(100.0 - (100.0 / (1.0 + avg_gain / avg_loss)), 2)


def calculate_stochastic(
    candles:  list[dict],
    k_period: int = STOCH_K_PERIOD,
    d_period: int = STOCH_D_PERIOD,
    slowing:  int = STOCH_SLOWING,
) -> dict | None:
    """Stochastique %K et %D."""
    ordered = list(reversed(candles))
    if len(ordered) < k_period + slowing + d_period - 2:
        return None

    raw_k = []
    for i in range(k_period - 1, len(ordered)):
        window = ordered[i - k_period + 1 : i + 1]
        hh     = max(c["high"] for c in window)
        ll     = min(c["low"]  for c in window)
        close  = ordered[i]["close"]
        raw_k.append(50.0 if hh == ll else (close - ll) / (hh - ll) * 100)

    sk = []
    for i in range(slowing - 1, len(raw_k)):
        sk.append(sum(raw_k[i - slowing + 1 : i + 1]) / slowing)

    if len(sk) < d_period:
        return None

    return {"k": round(sk[-1], 2), "d": round(sum(sk[-d_period:]) / d_period, 2)}


# ════════════════════════════════════════════════════════════════════════════
# 2. TENDANCE
# ════════════════════════════════════════════════════════════════════════════

def detect_trend(candles: list[dict], lookback: int = 20) -> Trend:
    """Tendance par structure HH/HL/LH/LL."""
    window = list(reversed(candles[:lookback]))
    if len(window) < 4:
        return "NEUTRAL"

    mid    = len(window) // 2
    prev_h = max(c["high"] for c in window[:mid])
    prev_l = min(c["low"]  for c in window[:mid])
    last_h = max(c["high"] for c in window[mid:])
    last_l = min(c["low"]  for c in window[mid:])

    if last_h > prev_h and last_l > prev_l:
        return "BULLISH"
    if last_h < prev_h and last_l < prev_l:
        return "BEARISH"
    return "NEUTRAL"


# ════════════════════════════════════════════════════════════════════════════
# 3. ORDER BLOCKS
# ════════════════════════════════════════════════════════════════════════════

def _calculate_atr(candles: list[dict], period: int = 14) -> float:
    ordered = list(reversed(candles))
    if len(ordered) < 2:
        return 1.0

    trs = []
    for i in range(1, len(ordered)):
        h, l, pc = ordered[i]["high"], ordered[i]["low"], ordered[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))

    return sum(trs[-period:]) / min(len(trs), period)


def detect_order_blocks(candles: list[dict], atr_multiplier: float = 1.5) -> list[dict]:
    """
    Détecte les Order Blocks institutionnels.
    Bullish OB : bougie baissière avant forte impulsion haussière (> 1.5×ATR).
    Bearish OB : bougie haussière avant forte impulsion baissière (> 1.5×ATR).
    """
    ordered   = list(reversed(candles))
    atr       = _calculate_atr(candles)
    threshold = atr * atr_multiplier
    obs       = []

    for i in range(1, len(ordered) - 1):
        c     = ordered[i]
        nc    = ordered[i + 1]
        body  = abs(c["close"]  - c["open"])
        nbody = abs(nc["close"] - nc["open"])

        is_bear_c  = c["close"]  < c["open"]
        is_bull_c  = c["close"]  > c["open"]
        is_bull_nc = nc["close"] > nc["open"]
        is_bear_nc = nc["close"] < nc["open"]

        if is_bear_c and is_bull_nc and nbody >= threshold:
            obs.append({
                "type": "BULLISH", "high": c["high"], "low": c["low"],
                "datetime": c["datetime"], "body_size": round(body, 2), "retested": False,
            })
        elif is_bull_c and is_bear_nc and nbody >= threshold:
            obs.append({
                "type": "BEARISH", "high": c["high"], "low": c["low"],
                "datetime": c["datetime"], "body_size": round(body, 2), "retested": False,
            })

    return obs[-3:] if len(obs) > 3 else obs


def is_price_at_order_block(
    price: float, order_blocks: list[dict], ob_type: str, tolerance: float = 0.3
) -> dict | None:
    """Vérifie si le prix reteste un OB du type demandé."""
    for ob in reversed(order_blocks):
        if ob["type"] != ob_type:
            continue
        tol = (ob["high"] - ob["low"]) * tolerance
        if (ob["low"] - tol) <= price <= (ob["high"] + tol):
            ob["retested"] = True
            return ob
    return None


# ════════════════════════════════════════════════════════════════════════════
# 4. CALCUL D'ENTRÉE — capital réel depuis capital_tracker
# ════════════════════════════════════════════════════════════════════════════

def calculate_entry(signal: Signal, price: float, ob: dict) -> dict:
    """
    Calcule les paramètres d'entrée basés sur le capital ACTUEL du tracker.

    Risque = RISK_PERCENT % du capital actuel.
    SL     = sous/sur l'OB + marge.
    TP     = entrée ± (distance SL × TP_RATIO).
    Lot    = risque_usd / (distance_sl_usd × 100).

    Returns:
        dict: {entry, sl, tp, lot_size, risk_usd, potential_profit,
               rr_ratio, capital_before}
    """
    capital  = capital_tracker.get_capital()
    risk_usd = round(capital * RISK_PERCENT / 100, 2)

    ob_distance = ob["high"] - ob["low"]
    sl_distance = max(ob_distance, SL_PIPS * 0.01)

    if signal == "BUY":
        entry = price
        sl    = round(ob["low"]  - sl_distance * 0.1, 2)
        tp    = round(entry + (entry - sl) * TP_RATIO, 2)
    else:
        entry = price
        sl    = round(ob["high"] + sl_distance * 0.1, 2)
        tp    = round(entry - (sl - entry) * TP_RATIO, 2)

    sl_dist_real = abs(entry - sl)
    lot_size     = round(risk_usd / (sl_dist_real * 100), 2) if sl_dist_real > 0 else 0.01
    lot_size     = max(lot_size, 0.01)

    potential_profit = round(lot_size * sl_dist_real * 100 * TP_RATIO, 2)

    return {
        "entry":            round(entry, 2),
        "sl":               sl,
        "tp":               tp,
        "lot_size":         lot_size,
        "risk_usd":         risk_usd,
        "potential_profit": potential_profit,
        "rr_ratio":         TP_RATIO,
        "capital_before":   capital,   # capital au moment du signal
    }


# ════════════════════════════════════════════════════════════════════════════
# 5. CONFLUENCE
# ════════════════════════════════════════════════════════════════════════════

def _check_confluence(
    trend: Trend, rsi: float | None,
    stoch_k: float | None, stoch_d: float | None,
    price: float, order_blocks: list[dict],
) -> tuple[Signal, dict | None]:
    """Triple confluence RSI + Stoch (%K et %D) + Order Block."""
    if rsi is None or stoch_k is None or stoch_d is None:
        return "NEUTRAL", None

    rsi_buy   = rsi    < RSI_OVERSOLD
    stoch_buy = stoch_k < STOCH_OVERSOLD  and stoch_d < STOCH_OVERSOLD
    ob_buy    = is_price_at_order_block(price, order_blocks, "BULLISH")

    if rsi_buy and stoch_buy and ob_buy:
        logger.info("✅ Confluence BUY | RSI=%.1f | K=%.1f D=%.1f | OB=%s",
                    rsi, stoch_k, stoch_d, ob_buy["datetime"])
        return "BUY", ob_buy

    rsi_sell  = rsi    > RSI_OVERBOUGHT
    stoch_sell = stoch_k > STOCH_OVERBOUGHT and stoch_d > STOCH_OVERBOUGHT
    ob_sell    = is_price_at_order_block(price, order_blocks, "BEARISH")

    if rsi_sell and stoch_sell and ob_sell:
        logger.info("✅ Confluence SELL | RSI=%.1f | K=%.1f D=%.1f | OB=%s",
                    rsi, stoch_k, stoch_d, ob_sell["datetime"])
        return "SELL", ob_sell

    logger.info("⏳ Pas de confluence | RSI=%s | K=%s D=%s | OBs=%d",
                rsi, stoch_k, stoch_d, len(order_blocks))
    return "NEUTRAL", None


# ════════════════════════════════════════════════════════════════════════════
# 6. POINT D'ENTRÉE PRINCIPAL
# ════════════════════════════════════════════════════════════════════════════

def analyze_market(candles: list[dict]) -> dict:
    """
    Analyse complète. Signal BUY/SELL uniquement si triple confluence validée.
    entry_params inclut le capital actuel pour affichage du capital après TP/SL.
    """
    if not candles:
        return _empty_result()

    last  = candles[0]
    price = last["close"]
    dt    = last["datetime"]

    trend        = detect_trend(candles)
    rsi          = calculate_rsi(candles)
    stoch        = calculate_stochastic(candles)
    order_blocks = detect_order_blocks(candles)

    stoch_k = stoch["k"] if stoch else None
    stoch_d = stoch["d"] if stoch else None

    signal, ob_matched = _check_confluence(trend, rsi, stoch_k, stoch_d, price, order_blocks)

    entry_params = None
    if signal in ("BUY", "SELL") and ob_matched:
        entry_params = calculate_entry(signal, price, ob_matched)

    return {
        "signal":       signal,
        "trend":        trend,
        "rsi":          rsi,
        "stoch_k":      stoch_k,
        "stoch_d":      stoch_d,
        "order_blocks": order_blocks,
        "ob_matched":   ob_matched,
        "price":        price,
        "datetime":     dt,
        "entry_params": entry_params,
    }


def _empty_result() -> dict:
    return {
        "signal": "NEUTRAL", "trend": "NEUTRAL",
        "rsi": None, "stoch_k": None, "stoch_d": None,
        "order_blocks": [], "ob_matched": None,
        "price": 0.0, "datetime": "N/A", "entry_params": None,
    }
