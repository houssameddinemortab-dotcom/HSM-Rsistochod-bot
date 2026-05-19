"""
telegram_bot.py
---------------
2 types de messages envoyés toutes les 5 minutes :

  1. MESSAGE DE VEILLE (toujours) :
     - Prix, RSI, Stoch, OBs détectés
     - Checklist des conditions BUY/SELL avec ✅/❌
     - Ce qui manque pour déclencher un signal

  2. MESSAGE DE SIGNAL (si confluence validée) :
     - Paramètres d'entrée complets
     - Capital actuel + si TP + si SL

  3. MESSAGE RÉSULTAT (si TP ou SL atteint) :
     - PnL + nouveau capital + stats globales
"""

import logging
import requests

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    RSI_OVERSOLD, RSI_OVERBOUGHT,
    STOCH_OVERSOLD, STOCH_OVERBOUGHT,
)
import capital_tracker

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
TIMEOUT = 10

_SIGNAL_EMOJI = {"BUY": "🟢", "SELL": "🔴"}
_TREND_EMOJI  = {"BULLISH": "📈", "BEARISH": "📉", "NEUTRAL": "➡️"}
_OB_EMOJI     = {"BULLISH": "🟦", "BEARISH": "🟧"}


# ════════════════════════════════════════════════════════════════════════════
# 1. ENVOI BRUT
# ════════════════════════════════════════════════════════════════════════════

def send_message(text: str, parse_mode: str = "HTML") -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("TOKEN ou CHAT_ID manquant.")
        return False
    url     = TELEGRAM_API_URL.format(token=TELEGRAM_BOT_TOKEN)
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode}
    try:
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        logger.error("Timeout Telegram.")
        return False
    except requests.exceptions.RequestException as exc:
        logger.error("Erreur réseau Telegram : %s", exc)
        return False
    if resp.status_code != 200:
        logger.error("HTTP %d — %s", resp.status_code, resp.text[:200])
        return False
    return True


# ════════════════════════════════════════════════════════════════════════════
# 2. MESSAGE DE VEILLE — diagnostic toutes les 5 minutes
# ════════════════════════════════════════════════════════════════════════════

