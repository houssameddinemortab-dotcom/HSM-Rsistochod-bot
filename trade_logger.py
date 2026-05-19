"""
trade_logger.py
---------------
Module COMPLÉMENTAIRE — ne remplace aucun fichier existant.
Rôle : envoyer un message Telegram COMPLET lors de :
  1. L'ouverture d'un trade (entrée BUY/SELL avec tous les détails)
  2. La clôture d'un trade (TP ou SL avec bilan capital complet)

Usage dans main.py :
  import trade_logger
  trade_logger.log_entry(analysis)        # à l'ouverture
  trade_logger.log_result("TP", trade)    # quand TP atteint
  trade_logger.log_result("SL", trade)    # quand SL atteint
"""

import logging
from datetime import datetime

import capital_tracker
import telegram_bot   # réutilise send_message() existant

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# 1. MESSAGE D'ENTRÉE — envoyé DÈS qu'un signal est exécuté
# ════════════════════════════════════════════════════════════════════════════

def log_entry(analysis: dict) -> bool:
    """
    Envoie un message Telegram complet au moment de l'ouverture du trade.
    Appelé dans main.py juste après open_trade(analysis).

    Contient :
      - Direction (BUY/SELL), prix d'entrée, heure
      - Stop Loss et Take Profit
      - Lot size, risque en USD et en %
      - Capital au moment de l'entrée
      - Projections capital si TP / si SL
      - RSI, Stoch, Order Block de référence
      - Ratio R/R
    """
    signal = analysis.get("signal", "NEUTRAL")
    if signal not in ("BUY", "SELL"):
        return False

    ep  = analysis.get("entry_params")
    ob  = analysis.get("ob_matched")
    rsi = analysis.get("rsi")
    k   = analysis.get("stoch_k")
    d   = analysis.get("stoch_d")
    dt  = analysis.get("datetime", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    if not ep:
        logger.warning("log_entry() : entry_params manquant.")
        return False

    capital_now   = ep["capital_before"]
    capital_if_tp = round(capital_now + ep["potential_profit"], 2)
    capital_if_sl = round(capital_now - ep["risk_usd"],         2)
    pct_risk      = round(ep["risk_usd"]         / capital_now * 100, 1) if capital_now else 0
    pct_tp        = round(ep["potential_profit"] / capital_now * 100, 1) if capital_now else 0

    direction_emoji = "🔼" if signal == "BUY" else "🔽"
    signal_emoji    = "🟢" if signal == "BUY" else "🔴"
    sl_dist         = round(abs(ep["entry"] - ep["sl"]), 2)
    tp_dist         = round(abs(ep["tp"]    - ep["entry"]), 2)

    rsi_s = f"{rsi:.1f}" if rsi is not None else "N/A"
    k_s   = f"{k:.1f}"   if k   is not None else "N/A"
    d_s   = f"{d:.1f}"   if d   is not None else "N/A"

    ob_line = ""
    if ob:
        ob_emoji = "🟦" if ob["type"] == "BULLISH" else "🟧"
        ob_line  = (
            f"  {ob_emoji} OB {ob['type']} : "
            f"[{ob['low']:.2f} – {ob['high']:.2f}]\n"
        )

    msg = (
        f"{signal_emoji} <b>ENTRÉE {signal} EXÉCUTÉE — XAUUSD</b>\n"
        f"🕐 <b>Heure :</b> {dt}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"

        f"<b>📍 Paramètres du trade</b>\n"
        f"  {direction_emoji} <b>Entrée :</b>       <b>{ep['entry']:.2f}</b>\n"
        f"  🛑 <b>Stop Loss :</b>    <b>{ep['sl']:.2f}</b>  "
        f"<i>({sl_dist:.2f} pts)</i>\n"
        f"  🎯 <b>Take Profit :</b>  <b>{ep['tp']:.2f}</b>  "
        f"<i>({tp_dist:.2f} pts)</i>\n"
        f"  ⚖️  <b>R/R :</b>          1:{ep['rr_ratio']:.1f}\n"
        f"  📦 <b>Lot Size :</b>     {ep['lot_size']:.2f}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"

        f"<b>📊 Confluence détectée</b>\n"
        f"  📐 RSI (14) : <b>{rsi_s}</b>\n"
        f"  📊 Stoch %K : <b>{k_s}</b>  |  %D : <b>{d_s}</b>\n"
        f"{ob_line}"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"

        f"<b>💼 Capital & Risque</b>\n"
        f"  💵 <b>Capital actuel :</b>     {capital_now:.2f} USD\n"
        f"  ⚠️  <b>Risque max :</b>         "
        f"-{ep['risk_usd']:.2f} USD  ({pct_risk:.1f}%)\n"
        f"  ✅ <b>Si TP atteint :</b>      "
        f"<b>{capital_if_tp:.2f} USD</b>  (+{ep['potential_profit']:.2f} / +{pct_tp:.1f}%)\n"
        f"  ❌ <b>Si SL atteint :</b>      "
        f"<b>{capital_if_sl:.2f} USD</b>  (-{ep['risk_usd']:.2f} / -{pct_risk:.1f}%)\n"
    )

    logger.info("log_entry() → message entrée %s envoyé.", signal)
    return telegram_bot.send_message(msg)


# ════════════════════════════════════════════════════════════════════════════
# 2. MESSAGE DE RÉSULTAT — envoyé quand TP ou SL est atteint
# ════════════════════════════════════════════════════════════════════════════

def log_result(outcome: str, trade: dict, close_dt: str = "") -> bool:
    """
    Envoie un message Telegram complet à la clôture du trade.
    Met à jour le capital via capital_tracker.

    Args:
        outcome  : "TP" ou "SL"
        trade    : dict du trade actif (depuis main.py active_trade)
                   attendu : {signal, entry, sl, tp, profit, risk, dt}
        close_dt : datetime de clôture (optionnel)

    Contient :
      - Résultat TP/SL avec PnL en USD et en %
      - Prix d'entrée rappelé vs prix de sortie (TP ou SL)
      - Distance parcourue en points
      - Durée du trade (si datetime disponible)
      - Capital avant / après
      - Variation du capital en USD et en %
      - Cumul : PnL total, Win Rate, nb trades
      - Barre de progression visuelle du capital
    """
    signal   = trade.get("signal", "?")
    entry    = trade.get("entry",  0.0)
    sl       = trade.get("sl",     0.0)
    tp       = trade.get("tp",     0.0)
    profit   = trade.get("profit", 0.0)
    risk     = trade.get("risk",   0.0)
    open_dt  = trade.get("dt",     "")
    close_dt = close_dt or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # ── Mise à jour capital ───────────────────────────────────────────────────
    if outcome == "TP":
        result = capital_tracker.apply_tp(signal, entry, sl, tp, profit, close_dt)
        exit_price  = tp
        pnl         = profit
        outcome_emoji = "🎯"
        outcome_label = "TAKE PROFIT atteint"
        pnl_emoji     = "✅"
    else:
        result = capital_tracker.apply_sl(signal, entry, sl, tp, risk, close_dt)
        exit_price  = sl
        pnl         = -risk
        outcome_emoji = "🛑"
        outcome_label = "STOP LOSS atteint"
        pnl_emoji     = "❌"

    capital_before = result["capital_before"]
    capital_after  = result["capital_after"]
    pnl_usd        = result["pnl"]
    pnl_pct        = round(pnl_usd / capital_before * 100, 1) if capital_before else 0
    pnl_str        = f"+{pnl_usd:.2f}" if pnl_usd >= 0 else f"{pnl_usd:.2f}"
    pnl_pct_str    = f"+{pnl_pct:.1f}%" if pnl_pct >= 0 else f"{pnl_pct:.1f}%"

    # ── Distance parcourue ────────────────────────────────────────────────────
    dist_parcourue = round(abs(exit_price - entry), 2)
    dist_sl        = round(abs(entry - sl), 2)
    dist_tp        = round(abs(tp - entry), 2)

    # ── Durée du trade ────────────────────────────────────────────────────────
    duree_str = ""
    try:
        fmt = "%Y-%m-%d %H:%M:%S"
        t1  = datetime.strptime(open_dt[:19],  fmt)
        t2  = datetime.strptime(close_dt[:19], fmt)
        diff = t2 - t1
        mins = int(diff.total_seconds() // 60)
        duree_str = f"  ⏱️  <b>Durée :</b>  {mins} minutes\n"
    except Exception:
        pass

    # ── Stats globales ─────────────────────────────────────────────────────────
    stats       = capital_tracker.get_stats()
    pnl_tot     = stats["pnl_total"]
    pnl_tot_str = f"+{pnl_tot:.2f}" if pnl_tot >= 0 else f"{pnl_tot:.2f}"
    cap_var_pct = round((capital_after - 100.0) / 100.0 * 100, 1)  # vs capital initial

    # ── Barre de progression du capital (sur 20 caractères) ───────────────────
    filled = min(int(cap_var_pct / 5) + 10, 20)   # 10 = neutre (100$)
    filled = max(filled, 0)
    bar    = "█" * filled + "░" * (20 - filled)

    direction_emoji = "🔼" if signal == "BUY" else "🔽"
    signal_emoji    = "🟢" if signal == "BUY" else "🔴"

    msg = (
        f"{outcome_emoji} <b>{outcome_label} — {signal}</b>\n"
        f"🕐 <b>Clôture :</b> {close_dt}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"

        f"<b>📍 Récapitulatif du trade</b>\n"
        f"  {signal_emoji} <b>Direction :</b>   {signal}\n"
        f"  {direction_emoji} <b>Entrée :</b>      {entry:.2f}\n"
        f"  🏁 <b>Sortie :</b>      <b>{exit_price:.2f}</b>\n"
        f"  📏 <b>Distance :</b>    {dist_parcourue:.2f} pts  "
        f"<i>(SL={dist_sl:.2f} | TP={dist_tp:.2f})</i>\n"
        f"{duree_str}"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"

        f"<b>{pnl_emoji} Résultat</b>\n"
        f"  💹 <b>PnL :</b>   <b>{pnl_str} USD</b>  ({pnl_pct_str})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"

        f"<b>💰 Évolution du capital</b>\n"
        f"  Avant :  {capital_before:.2f} USD\n"
        f"  Après :  <b>{capital_after:.2f} USD</b>\n"
        f"  Variation : <b>{pnl_str} USD</b>  ({pnl_pct_str})\n"
        f"  <code>[{bar}]</code>  {cap_var_pct:+.1f}% vs départ\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"

        f"<b>📈 Stats globales</b>\n"
        f"  🔢 Trades :     {stats['total_trades']}  "
        f"(✅ {stats['total_wins']} / ❌ {stats['total_losses']})\n"
        f"  🏆 Win Rate :   <b>{stats['win_rate']:.1f}%</b>\n"
        f"  💵 PnL total :  <b>{pnl_tot_str} USD</b>\n"
        f"  🏦 Capital :    <b>{capital_after:.2f} USD</b>  "
        f"<i>(initial : {stats['initial_capital']:.2f})</i>\n"
    )

    logger.info("log_result() → %s %s | PnL=%.2f | Capital=%.2f",
                outcome, signal, pnl_usd, capital_after)
    return telegram_bot.send_message(msg)


# ════════════════════════════════════════════════════════════════════════════
# 3. RÉSUMÉ QUOTIDIEN (optionnel — appeler manuellement ou via scheduler)
# ════════════════════════════════════════════════════════════════════════════

def log_daily_summary() -> bool:
    """
    Envoie un résumé complet de la journée.
    Peut être appelé toutes les 24h depuis main.py si souhaité.
    """
    stats       = capital_tracker.get_stats()
    pnl_tot     = stats["pnl_total"]
    pnl_tot_str = f"+{pnl_tot:.2f}" if pnl_tot >= 0 else f"{pnl_tot:.2f}"
    cap_var_pct = round((stats["capital"] - stats["initial_capital"]) /
                        stats["initial_capital"] * 100, 1) if stats["initial_capital"] else 0

    history = capital_tracker.get_history(limit=5)
    history_lines = ""
    for t in reversed(history):
        e  = "✅" if t["outcome"] == "TP" else "❌"
        pnl_h = f"+{t['pnl']:.2f}" if t["pnl"] >= 0 else f"{t['pnl']:.2f}"
        history_lines += f"  {e} {t['signal']} | {pnl_h} USD | → {t['capital_after']:.2f}\n"

    msg = (
        f"📋 <b>RÉSUMÉ XAUUSD Bot</b>\n"
        f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>💰 Capital</b>\n"
        f"  Initial :  {stats['initial_capital']:.2f} USD\n"
        f"  Actuel :   <b>{stats['capital']:.2f} USD</b>\n"
        f"  Variation : <b>{pnl_tot_str} USD</b>  ({cap_var_pct:+.1f}%)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>📊 Performance</b>\n"
        f"  Trades :   {stats['total_trades']}\n"
        f"  Wins :     ✅ {stats['total_wins']}\n"
        f"  Losses :   ❌ {stats['total_losses']}\n"
        f"  Win Rate : <b>{stats['win_rate']:.1f}%</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>🕘 5 derniers trades</b>\n"
        f"{history_lines if history_lines else '  Aucun trade enregistré.\n'}"
    )

    return telegram_bot.send_message(msg)
