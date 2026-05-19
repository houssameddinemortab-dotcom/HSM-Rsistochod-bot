"""
strategy.py
-----------
Logique d'analyse XAUUSD — Confluence assouplie et réaliste.

Conditions BUY (toutes requises) :
  ✅ RSI < RSI_OVERSOLD        (ex. < 40 sur 5min)
  ✅ Stoch %K < STOCH_OVERSOLD (ex. < 25) — %D affiché en diagnostic
  ✅ Prix dans un Bullish Order Block (ATR × 0.8, tolérance 50%)

Conditions SELL (toutes requises) :
  ✅ RSI > RSI_OVERBOUGHT       (ex. > 60)
  ✅ Stoch %K > STOCH_OVERBOUGHT (ex. > 75)
  ✅ Prix dans un Bearish Order Block

Chaque cycle envoie un message de DIAGNOSTIC Telegram même sans confluence,
pour permettre de suivre les valeurs en temps réel.
"""

import logging
from typing import Literal

import capital_tracker
from config import (
    RSI_PERIOD,
    STOCH_K_PERIOD, STOCH_D_PERIOD, STOCH_SLOWING,
    RSI_OVERSOLD, RSI_OVERBOUGHT,
    STOCH_OVERSOLD, STOCH_OVERBOUGHT,
    OB_ATR_MULTIPLIER, OB_TOLERANCE,
)

logger = logging.getLogger(__name__)

Signal = Literal["BUY", "SELL", "NEUTRAL"]
Trend  = Literal["BULLISH", "BEARISH", "NEUTRAL"]

RISK_PERCENT = 1.0
TP_RATIO     = 2.0
SL_PIPS      = 15.0


# ════════════════════════════════════════════════════════════════════════════
# 1. INDICATEURS
# ════════════════════════════════════════════════════════════════════════════

def calculate_rsi(candles: list[dict], period: int = RSI_PERIOD) -> float | None:
    """RSI de Wilder."""
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


def detect_order_blocks(
    candles:        list[dict],
    atr_multiplier: float = OB_ATR_MULTIPLIER,
) -> list[dict]:
    """
    Détecte les Order Blocks.
    Seuil impulsion : corps > ATR × OB_ATR_MULTIPLIER (0.8 par défaut).
    Retourne les 5 OB les plus récents.
    """
    ordered   = list(reversed(candles))
    atr       = _calculate_atr(candles)
    threshold = atr * atr_multiplier
    obs       = []

    for i in range(1, len(ordered) - 1):
        c     = ordered[i]
        nc    = ordered[i + 1]
        nbody = abs(nc["close"] - nc["open"])
        body  = abs(c["close"]  - c["open"])

        is_bear_c  = c["close"]  < c["open"]
        is_bull_c  = c["close"]  > c["open"]
        is_bull_nc = nc["close"] > nc["open"]
        is_bear_nc = nc["close"] < nc["open"]

        if is_bear_c and is_bull_nc and nbody >= threshold:
            obs.append({
                "type": "BULLISH", "high": c["high"], "low": c["low"],
                "datetime": c["datetime"], "body_size": round(body, 2),
                "retested": False,
            })
        elif is_bull_c and is_bear_nc and nbody >= threshold:
            obs.append({
                "type": "BEARISH", "high": c["high"], "low": c["low"],
                "datetime": c["datetime"], "body_size": round(body, 2),
                "retested": False,
            })

    recent = obs[-5:] if len(obs) > 5 else obs
    logger.debug("OB détectés : %d | ATR=%.2f | seuil=%.2f", len(recent), atr, threshold)
    return recent


def is_price_at_order_block(
    price:        float,
    order_blocks: list[dict],
    ob_type:      str,
    tolerance:    float = OB_TOLERANCE,
) -> dict | None:
    """Vérifie si le prix reteste un OB du type demandé."""
    for ob in reversed(order_blocks):
        if ob["type"] != ob_type:
            continue
        tol   = (ob["high"] - ob["low"]) * tolerance
        low_z = ob["low"]  - tol
        hi_z  = ob["high"] + tol
        if low_z <= price <= hi_z:
            ob["retested"] = True
            logger.debug("OB %s retest : prix=%.2f dans [%.2f – %.2f]", ob_type, price, low_z, hi_z)
            return ob
    return None


