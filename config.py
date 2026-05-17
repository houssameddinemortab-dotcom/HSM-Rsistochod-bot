"""
config.py
---------
Constantes globales + chargement des variables d'environnement.
Les valeurs sensibles sont lues depuis l'environnement (Railway / .env local).
En local, créer un fichier .env et ne jamais le commiter sur GitHub.
"""

import os

# ── Credentials ───────────────────────────────────────────────────────────────
TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY", "1a6449e9febd41c08736d0340aedc75a")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8675193878:AAEKJoJDyDKkVGuSOO7qNAKNHP5ZissLTqE")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID",   "6387333974")

# ── Paire et timeframe ────────────────────────────────────────────────────────
SYMBOL     = "XAU/USD"   # Format 12data pour l'or spot
INTERVAL   = "5min"      # 1min | 5min | 15min | 30min | 1h | 4h | 1day
OUTPUTSIZE = 100         # Nombre de bougies récupérées par cycle

# ── Scheduler ─────────────────────────────────────────────────────────────────
INTERVAL_SECONDS = 300   # Rafraîchissement toutes les 5 minutes

# ── Indicateurs ───────────────────────────────────────────────────────────────
RSI_PERIOD       = 14

STOCH_K_PERIOD   = 14
STOCH_D_PERIOD   = 3
STOCH_SLOWING    = 3

# ── Seuils de signal ──────────────────────────────────────────────────────────
RSI_OVERSOLD     = 30
RSI_OVERBOUGHT   = 70
STOCH_OVERSOLD   = 20
STOCH_OVERBOUGHT = 80

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"   # DEBUG | INFO | WARNING | ERROR
