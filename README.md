# XAUUSD Trading Bot

Bot de trading algorithmique pour **XAUUSD** (Or/USD).
API marché : **12data.com** | Notifications : **Telegram**

---

## Arborescence

```
xauusd_bot/
├── main.py           ← Point d'entrée — boucle toutes les 300s
├── config.py         ← Credentials + constantes globales
├── data_client.py    ← API 12data — fetch + parse OHLCV
├── strategy.py       ← RSI, Stoch, tendance HH/HL, signal
├── telegram_bot.py   ← Envoi notifications Telegram
└── requirements.txt
```

---

## Installation locale

```bash
pip install -r requirements.txt
python main.py
```

---

## Déploiement Railway

1. Pusher ce dossier sur GitHub.
2. Créer un projet Railway depuis le dépôt.
3. Variables d'environnement Railway (optionnel — déjà dans config.py) :
   - `TWELVEDATA_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. Railway détecte `requirements.txt` et lance `python main.py`.

---

## Roadmap V6

| Version | Contenu |
|---------|---------|
| V6.1 | Ichimoku + RSI divergence + Order Blocks réels |
| V6.2 | TP partiel, trailing stop, filtre news |
| V6.3 | Commandes Telegram : /status /capital /stats /stop |
| V6.4 | Graphiques Telegram |
| V6.5 | Risk management : drawdown 20%, auto lot sizing |
