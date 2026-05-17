"""
main.py
-------
Point d'entrée du bot XAUUSD.
Lance une boucle infinie toutes les INTERVAL_SECONDS secondes :
  1. Récupère les bougies XAUUSD (12data)
  2. Analyse le marché (RSI, Stoch, tendance, Order Blocks)
  3. Envoie le signal via Telegram
"""

import time
import logging

# Charge .env si python-dotenv est installé (utile en local)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import SYMBOL, INTERVAL, INTERVAL_SECONDS, LOG_LEVEL
import data_client
import strategy
import telegram_bot


# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


# ════════════════════════════════════════════════════════════════════════════
# CYCLE D'ANALYSE
# ════════════════════════════════════════════════════════════════════════════

def run_cycle() -> None:
    """
    Exécute un cycle complet :
      - Fetch données  →  Analyse  →  Notification Telegram.

    Raises:
        RuntimeError si la récupération des données échoue.
    """
    logger.info("═══ Nouveau cycle [%s | %s] ═══", SYMBOL, INTERVAL)

    # 1. Données
    candles = data_client.get_ohlcv()

    # 2. Analyse
    analysis = strategy.analyze_market(candles)

    # 3. Notification
    sent = telegram_bot.notify_signal(analysis)
    if not sent:
        logger.warning("Échec de l'envoi Telegram — signal non transmis.")

    logger.info(
        "Cycle OK → signal=%s | prix=%.2f | RSI=%s | Stoch K=%s",
        analysis["signal"],
        analysis["price"],
        analysis["rsi"]    if analysis["rsi"]    is not None else "N/A",
        analysis["stoch_k"] if analysis["stoch_k"] is not None else "N/A",
    )


# ════════════════════════════════════════════════════════════════════════════
# BOUCLE PRINCIPALE
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    """
    Boucle infinie du bot.
    - Erreurs non fatales → log + alerte Telegram + continuation.
    - Erreurs fatales     → log + alerte Telegram + arrêt.
    - KeyboardInterrupt   → arrêt propre.
    """
    logger.info("🚀 XAUUSD Bot démarré — cycle toutes les %ds", INTERVAL_SECONDS)

    telegram_bot.send_message(
        f"🚀 <b>XAUUSD Bot démarré</b>\n"
        f"Symbole : {SYMBOL} | Intervalle : {INTERVAL} | "
        f"Rafraîchissement : {INTERVAL_SECONDS}s"
    )

    consecutive_errors  = 0
    MAX_ERRORS_BEFORE_ALERT = 5

    while True:
        try:
            run_cycle()
            consecutive_errors = 0

        except KeyboardInterrupt:
            logger.info("Arrêt manuel (KeyboardInterrupt).")
            telegram_bot.send_message("🛑 <b>XAUUSD Bot arrêté manuellement.</b>")
            break

        except RuntimeError as exc:
            consecutive_errors += 1
            logger.error(
                "Erreur cycle (%d/%d) : %s",
                consecutive_errors, MAX_ERRORS_BEFORE_ALERT, exc,
            )
            if consecutive_errors >= MAX_ERRORS_BEFORE_ALERT:
                msg = (
                    f"{consecutive_errors} erreurs consécutives — "
                    f"vérifier l'API 12data ou la connexion réseau."
                )
                logger.critical(msg)
                telegram_bot.notify_error("Boucle principale", msg)
                consecutive_errors = 0   # reset après alerte

        except Exception as exc:   # noqa
            logger.exception("Exception inattendue : %s", exc)
            telegram_bot.notify_error("Exception inattendue", str(exc))

        finally:
            logger.debug("Attente %ds...", INTERVAL_SECONDS)
            time.sleep(INTERVAL_SECONDS)


# ════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    main()
