"""
config.py
---------
Constantes globales + chargement des variables d'environnement.
"""

import os

# ── Credentials ───────────────────────────────────────────────────────────────
TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY", "1a6449e9febd41c08736d0340aedc75a")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8675193878:AAEKJoJDyDKkVGuSOO7qNAKNHP5ZissLTqE")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID",   "6387333974")

# ── Paire et timeframe ────────────────────────────────────────────────────────
SYMBOL     = "XAU/USD"
INTERVAL   = "5min"
OUTPUTSIZE = 100

# ── Scheduler ─────────────────────────────────────────────────────────────────
INTERVAL_SECONDS = 300

# ── Indicateurs ───────────────────────────────────────────────────────────────
RSI_PERIOD       = 14
STOCH_K_PERIOD   = 5     # Réduit de 14 → 5 : plus réactif sur 5min
STOCH_D_PERIOD   = 3
STOCH_SLOWING    = 3

# ── Seuils RSI ────────────────────────────────────────────────────────────────
# XAUUSD 5min : le RSI dépasse rarement 30/70 → on élargit à 35/65
# Cela correspond aux zones de retournement réalistes sur l'or
RSI_OVERSOLD     = 40    # était 30 → signal BUY si RSI < 40
RSI_OVERBOUGHT   = 60    # était 70 → signal SELL si RSI > 60

# ── Seuils Stochastique ────────────────────────────────────────────────────────
# On exige seulement %K en zone (plus %D en même temps → trop restrictif)
# %D sera affiché en diagnostic mais ne bloque plus le signal
STOCH_OVERSOLD   = 25    # était 20
STOCH_OVERBOUGHT = 75    # était 80

# ── Order Block ────────────────────────────────────────────────────────────────
# Multiplicateur ATR pour définir une "forte impulsion"
# 1.5 était trop élevé sur 5min → réduit à 0.8 (plus d'OB détectés)
OB_ATR_MULTIPLIER = 0.8  # était 1.5 dans strategy.py

# Tolérance pour le retest de l'OB (en % de la hauteur de la zone)
OB_TOLERANCE = 0.5       # était 0.3 → zone de retest élargie

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
