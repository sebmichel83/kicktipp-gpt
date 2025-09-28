# kicktipp-gpt

Automatisierte Tippabgabe für Kicktipp-Spielrunden mit einer OpenAI-gestützten
Prognose-Pipeline. Das Projekt sammelt die offenen Spiele eines Spieltages,
fordert das Modell zu quellengestützten Vorhersagen auf und trägt die Tipps im
Portal ein.

## Highlights

- **Websuche standardmäßig aktiv** – sowohl `bot.py` als auch
  `openai_predictor.py` nutzen die OpenAI Responses API inklusive
  `web_search`-Tool, um Quoten, Verletzungsnews und weitere Evidenz live
  nachzuschlagen.
- Strenges JSON-Schema mit Validierung der Modellantworten, um fehlerhafte
  Tippreihen zu erkennen.
- Optionaler Fallback auf Chat Completions (ohne Websuche), falls die
  Responses-API nicht verfügbar ist.

## Voraussetzungen

- Python ≥ 3.11
- Ein OpenAI-API-Schlüssel mit Zugriff auf die verwendeten Modelle und das
  `web_search`-Tool
- Abhängigkeiten installieren (z. B. via `python -m venv .venv` und
  `pip install -r requirements.txt`, falls vorhanden)

## Konfiguration

1. Kopiere `config.ini.dist` nach `config.ini` und fülle die Zugangsdaten aus.
2. Relevante Optionen:
   - `prompt_profile = research` (Standard): aktiviert den Responses-Flow mit
     Websuche in `bot.py`.
   - `use_web_search = true`: sorgt dafür, dass `openai_predictor.py` die
     Websuche nutzt.
   - Über die Umgebungsvariable `OPENAI_PROMPT_PROFILE` oder den CLI-Parameter
     `--prompt-profile` kann auf den Chat-Fallback gewechselt werden, wenn die
     Websuche nicht verfügbar sein sollte.

## Nutzung

### Kicktipp-Bot (`bot.py`)

```
python3 bot.py --config config.ini
```

Der Bot liest die offenen Spiele, ruft standardmäßig die Responses API mit
aktivierter Websuche auf und schreibt die Tipps anschließend ins Portal. Die
Rohantworten werden unter `out/raw_openai/` protokolliert.

### Prognose-Helfer (`openai_predictor.py`)

Das Skript stellt eine wiederverwendbare Klasse `OpenAIPredictor` bereit, die
ebenfalls per Default die Websuche der Responses API nutzt. Beispiel:

```python
from openai_predictor import OpenAIPredictor, MatchLine

predictor = OpenAIPredictor(model="gpt-5")
predictions = predictor.predict_matchday(
    season="2025/26",
    matchday=1,
    lines=[MatchLine(matchday=1, home_team="FCB", away_team="BVB")],
)
```

## Websuche deaktivieren (falls nötig)

- `bot.py`: `python3 bot.py --prompt-profile basic`
- `openai_predictor.py`: `OpenAIPredictor(..., use_web_search=False)`

In beiden Fällen fällt das System auf den Chat-Completion-Flow mit JSON-Schema
zurück.

## Tests

Zum schnellen Syntax-Check genügt:

```
python3 -m compileall bot.py openai_predictor.py
```

