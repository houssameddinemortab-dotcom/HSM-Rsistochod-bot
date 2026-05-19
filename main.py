"""
main.py
-------
Boucle principale du bot XAUUSD.
Toutes les 300 secondes :
  - Si trade actif : vérifie TP/SL
  - Sinon : analyse + envoi message de veille (+ signal si confluence)
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

active_trade: dict | None = None


def open_trade(analysis: dict) -> None:
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
        "dt":     analysis["datetime"],
    }
    logger.info("Trade ouvert → %s | Entry=%.2f | SL=%.2f | TP=%.2f",
                active_trade["signal"], active_trade["entry"],
                active_trade["sl"], active_trade["tp"])


def check_active_trade(candles: list[dict]) -> bool:
    global active_trade
    if not active_trade:
        return False

    last   = candles[0]
    high   = last["high"]
    low    = last["low"]
    signal = active_trade["signal"]

    tp_hit = (high >= active_trade["tp"]) if signal == "BUY" else (low <= active_trade["tp"])
    sl_hit = (low  <= active_trade["sl"]) if signal == "BUY" else (high >= active_trade["sl"])

    if tp_hit:
        logger.info("🎯 TP atteint | %s | +%.2f USD", signal, active_trade["profit"])
        telegram_bot.notify_tp(
            signal, active_trade["entry"], active_trade["sl"],
            active_trade["tp"], active_trade["profit"], last["datetime"],
        )
        active_trade = None
        return True

    if sl_hit:
        logger.info("🛑 SL atteint | %s | -%.2f USD", signal, active_trade["risk"])
        telegram_bot.notify_sl(
            signal, active_trade["entry"], active_trade["sl"],
            active_trade["tp"], active_trade["risk"], last["datetime"],
        )
        active_trade = None
        return True

    return False


def run_cycle() -> None:
    logger.info("═══ Cycle | Capital : %.2f USD ═══", capital_tracker.get_capital())
    candles = data_client.get_ohlcv()

    if active_trade:
        closed = check_active_trade(candles)
        if not closed:
            logger.info("Trade en cours (%s) — attente TP/SL.", active_trade["signal"])
        return

    analysis = strategy.analyze_market(candles)
    telegram_bot.notify_cycle(analysis)   # ← envoie veille + signal si confluence

    if analysis.get("signal") in ("BUY", "SELL"):
        open_trade(analysis)


def main() -> None:
    logger.info("🚀 Bot démarré — %s | cycle %ds", SYMBOL, INTERVAL_SECONDS)
    stats = capital_tracker.get_stats()
    telegram_bot.send_message(
        f"🚀 <b>XAUUSD Bot démarré</b>\n"
        f"Symbole : {SYMBOL} | Cycle : {INTERVAL_SECONDS}s\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 Capital : {stats['capital']:.2f} USD  |  "
        f"PnL : {stats['pnl_total']:+.2f} USD  |  "
        f"WR : {stats['win_rate']:.1f}%"
    )

    consecutive_errors = 0
    MAX_ERRORS = 5

    while True:
        try:
            run_cycle()
            consecutive_errors = 0
        except KeyboardInterrupt:
            telegram_bot.send_message("🛑 <b>XAUUSD Bot arrêté.</b>")
            break
        except RuntimeError as exc:
            consecutive_errors += 1
            logger.error("Erreur (%d/%d) : %s", consecutive_errors, MAX_ERRORS, exc)
            if consecutive_errors >= MAX_ERRORS:
                telegram_bot.notify_error("Boucle principale",
                    f"{consecutive_errors} erreurs consécutives.")
                consecutive_errors = 0
        except Exception as exc:
            logger.exception("Exception : %s", exc)
            telegram_bot.notify_error("Exception inattendue", str(exc))
        finally:
            time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