def format_watch_message(a: dict) -> str:
    """
    Message envoyé à CHAQUE cycle (avec ou sans confluence).
    Montre l'état de chaque condition pour comprendre pourquoi
    le signal est déclenché ou non.
    """
    price   = a.get("price",    0.0)
    dt      = a.get("datetime", "N/A")
    trend   = a.get("trend",    "NEUTRAL")
    rsi     = a.get("rsi")
    stoch_k = a.get("stoch_k")
    stoch_d = a.get("stoch_d")
    obs     = a.get("order_blocks", [])
    diag    = a.get("diagnostic", {})
    signal  = a.get("signal", "NEUTRAL")
    te      = _TREND_EMOJI.get(trend, "➡️")

    rsi_s = f"{rsi:.1f}"    if rsi     is not None else "N/A"
    k_s   = f"{stoch_k:.1f}" if stoch_k is not None else "N/A"
    d_s   = f"{stoch_d:.1f}" if stoch_d is not None else "N/A"

    # ── En-tête ──────────────────────────────────────────────────────────────
    if signal == "NEUTRAL":
        header = f"👁️ <b>XAUUSD — Veille</b>  |  {dt}"
    else:
        se = _SIGNAL_EMOJI.get(signal, "⚪")
        header = f"{se} <b>SIGNAL {signal} — XAUUSD</b>  |  {dt}"

    msg = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Prix :</b> {price:.2f}  {te} <b>Tendance :</b> {trend}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>📊 Indicateurs</b>\n"
        f"  RSI  (14) : <b>{rsi_s}</b>  "
        f"<i>[survente &lt;{RSI_OVERSOLD} | surachat &gt;{RSI_OVERBOUGHT}]</i>\n"
        f"  Stoch  %K : <b>{k_s}</b>  %D : <b>{d_s}</b>  "
        f"<i>[&lt;{STOCH_OVERSOLD} / &gt;{STOCH_OVERBOUGHT}]</i>\n"
    )

    # ── Order Blocks détectés ─────────────────────────────────────────────────
    bull_obs = [o for o in obs if o["type"] == "BULLISH"]
    bear_obs = [o for o in obs if o["type"] == "BEARISH"]

    if bull_obs or bear_obs:
        msg += f"━━━━━━━━━━━━━━━━━━━━\n<b>🧱 Order Blocks actifs</b>\n"
        for o in bull_obs:
            msg += f"  🟦 Bull OB : [{o['low']:.2f} – {o['high']:.2f}]\n"
        for o in bear_obs:
            msg += f"  🟧 Bear OB : [{o['low']:.2f} – {o['high']:.2f}]\n"
    else:
        msg += f"  🧱 <i>Aucun Order Block détecté</i>\n"

    # ── Checklist confluence ──────────────────────────────────────────────────
    msg += f"━━━━━━━━━━━━━━━━━━━━\n<b>✅ Checklist BUY</b>\n"
    msg += f"  {'✅' if diag.get('rsi_buy_ok')   else '❌'} RSI < {RSI_OVERSOLD}  ({rsi_s})\n"
    msg += f"  {'✅' if diag.get('stoch_buy_ok') else '❌'} Stoch K < {STOCH_OVERSOLD}  ({k_s})\n"
    msg += f"  {'✅' if diag.get('ob_buy_match') else '❌'} Prix sur Bullish OB\n"

    msg += f"<b>✅ Checklist SELL</b>\n"
    msg += f"  {'✅' if diag.get('rsi_sell_ok')   else '❌'} RSI > {RSI_OVERBOUGHT}  ({rsi_s})\n"
    msg += f"  {'✅' if diag.get('stoch_sell_ok') else '❌'} Stoch K > {STOCH_OVERBOUGHT}  ({k_s})\n"
    msg += f"  {'✅' if diag.get('ob_sell_match') else '❌'} Prix sur Bearish OB\n"

    # ── Capital ───────────────────────────────────────────────────────────────
    capital = capital_tracker.get_capital()
    stats   = capital_tracker.get_stats()
    pnl_str = f"+{stats['pnl_total']:.2f}" if stats["pnl_total"] >= 0 else f"{stats['pnl_total']:.2f}"
    msg += (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Capital :</b> {capital:.2f} USD  "
        f"|  <b>PnL :</b> {pnl_str} USD  "
        f"|  <b>WR :</b> {stats['win_rate']:.0f}%\n"
    )

    return msg


# ════════════════════════════════════════════════════════════════════════════
# 3. MESSAGE DE SIGNAL — confluence validée
# ════════════════════════════════════════════════════════════════════════════

def format_signal_message(a: dict) -> str:
    """Message complet uniquement si BUY ou SELL — avec paramètres d'entrée."""
    signal = a["signal"]
    ob     = a.get("ob_matched")
    ep     = a.get("entry_params")
    se     = _SIGNAL_EMOJI.get(signal, "⚪")

    msg = f"\n{se} <b>━━ ENTRÉE {signal} CONFIRMÉE ━━</b>\n"

    if ob:
        oe = _OB_EMOJI.get(ob["type"], "🟫")
        msg += f"{oe} OB {ob['type']} : [{ob['low']:.2f} – {ob['high']:.2f}]\n"

    if ep:
        capital_now   = ep["capital_before"]
        capital_if_tp = round(capital_now + ep["potential_profit"], 2)
        capital_if_sl = round(capital_now - ep["risk_usd"], 2)
        pct_tp        = round(ep["potential_profit"] / capital_now * 100, 1) if capital_now else 0
        pct_sl        = round(ep["risk_usd"]         / capital_now * 100, 1) if capital_now else 0
        direction     = "🔼" if signal == "BUY" else "🔽"

        msg += (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>💼 Paramètres</b>\n"
            f"  {direction} Entrée :     <b>{ep['entry']:.2f}</b>\n"
            f"  🛑 Stop Loss :   <b>{ep['sl']:.2f}</b>\n"
            f"  🎯 Take Profit : <b>{ep['tp']:.2f}</b>\n"
            f"  📦 Lot Size :    <b>{ep['lot_size']:.2f}</b>\n"
            f"  ⚖️  R/R :         1:{ep['rr_ratio']:.1f}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>💰 Capital</b>\n"
            f"  Actuel :         <b>{capital_now:.2f} USD</b>\n"
            f"  ✅ Si TP :       <b>{capital_if_tp:.2f} USD</b>  (+{pct_tp:.1f}%)\n"
            f"  ❌ Si SL :       <b>{capital_if_sl:.2f} USD</b>  (-{pct_sl:.1f}%)\n"
        )
    return msg


