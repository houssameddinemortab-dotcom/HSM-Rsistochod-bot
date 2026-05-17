"""
telegram_bot.py
---------------
Module de notifications Telegram pour XAUUSD Bot.
TOKEN et CHAT_ID sont lus depuis config.py.
"""

import logging
import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
TIMEOUT = 10


# ════════════════════════════════════════════════════════════════════════════
# 1. ENVOI DE MESSAGES
# ════════════════════════════════════════════════════════════════════════════

def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """
    Envoie un message texte au CHAT_ID configuré.

    Args:
        text       : Contenu du message (HTML ou Markdown).
        parse_mode : "HTML" (défaut) ou "Markdown".

    Returns:
        True si succès, False sinon.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("send_message() : TOKEN ou CHAT_ID manquant dans config.py.")
        return False

    url     = TELEGRAM_API_URL.format(token=TELEGRAM_BOT_TOKEN)
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       text,
        "parse_mode": parse_mode,
    }

    try:
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        logger.error("send_message() : timeout Telegram.")
        return False
    except requests.exceptions.RequestException as exc:
        logger.error("send_message() : erreur réseau → %s", exc)
        return False

    if resp.status_code != 200:
        logger.error(
            "send_message() : HTTP %d — %s",
            resp.status_code, resp.text[:200],
        )
        return False

    logger.debug("Message Telegram envoyé avec succès.")
    return True


# ════════════════════════════════════════════════════════════════════════════
# 2. FORMATAGE DES MESSAGES
# ════════════════════════════════════════════════════════════════════════════

_SIGNAL_EMOJI = {"BUY": "🟢", "SELL": "🔴", "NEUTRAL": "⚪"}
_TREND_EMOJI  = {"BULLISH": "📈", "BEARISH": "📉", "NEUTRAL": "➡️"}


def format_signal_message(a: dict) -> str:
    """
    Formate le message de signal de trading (HTML Telegram).

    Args:
        a: Résultat de strategy.analyze_market().

    Returns:
        str: Message HTML prêt à l'envoi.
    """
    signal  = a.get("signal",   "NEUTRAL")
    trend   = a.get("trend",    "NEUTRAL")
    rsi     = a.get("rsi")
    stoch_k = a.get("stoch_k")
    stoch_d = a.get("stoch_d")
    price   = a.get("price",    0.0)
    dt      = a.get("datetime", "N/A")
    obs     = a.get("order_blocks", [])

    se = _SIGNAL_EMOJI.get(signal, "⚪")
    te = _TREND_EMOJI.get(trend, "➡️")

    rsi_s  = f"{rsi:.2f}"    if rsi     is not None else "N/A"
    k_s    = f"{stoch_k:.2f}" if stoch_k is not None else "N/A"
    d_s    = f"{stoch_d:.2f}" if stoch_d is not None else "N/A"
    ob_s   = f"{len(obs)} détecté(s)" if obs else "Aucun"

    return (
        f"<b>📊 XAUUSD — {dt}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{se} <b>Signal :</b> <b>{signal}</b>\n"
        f"{te} <b>Tendance :</b> {trend}\n"
        f"💰 <b>Prix :</b> {price:.2f} USD\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📐 <b>RSI (14) :</b> {rsi_s}\n"
        f"📊 <b>Stoch %K :</b> {k_s}  |  <b>%D :</b> {d_s}\n"
        f"🧱 <b>Order Blocks :</b> {ob_s}\n"
    )


def format_error_message(context: str, error: str) -> str:
    """Formate un message d'erreur critique."""
    return (
        f"⚠️ <b>XAUUSD Bot — Erreur critique</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Contexte :</b> {context}\n"
        f"❌ <b>Erreur :</b> {error}"
    )


# ════════════════════════════════════════════════════════════════════════════
# 3. RACCOURCIS
# ════════════════════════════════════════════════════════════════════════════

def notify_signal(analysis: dict) -> bool:
    """Envoie le message de signal formaté."""
    return send_message(format_signal_message(analysis))


def notify_error(context: str, error: str) -> bool:
    """Envoie un message d'erreur critique."""
    return send_message(format_error_message(context, error))
