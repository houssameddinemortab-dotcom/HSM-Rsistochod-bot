"""
strategy.py
-----------
Logique d'analyse de marché pour XAUUSD.
Contient :
  - RSI (Wilder)
  - Stochastique (%K / %D)
  - Tendance par structure de marché (HH/HL/LH/LL)
  - Placeholder Order Blocks
  - analyze_market() → signal + diagnostic complet
"""

import logging
from typing import Literal

from config import (
    RSI_PERIOD,
    STOCH_K_PERIOD, STOCH_D_PERIOD, STOCH_SLOWING,
    RSI_OVERSOLD, RSI_OVERBOUGHT,
    STOCH_OVERSOLD, STOCH_OVERBOUGHT,
)

logger  = logging.getLogger(__name__)
Signal  = Literal["BUY", "SELL", "NEUTRAL"]
Trend   = Literal["BULLISH", "BEARISH", "NEUTRAL"]


# ════════════════════════════════════════════════════════════════════════════
# 1. INDICATEURS TECHNIQUES
# ════════════════════════════════════════════════════════════════════════════

def calculate_rsi(candles: list[dict], period: int = RSI_PERIOD) -> float | None:
    """
    RSI de Wilder sur les clôtures.

    Args:
        candles : Bougies parsées, plus récente en premier.
        period  : Période (défaut 14).

    Returns:
        float [0-100] ou None si données insuffisantes.
    """
    closes = [c["close"] for c in reversed(candles)]

    if len(closes) < period + 1:
        logger.warning("RSI : données insuffisantes (%d bougies, besoin %d)", len(closes), period + 1)
        return None

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains  = [max(d, 0.0) for d in deltas]
    losses = [abs(min(d, 0.0)) for d in deltas]

    avg_gain = sum(gains[:period])  / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i])  / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0

    rs  = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return round(rsi, 2)


def calculate_stochastic(
    candles:  list[dict],
    k_period: int = STOCH_K_PERIOD,
    d_period: int = STOCH_D_PERIOD,
    slowing:  int = STOCH_SLOWING,
) -> dict | None:
    """
    Oscillateur Stochastique — retourne %K et %D.

    Args:
        candles  : Bougies parsées, plus récente en premier.
        k_period : Période lookback %K brut.
        d_period : Période lissage %D.
        slowing  : Ralentissement %K.

    Returns:
        {"k": float, "d": float} ou None si données insuffisantes.
    """
    ordered = list(reversed(candles))

    if len(ordered) < k_period + slowing + d_period - 2:
        logger.warning("Stoch : données insuffisantes (%d bougies)", len(ordered))
        return None

    raw_k = []
    for i in range(k_period - 1, len(ordered)):
        window  = ordered[i - k_period + 1 : i + 1]
        hh      = max(c["high"] for c in window)
        ll      = min(c["low"]  for c in window)
        close   = ordered[i]["close"]
        raw_k.append(50.0 if hh == ll else (close - ll) / (hh - ll) * 100)

    # Lissage %K
    sk = []
    for i in range(slowing - 1, len(raw_k)):
        sk.append(sum(raw_k[i - slowing + 1 : i + 1]) / slowing)

    if len(sk) < d_period:
        return None

    k_val = sk[-1]
    d_val = sum(sk[-d_period:]) / d_period
    return {"k": round(k_val, 2), "d": round(d_val, 2)}


# ════════════════════════════════════════════════════════════════════════════
# 2. TENDANCE — Structure de marché HH / HL / LH / LL
# ════════════════════════════════════════════════════════════════════════════

def detect_trend(candles: list[dict], lookback: int = 20) -> Trend:
    """
    Analyse la structure de marché sur les N dernières bougies.

    BULLISH : Higher High + Higher Low
    BEARISH : Lower High  + Lower Low
    NEUTRAL : structure mixte

    Args:
        candles  : Bougies parsées, plus récente en premier.
        lookback : Fenêtre d'analyse.

    Returns:
        "BULLISH" | "BEARISH" | "NEUTRAL"
    """
    window = list(reversed(candles[:lookback]))

    if len(window) < 4:
        return "NEUTRAL"

    mid     = len(window) // 2
    prev_h  = max(c["high"] for c in window[:mid])
    prev_l  = min(c["low"]  for c in window[:mid])
    last_h  = max(c["high"] for c in window[mid:])
    last_l  = min(c["low"]  for c in window[mid:])

    hh = last_h > prev_h
    hl = last_l > prev_l
    lh = last_h < prev_h
    ll = last_l < prev_l

    if hh and hl:
        return "BULLISH"
    if lh and ll:
        return "BEARISH"
    return "NEUTRAL"


