"""
telegram_bot.py
---------------
Notifications Telegram pour XAUUSD Bot.

Messages envoyés :
  1. Signal BUY/SELL (confluence validée) → avec capital actuel + capital après TP/SL
  2. Résultat d'un trade (TP ou SL atteint) → avec PnL et nouveau capital
  3. Erreur critique
  4. Démarrage / arrêt du bot
"""

import logging
import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
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
    """Envoie un message texte au CHAT_ID configuré."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("TOKEN ou CHAT_ID manquant.")
        return False

    url     = TELEGRAM_API_URL.format(token=TELEGRAM_BOT_TOKEN)
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode}

    try:
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        logger.error("send_message() : timeout.")
        return False
    except requests.exceptions.RequestException as exc:
        logger.error("send_message() : erreur réseau → %s", exc)
        return False

    if resp.status_code != 200:
        logger.error("send_message() : HTTP %d — %s", resp.status_code, resp.text[:200])
        return False

    return True


# ════════════════════════════════════════════════════════════════════════════
# 2. FORMAT — SIGNAL D'ENTRÉE (avec capital avant + projections TP/SL)
# ════════════════════════════════════════════════════════════════════════════

def format_signal_message(a: dict) -> str:
    """
    Message de signal BUY/SELL avec :
      - Triple confluence (RSI, Stoch, OB)
      - Paramètres d'entrée pour le capital actuel
      - Capital actuel, capital si TP atteint, capital si SL atteint
    """
    signal  = a["signal"]
    trend   = a.get("trend", "NEUTRAL")
    rsi     = a.get("rsi")
    stoch_k = a.get("stoch_k")
    stoch_d = a.get("stoch_d")
    price   = a.get("price", 0.0)
    dt      = a.get("datetime", "N/A")
    ob      = a.get("ob_matched")
    ep      = a.get("entry_params")

    se = _SIGNAL_EMOJI.get(signal, "⚪")
    te = _TREND_EMOJI.get(trend, "➡️")

    rsi_s = f"{rsi:.1f}"    if rsi     is not None else "N/A"
    k_s   = f"{stoch_k:.1f}" if stoch_k is not None else "N/A"
    d_s   = f"{stoch_d:.1f}" if stoch_d is not None else "N/A"

    msg = (
        f"{se} <b>SIGNAL {signal} — XAUUSD</b>\n"
        f"🕐 {dt}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Prix :</b> {price:.2f} USD\n"
        f"{te} <b>Tendance :</b> {trend}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>✅ Triple Confluence</b>\n"
        f"📐 RSI (14) : <b>{rsi_s}</b>\n"
        f"📊 Stoch %K : <b>{k_s}</b>  |  %D : <b>{d_s}</b>\n"
    )

    # Order Block
    if ob:
        oe = _OB_EMOJI.get(ob["type"], "🟫")
        msg += (
            f"{oe} OB <b>{ob['type']}</b> : "
            f"[{ob['low']:.2f} – {ob['high']:.2f}]"
            f"  <i>({ob['datetime']})</i>\n"
        )

    # Paramètres d'entrée + capital
    if ep:
        capital_now    = ep["capital_before"]
        capital_if_tp  = round(capital_now + ep["potential_profit"], 2)
        capital_if_sl  = round(capital_now - ep["risk_usd"], 2)
        direction      = "🔼" if signal == "BUY" else "🔽"
        pnl_pct_tp     = round(ep["potential_profit"] / capital_now * 100, 1) if capital_now else 0
        pnl_pct_sl     = round(ep["risk_usd"]         / capital_now * 100, 1) if capital_now else 0

        msg += (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>💼 Paramètres d'entrée</b>\n"
            f"{direction} <b>Entrée :</b>     {ep['entry']:.2f}\n"
            f"🛑 <b>Stop Loss :</b>   {ep['sl']:.2f}\n"
            f"🎯 <b>Take Profit :</b> {ep['tp']:.2f}\n"
            f"📦 <b>Lot Size :</b>    {ep['lot_size']:.2f}\n"
            f"⚖️ <b>R/R :</b>         1:{ep['rr_ratio']:.1f}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>📊 Capital</b>\n"
            f"💵 <b>Capital actuel :</b>  {capital_now:.2f} USD\n"
            f"⚠️ <b>Risque :</b>          -{ep['risk_usd']:.2f} USD ({pnl_pct_sl:.1f}%)\n"
            f"✅ <b>Si TP atteint :</b>   {capital_if_tp:.2f} USD "
            f"<i>(+{ep['potential_profit']:.2f} / +{pnl_pct_tp:.1f}%)</i>\n"
            f"❌ <b>Si SL atteint :</b>   {capital_if_sl:.2f} USD "
            f"<i>(-{ep['risk_usd']:.2f} / -{pnl_pct_sl:.1f}%)</i>\n"
        )

    return msg


# ════════════════════════════════════════════════════════════════════════════
# 3. FORMAT — RÉSULTAT D'UN TRADE (TP ou SL confirmé)
# ════════════════════════════════════════════════════════════════════════════

def format_trade_result_message(result: dict, signal: str) -> str:
    """
    Message envoyé après confirmation d'un TP ou SL.
    result = retour de capital_tracker.apply_tp() ou apply_sl()

    Args:
        result : {outcome, capital_before, capital_after, pnl}
        signal : "BUY" ou "SELL"
    """
    outcome        = result["outcome"]
    capital_before = result["capital_before"]
    capital_after  = result["capital_after"]
    pnl            = result["pnl"]
    pnl_pct        = round(pnl / capital_before * 100, 1) if capital_before else 0

    stats   = capital_tracker.get_stats()
    pnl_tot = stats["pnl_total"]
    wr      = stats["win_rate"]
    trades  = stats["total_trades"]

    if outcome == "TP":
        header = f"🎯 <b>TAKE PROFIT atteint — {signal}</b>"
        emoji  = "✅"
        pnl_str = f"+{pnl:.2f} USD (+{pnl_pct:.1f}%)"
    else:
        header = f"🛑 <b>STOP LOSS atteint — {signal}</b>"
        emoji  = "❌"
        pnl_str = f"{pnl:.2f} USD ({pnl_pct:.1f}%)"

    pnl_tot_str = f"+{pnl_tot:.2f}" if pnl_tot >= 0 else f"{pnl_tot:.2f}"

    return (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{emoji} <b>PnL trade :</b>      {pnl_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>📊 Évolution du capital</b>\n"
        f"💵 <b>Capital avant :</b>   {capital_before:.2f} USD\n"
        f"💰 <b>Nouveau capital :</b> <b>{capital_after:.2f} USD</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>📈 Stats globales</b>\n"
        f"🔢 <b>Trades :</b>    {trades}\n"
        f"🏆 <b>Win rate :</b>  {wr:.1f}%\n"
        f"💹 <b>PnL total :</b> {pnl_tot_str} USD\n"
    )


# ════════════════════════════════════════════════════════════════════════════
# 4. FORMAT — ERREUR
# ════════════════════════════════════════════════════════════════════════════

def format_error_message(context: str, error: str) -> str:
    return (
        f"⚠️ <b>XAUUSD Bot — Erreur critique</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Contexte :</b> {context}\n"
        f"❌ <b>Erreur :</b> {error}"
    )


# ════════════════════════════════════════════════════════════════════════════
# 5. RACCOURCIS
# ════════════════════════════════════════════════════════════════════════════

def notify_signal(analysis: dict) -> bool:
    """
    Envoie le signal UNIQUEMENT si confluence validée (BUY ou SELL).
    Silence total si NEUTRAL.
    """
    signal = analysis.get("signal", "NEUTRAL")
    if signal == "NEUTRAL":
        logger.info("⏭️  NEUTRAL — pas d'envoi Telegram.")
        return False
    logger.info("📨 Envoi signal %s", signal)
    return send_message(format_signal_message(analysis))


def notify_tp(signal: str, entry: float, sl: float, tp: float, profit: float, dt: str = "") -> bool:
    """
    Appelle capital_tracker.apply_tp() et envoie le message de résultat.

    Args:
        signal : "BUY" ou "SELL"
        entry  : Prix d'entrée
        sl     : Stop Loss
        tp     : Take Profit
        profit : Gain réalisé en USD
        dt     : Datetime (optionnel)
    """
    result = capital_tracker.apply_tp(signal, entry, sl, tp, profit, dt)
    return send_message(format_trade_result_message(result, signal))


def notify_sl(signal: str, entry: float, sl: float, tp: float, loss: float, dt: str = "") -> bool:
    """
    Appelle capital_tracker.apply_sl() et envoie le message de résultat.

    Args:
        loss : Perte en USD (valeur positive)
    """
    result = capital_tracker.apply_sl(signal, entry, sl, tp, loss, dt)
    return send_message(format_trade_result_message(result, signal))


def notify_error(context: str, error: str) -> bool:
    return send_message(format_error_message(context, error))