# ════════════════════════════════════════════════════════════════════════════
# 4. DIAGNOSTIC — état de chaque condition (pour le log et le message Telegram)
# ════════════════════════════════════════════════════════════════════════════

def build_diagnostic(
    rsi:     float | None,
    stoch_k: float | None,
    stoch_d: float | None,
    price:   float,
    obs:     list[dict],
) -> dict:
    """
    Évalue chaque condition individuellement et retourne un état détaillé.
    Permet de comprendre pourquoi la confluence est validée ou non.

    Returns:
        dict: {
            rsi_ok, stoch_ok, ob_buy, ob_sell,
            rsi_val, stoch_k_val, stoch_d_val,
            ob_buy_zone, ob_sell_zone,
            missing  (liste des conditions manquantes)
        }
    """
    rsi_buy_ok    = rsi    is not None and rsi    < RSI_OVERSOLD
    rsi_sell_ok   = rsi    is not None and rsi    > RSI_OVERBOUGHT
    stoch_buy_ok  = stoch_k is not None and stoch_k < STOCH_OVERSOLD
    stoch_sell_ok = stoch_k is not None and stoch_k > STOCH_OVERBOUGHT

    ob_buy_match  = is_price_at_order_block(price, obs, "BULLISH")
    ob_sell_match = is_price_at_order_block(price, obs, "BEARISH")

    # Liste des OB disponibles pour info
    ob_bull_zones = [(o["low"], o["high"]) for o in obs if o["type"] == "BULLISH"]
    ob_bear_zones = [(o["low"], o["high"]) for o in obs if o["type"] == "BEARISH"]

    # Conditions manquantes côté BUY
    missing_buy = []
    if not rsi_buy_ok:
        missing_buy.append(f"RSI={rsi:.1f} (besoin < {RSI_OVERSOLD})" if rsi else "RSI=N/A")
    if not stoch_buy_ok:
        missing_buy.append(f"Stoch K={stoch_k:.1f} (besoin < {STOCH_OVERSOLD})" if stoch_k else "Stoch=N/A")
    if not ob_buy_match:
        zones_str = ", ".join(f"[{l:.1f}–{h:.1f}]" for l, h in ob_bull_zones) or "aucun"
        missing_buy.append(f"OB Bullish: prix={price:.2f} hors zones {zones_str}")

    # Conditions manquantes côté SELL
    missing_sell = []
    if not rsi_sell_ok:
        missing_sell.append(f"RSI={rsi:.1f} (besoin > {RSI_OVERBOUGHT})" if rsi else "RSI=N/A")
    if not stoch_sell_ok:
        missing_sell.append(f"Stoch K={stoch_k:.1f} (besoin > {STOCH_OVERBOUGHT})" if stoch_k else "Stoch=N/A")
    if not ob_sell_match:
        zones_str = ", ".join(f"[{l:.1f}–{h:.1f}]" for l, h in ob_bear_zones) or "aucun"
        missing_sell.append(f"OB Bearish: prix={price:.2f} hors zones {zones_str}")

    return {
        "rsi_buy_ok":    rsi_buy_ok,
        "rsi_sell_ok":   rsi_sell_ok,
        "stoch_buy_ok":  stoch_buy_ok,
        "stoch_sell_ok": stoch_sell_ok,
        "ob_buy_match":  ob_buy_match,
        "ob_sell_match": ob_sell_match,
        "ob_bull_zones": ob_bull_zones,
        "ob_bear_zones": ob_bear_zones,
        "missing_buy":   missing_buy,
        "missing_sell":  missing_sell,
    }


# ════════════════════════════════════════════════════════════════════════════
# 5. CONFLUENCE
# ════════════════════════════════════════════════════════════════════════════

def _check_confluence(
    rsi: float | None, stoch_k: float | None, stoch_d: float | None,
    price: float, order_blocks: list[dict],
    diag: dict,
) -> tuple[Signal, dict | None]:
    """
    Confluence : RSI + Stoch %K + Order Block.
    Le %D est affiché en diagnostic mais ne bloque plus le signal.
    """
    if rsi is None or stoch_k is None:
        return "NEUTRAL", None

    if diag["rsi_buy_ok"] and diag["stoch_buy_ok"] and diag["ob_buy_match"]:
        logger.info("✅ BUY | RSI=%.1f | K=%.1f | OB=%s",
                    rsi, stoch_k, diag["ob_buy_match"]["datetime"])
        return "BUY", diag["ob_buy_match"]

    if diag["rsi_sell_ok"] and diag["stoch_sell_ok"] and diag["ob_sell_match"]:
        logger.info("✅ SELL | RSI=%.1f | K=%.1f | OB=%s",
                    rsi, stoch_k, diag["ob_sell_match"]["datetime"])
        return "SELL", diag["ob_sell_match"]

    return "NEUTRAL", None