# ════════════════════════════════════════════════════════════════════════════
# 4. MESSAGE RÉSULTAT TP / SL
# ════════════════════════════════════════════════════════════════════════════

def format_trade_result_message(result: dict, signal: str) -> str:
    outcome        = result["outcome"]
    capital_before = result["capital_before"]
    capital_after  = result["capital_after"]
    pnl            = result["pnl"]
    pnl_pct        = round(pnl / capital_before * 100, 1) if capital_before else 0
    stats          = capital_tracker.get_stats()
    pnl_tot_str    = f"+{stats['pnl_total']:.2f}" if stats["pnl_total"] >= 0 else f"{stats['pnl_total']:.2f}"

    if outcome == "TP":
        header  = f"🎯 <b>TAKE PROFIT atteint — {signal}</b>"
        emoji   = "✅"
        pnl_str = f"+{pnl:.2f} USD (+{pnl_pct:.1f}%)"
    else:
        header  = f"🛑 <b>STOP LOSS atteint — {signal}</b>"
        emoji   = "❌"
        pnl_str = f"{pnl:.2f} USD ({pnl_pct:.1f}%)"

    return (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{emoji} <b>PnL :</b>            {pnl_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>📊 Évolution du capital</b>\n"
        f"  Avant :   {capital_before:.2f} USD\n"
        f"  Après :   <b>{capital_after:.2f} USD</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>📈 Stats globales</b>\n"
        f"  Trades : {stats['total_trades']}  |  "
        f"WR : {stats['win_rate']:.1f}%  |  "
        f"PnL total : {pnl_tot_str} USD\n"
    )


def format_error_message(context: str, error: str) -> str:
    return (
        f"⚠️ <b>XAUUSD Bot — Erreur</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 {context}\n❌ {error}"
    )


# ════════════════════════════════════════════════════════════════════════════
# 5. RACCOURCIS PRINCIPAUX
# ════════════════════════════════════════════════════════════════════════════

def notify_cycle(analysis: dict) -> bool:
    """
    Envoyé à chaque cycle (300s) :
      - Toujours : message de veille avec checklist
      - Si signal BUY/SELL : ajoute les paramètres d'entrée dans le même message
    """
    msg = format_watch_message(analysis)

    if analysis.get("signal") in ("BUY", "SELL"):
        msg += format_signal_message(analysis)
        logger.info("📨 Signal %s envoyé.", analysis["signal"])
    else:
        logger.info("👁️  Veille envoyée — pas de confluence.")

    return send_message(msg)


def notify_tp(signal: str, entry: float, sl: float, tp: float, profit: float, dt: str = "") -> bool:
    result = capital_tracker.apply_tp(signal, entry, sl, tp, profit, dt)
    return send_message(format_trade_result_message(result, signal))


def notify_sl(signal: str, entry: float, sl: float, tp: float, loss: float, dt: str = "") -> bool:
    result = capital_tracker.apply_sl(signal, entry, sl, tp, loss, dt)
    return send_message(format_trade_result_message(result, signal))


def notify_error(context: str, error: str) -> bool:
    return send_message(format_error_message(context, error))
