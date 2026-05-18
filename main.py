"""
main.py
-------
Point d'entrée du bot XAUUSD.
Boucle toutes les INTERVAL_SECONDS secondes :
  1. Récupère les bougies XAUUSD (12data)
  2. Si un trade est en cours, vérifie si TP ou SL est atteint
  3. Sinon, analyse la confluence et envoie un signal si validée
"""

import time
import logging

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import SYMBOL, INTERVAL, INTERVAL_SECONDS, LOG_LEVEL
import data_client
import strategy
import telegram_bot
import capital_tracker

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


# ════════════════════════════════════════════════════════════════════════════
# ÉTAT DU TRADE EN COURS (en mémoire — reset si bot redémarre)
# ════════════════════════════════════════════════════════════════════════════

# Structure : None si pas de trade ouvert, sinon dict avec les paramètres
active_trade: dict | None = None


def open_trade(analysis: dict) -> None:
    """Enregistre le trade actif après un signal BUY/SELL."""
    global active_trade
    ep = analysis.get("entry_params")
    if not ep:
        return
    active_trade = {
        "signal": analysis["signal"],
        "entry":  ep["entry"],
        "sl":     ep["sl"],
        "tp":     ep["tp"],
        "profit": ep["potential_profit"],
        "risk":   ep["risk_usd"],
        "lot":    ep["lot_size"],
        "dt":     analysis["datetime"],
    }
    logger.info(
        "Trade ouvert → %s | Entry=%.2f | SL=%.2f | TP=%.2f",
        active_trade["signal"], active_trade["entry"],
        active_trade["sl"], active_trade["tp"],
    )


def check_active_trade(candles: list[dict]) -> bool:
    """
    Vérifie si le TP ou SL du trade actif est atteint sur la dernière bougie.

    Returns:
        True si le trade est clôturé (TP ou SL), False sinon.
    """
    global active_trade
    if not active_trade:
        return False

    last   = candles[0]
    high   = last["high"]
    low    = last["low"]
    signal = active_trade["signal"]

    tp_hit = False
    sl_hit = False

    if signal == "BUY":
        tp_hit = high >= active_trade["tp"]
        sl_hit = low  <= active_trade["sl"]
    elif signal == "SELL":
        tp_hit = low  <= active_trade["tp"]
        sl_hit = high >= active_trade["sl"]

    if tp_hit:
        logger.info("🎯 TP atteint → signal=%s | profit=%.2f USD", signal, active_trade["profit"])
        telegram_bot.notify_tp(
            signal = signal,
            entry  = active_trade["entry"],
            sl     = active_trade["sl"],
            tp     = active_trade["tp"],
            profit = active_trade["profit"],
            dt     = last["datetime"],
        )
        active_trade = None
        return True

    if sl_hit:
        logger.info("🛑 SL atteint → signal=%s | perte=%.2f USD", signal, active_trade["risk"])
        telegram_bot.notify_sl(
            signal = signal,
            entry  = active_trade["entry"],
            sl     = active_trade["sl"],
            tp     = active_trade["tp"],
            loss   = active_trade["risk"],
            dt     = last["datetime"],
        )
        active_trade = None
        return True

    logger.debug("Trade en cours — TP/SL non atteints.")
    return False


# ════════════════════════════════════════════════════════════════════════════
# CYCLE PRINCIPAL
# ════════════════════════════════════════════════════════════════════════════

def run_cycle() -> None:
    """
    Un cycle complet :
      - Si trade actif → vérifie TP/SL.
      - Sinon → cherche un nouveau signal de confluence.
    """
    logger.info("═══ Cycle [%s | %s] | Capital : %.2f USD ═══",
                SYMBOL, INTERVAL, capital_tracker.get_capital())

    candles = data_client.get_ohlcv()

    # ── Priorité : vérifier le trade en cours ────────────────────────────────
    if active_trade:
        closed = check_active_trade(candles)
        if not closed:
            logger.info(
                "Trade ouvert (%s) | Entry=%.2f | SL=%.2f | TP=%.2f — attente.",
                active_trade["signal"], active_trade["entry"],
                active_trade["sl"], active_trade["tp"],
            )
        return   # pas de nouveau signal tant qu'un trade est actif

    # ── Recherche de confluence ───────────────────────────────────────────────
    analysis = strategy.analyze_market(candles)
    sent     = telegram_bot.notify_signal(analysis)

    if sent:
        open_trade(analysis)   # enregistre le trade actif


# ════════════════════════════════════════════════════════════════════════════
# BOUCLE PRINCIPALE
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    logger.info("🚀 XAUUSD Bot démarré — cycle toutes les %ds", INTERVAL_SECONDS)

    stats = capital_tracker.get_stats()
    telegram_bot.send_message(
        f"🚀 <b>XAUUSD Bot démarré</b>\n"
        f"Symbole : {SYMBOL} | Rafraîchissement : {INTERVAL_SECONDS}s\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Capital actuel :</b> {stats['capital']:.2f} USD\n"
        f"📈 <b>PnL total :</b> {stats['pnl_total']:+.2f} USD\n"
        f"🔢 <b>Trades :</b> {stats['total_trades']} | "
        f"🏆 <b>Win rate :</b> {stats['win_rate']:.1f}%"
    )

    consecutive_errors = 0
    MAX_ERRORS = 5

    while True:
        try:
            run_cycle()
            consecutive_errors = 0

        except KeyboardInterrupt:
            logger.info("Arrêt manuel.")
            telegram_bot.send_message("🛑 <b>XAUUSD Bot arrêté manuellement.</b>")
            break

        except RuntimeError as exc:
            consecutive_errors += 1
            logger.error("Erreur cycle (%d/%d) : %s", consecutive_errors, MAX_ERRORS, exc)
            if consecutive_errors >= MAX_ERRORS:
                telegram_bot.notify_error(
                    "Boucle principale",
                    f"{consecutive_errors} erreurs consécutives — vérifier l'API."
                )
                consecutive_errors = 0

        except Exception as exc:
            logger.exception("Exception inattendue : %s", exc)
            telegram_bot.notify_error("Exception inattendue", str(exc))

        finally:
            time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