# ════════════════════════════════════════════════════════════════════════════
# 6. CALCUL D'ENTRÉE
# ════════════════════════════════════════════════════════════════════════════

def calculate_entry(signal: Signal, price: float, ob: dict) -> dict:
    """Paramètres d'entrée basés sur le capital actuel."""
    capital  = capital_tracker.get_capital()
    risk_usd = round(capital * RISK_PERCENT / 100, 2)

    ob_dist  = ob["high"] - ob["low"]
    sl_dist  = max(ob_dist, SL_PIPS * 0.01)

    if signal == "BUY":
        entry = price
        sl    = round(ob["low"]  - sl_dist * 0.1, 2)
        tp    = round(entry + (entry - sl) * TP_RATIO, 2)
    else:
        entry = price
        sl    = round(ob["high"] + sl_dist * 0.1, 2)
        tp    = round(entry - (sl - entry) * TP_RATIO, 2)

    sl_dist_real     = abs(entry - sl)
    lot_size         = round(risk_usd / (sl_dist_real * 100), 2) if sl_dist_real > 0 else 0.01
    lot_size         = max(lot_size, 0.01)
    potential_profit = round(lot_size * sl_dist_real * 100 * TP_RATIO, 2)

    return {
        "entry":            round(entry, 2),
        "sl":               sl,
        "tp":               tp,
        "lot_size":         lot_size,
        "risk_usd":         risk_usd,
        "potential_profit": potential_profit,
        "rr_ratio":         TP_RATIO,
        "capital_before":   capital,
    }


# ════════════════════════════════════════════════════════════════════════════
# 7. POINT D'ENTRÉE PRINCIPAL
# ════════════════════════════════════════════════════════════════════════════

def analyze_market(candles: list[dict]) -> dict:
    """
    Analyse complète. Retourne toujours le diagnostic complet,
    et entry_params uniquement si confluence validée.
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

    diag             = build_diagnostic(rsi, stoch_k, stoch_d, price, order_blocks)
    signal, ob_match = _check_confluence(rsi, stoch_k, stoch_d, price, order_blocks, diag)

    entry_params = None
    if signal in ("BUY", "SELL") and ob_match:
        entry_params = calculate_entry(signal, price, ob_match)

    # Log diagnostic complet à chaque cycle
    logger.info(
        "DIAG | Prix=%.2f | RSI=%.1f [%s] | K=%.1f [%s] | OBs=%d | Signal=%s",
        price,
        rsi     or 0, "✅" if (diag["rsi_buy_ok"] or diag["rsi_sell_ok"]) else "❌",
        stoch_k or 0, "✅" if (diag["stoch_buy_ok"] or diag["stoch_sell_ok"]) else "❌",
        len(order_blocks),
        signal,
    )
    if signal == "NEUTRAL":
        logger.info("BUY manque : %s", " | ".join(diag["missing_buy"])  or "—")
        logger.info("SELL manque: %s", " | ".join(diag["missing_sell"]) or "—")

    return {
        "signal":       signal,
        "trend":        trend,
        "rsi":          rsi,
        "stoch_k":      stoch_k,
        "stoch_d":      stoch_d,
        "order_blocks": order_blocks,
        "ob_matched":   ob_match,
        "price":        price,
        "datetime":     dt,
        "entry_params": entry_params,
        "diagnostic":   diag,   # ← transmis à telegram_bot pour le message de veille
    }


def _empty_result() -> dict:
    return {
        "signal": "NEUTRAL", "trend": "NEUTRAL",
        "rsi": None, "stoch_k": None, "stoch_d": None,
        "order_blocks": [], "ob_matched": None,
        "price": 0.0, "datetime": "N/A",
        "entry_params": None, "diagnostic": {},
    }
