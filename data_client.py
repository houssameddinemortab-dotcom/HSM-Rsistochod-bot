"""
data_client.py
--------------
Module de connexion à l'API 12data.com.
La clé API est lue depuis config.py (elle-même lue depuis l'environnement).
"""

import logging
import requests

from config import TWELVEDATA_API_KEY, SYMBOL, INTERVAL, OUTPUTSIZE

logger = logging.getLogger(__name__)

BASE_URL = "https://api.twelvedata.com"
TIMEOUT  = 15   # secondes


# ════════════════════════════════════════════════════════════════════════════
# RÉCUPÉRATION DES DONNÉES
# ════════════════════════════════════════════════════════════════════════════

def fetch_candles(
    symbol:     str = SYMBOL,
    interval:   str = INTERVAL,
    outputsize: int = OUTPUTSIZE,
) -> list[dict]:
    """
    Récupère les dernières bougies OHLCV depuis l'API 12data.

    Args:
        symbol     : Paire (ex. "XAU/USD").
        interval   : Timeframe 12data (ex. "5min").
        outputsize : Nombre de bougies demandées.

    Returns:
        list[dict]: Bougies brutes (valeurs en string), plus récente en premier.

    Raises:
        RuntimeError: En cas d'erreur réseau ou de réponse invalide.
    """
    if not TWELVEDATA_API_KEY:
        raise RuntimeError("TWELVEDATA_API_KEY non définie dans config.py.")

    params = {
        "symbol":     symbol,
        "interval":   interval,
        "outputsize": outputsize,
        "apikey":     TWELVEDATA_API_KEY,
        "format":     "JSON",
        "order":      "DESC",   # bougie la plus récente en tête
    }

    endpoint = f"{BASE_URL}/time_series"

    try:
        response = requests.get(endpoint, params=params, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Timeout lors de la requête à {endpoint}")
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Erreur réseau : {exc}")

    if response.status_code != 200:
        raise RuntimeError(
            f"HTTP {response.status_code} — {response.text[:300]}"
        )

    data = response.json()

    # 12data retourne {"status": "error", "message": "..."} en cas d'erreur
    if data.get("status") == "error":
        raise RuntimeError(f"Erreur API 12data : {data.get('message', data)}")

    if "values" not in data or not data["values"]:
        raise RuntimeError(f"Réponse vide ou sans 'values' : {data}")

    logger.debug(
        "fetch_candles() → %d bougies pour %s [%s]",
        len(data["values"]), symbol, interval,
    )
    return data["values"]


def parse_candle(raw: dict) -> dict:
    """
    Convertit une bougie brute (strings) en types numériques Python.

    Args:
        raw (dict): Bougie brute de l'API.

    Returns:
        dict: {datetime, open, high, low, close, volume} avec float/int.
    """
    return {
        "datetime": raw["datetime"],
        "open":     float(raw["open"]),
        "high":     float(raw["high"]),
        "low":      float(raw["low"]),
        "close":    float(raw["close"]),
        "volume":   int(float(raw.get("volume", 0))),
    }


def get_ohlcv(
    symbol:     str = SYMBOL,
    interval:   str = INTERVAL,
    outputsize: int = OUTPUTSIZE,
) -> list[dict]:
    """
    Point d'entrée principal : récupère et parse les bougies OHLCV.

    Returns:
        list[dict]: Bougies parsées (float), plus récente en premier.
    """
    raw = fetch_candles(symbol, interval, outputsize)
    candles = [parse_candle(c) for c in raw]
    logger.info(
        "get_ohlcv() → %d bougies | dernière clôture : %.2f @ %s",
        len(candles), candles[0]["close"], candles[0]["datetime"],
    )
    return candles