# ════════════════════════════════════════════════════════════════════════════
# 3. ORDER BLOCKS — Placeholders (à implémenter en V6.1)
# ════════════════════════════════════════════════════════════════════════════

def detect_order_blocks(candles: list[dict]) -> list[dict]:
    """
    [PLACEHOLDER] Détecte les Order Blocks institutionnels.

    Un Bullish OB = dernière bougie baissière avant un fort mouvement haussier.
    Un Bearish OB = dernière bougie haussière avant un fort mouvement baissier.

    TODO V6.1 :
      - Calculer l'ATR pour définir "fort mouvement" (ex. > 1.5 × ATR).
      - Identifier la bougie précédant l'impulsion comme OB.
      - Vérifier le retest : le prix est-il en train de revenir sur la zone ?
      - Retourner : {"type", "high", "low", "datetime", "retested"}

    Returns:
        list[dict]: Vide jusqu'à implémentation.
    """
    logger.debug("detect_order_blocks() : placeholder — non implémenté.")
    return []


def is_price_at_order_block(
    price:        float,
    order_blocks: list[dict],
    tolerance:    float = 0.5,
) -> dict | None:
    """
    [PLACEHOLDER] Vérifie si le prix actuel teste un Order Block.

    TODO : parcourir order_blocks, tester si price est dans [low-tol, high+tol].

    Returns:
        dict OB ou None.
    """
    return None


# ════════════════════════════════════════════════════════════════════════════
# 4. SIGNAL — Confluence des indicateurs
# ════════════════════════════════════════════════════════════════════════════

def _compute_signal(
    trend:   Trend,
    rsi:     float | None,
    stoch_k: float | None,
) -> Signal:
    """
    Génère le signal final par confluence.

    Règles actuelles (squelette — à enrichir) :
      BUY  : BULLISH + RSI survendu  + Stoch survendu
      SELL : BEARISH + RSI suracheté + Stoch suracheté
      NEUTRAL : tout le reste

    TODO V6.1 : ajouter confluence Order Blocks, Ichimoku, divergences RSI.
    """
    if rsi is None or stoch_k is None:
        return "NEUTRAL"

    if trend == "BULLISH" and rsi < RSI_OVERSOLD and stoch_k < STOCH_OVERSOLD:
        return "BUY"
    if trend == "BEARISH" and rsi > RSI_OVERBOUGHT and stoch_k > STOCH_OVERBOUGHT:
        return "SELL"
    return "NEUTRAL"


# ════════════════════════════════════════════════════════════════════════════
# 5. POINT D'ENTRÉE PRINCIPAL
# ════════════════════════════════════════════════════════════════════════════

def analyze_market(candles: list[dict]) -> dict:
    """
    Analyse complète du marché XAUUSD.

    Args:
        candles: Bougies OHLCV parsées, plus récente en premier.

    Returns:
        dict: {
            signal, trend, rsi, stoch_k, stoch_d,
            order_blocks, price, datetime
        }
    """
    if not candles:
        logger.error("analyze_market() : liste de bougies vide.")
        return {
            "signal": "NEUTRAL", "trend": "NEUTRAL",
            "rsi": None, "stoch_k": None, "stoch_d": None,
            "order_blocks": [], "price": 0.0, "datetime": "N/A",
        }

    last          = candles[0]
    current_price = last["close"]
    current_dt    = last["datetime"]

    trend        = detect_trend(candles)
    rsi          = calculate_rsi(candles)
    stoch        = calculate_stochastic(candles)
    order_blocks = detect_order_blocks(candles)

    stoch_k = stoch["k"] if stoch else None
    stoch_d = stoch["d"] if stoch else None

    signal = _compute_signal(trend, rsi, stoch_k)

    logger.info(
        "SIGNAL=%s | Trend=%s | Prix=%.2f | RSI=%.2f | Stoch K=%.2f D=%.2f",
        signal, trend, current_price,
        rsi     or 0,
        stoch_k or 0,
        stoch_d or 0,
    )

    return {
        "signal":       signal,
        "trend":        trend,
        "rsi":          rsi,
        "stoch_k":      stoch_k,
        "stoch_d":      stoch_d,
        "order_blocks": order_blocks,
        "price":        current_price,
        "datetime":     current_dt,
    }
