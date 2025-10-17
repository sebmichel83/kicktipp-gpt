# Kicktipp-GPT Bot - Multi-Model Edition

> **⚠️ Experimentelles Vibe-Coding-Projekt**
> Dieses gesamte Projekt – einschließlich Code, Architektur, Prompts und Dokumentation – wurde **vollständig durch KI-gestützte Vibe-Coding-Sessions** erstellt. Es handelt sich um ein **experimentelles Projekt** zur Erforschung der Möglichkeiten von AI-Pair-Programming und automatisierter Fußball-Vorhersage. Keine Garantie für Funktionalität, Genauigkeit oder Stabilität. Nutzung auf eigene Gefahr!

Automatisierte Tippabgabe für Kicktipp-Spielrunden mit KI-gestützter Prognose-Pipeline. Dieses Projekt bietet **zwei Implementierungen** mit modernsten Large Language Models:

## 🆕 Zwei Versionen verfügbar!

| Feature | **Claude Sonnet 4.5** ⭐ | **OpenAI GPT-5** |
|---------|------------------------|------------------|
| **Modell** | claude-sonnet-4-5-20250929 | gpt-5 / gpt-4o |
| **Extended Thinking** | ✅ 10k tokens | ❌ |
| **Web Search** | ✅ DuckDuckGo | ✅ Built-in |
| **Reasoning Depth** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Prompt Complexity** | Natürlicher Konversationsstil | Standard Research |
| **Kontext-Bewusstsein** | Explizit (Derby, Druck, etc.) | Implizit |
| **Analyse-Framework** | Faktor-Checkliste | Allgemein |
| **Kosten** | Moderat (~$0.05-0.15/Spieltag) | Höher |
| **Empfehlung** | 🏆 Für maximale Genauigkeit | Solide Alternative |

## 📁 Projektstruktur

```
kicktipp-gpt/
├── claude/              # Claude Sonnet 4.5 Version (NEU!)
│   ├── bot.py          # Hauptskript mit Extended Thinking
│   ├── README.md       # Vollständige Dokumentation
│   ├── AGENTS.md       # Architektur & Methodik
│   ├── config.ini.example
│   └── requirements.txt
│
├── openai/             # OpenAI GPT-5 Version (Original)
│   ├── bot.py          # Hauptskript mit Responses API
│   ├── README.md       # Vollständige Dokumentation
│   ├── AGENTS.md       # Architektur & Prompts
│   ├── config.ini.example
│   └── requirements.txt
│
└── out/                # Gemeinsame Ausgabe
    ├── forms/          # Geparste Tippformulare
    ├── predictions/    # Finale Vorhersagen
    ├── raw_claude/     # Claude Rohantworten + Thinking
    └── raw_openai/     # OpenAI Rohantworten
```

## 🚀 Schnellstart

### Option 1: Claude Sonnet 4.5 (Empfohlen für beste Ergebnisse)

```bash
cd claude
pip install -r requirements.txt

# Config erstellen
cp config.ini.example config.ini
# Bearbeite config.ini: ANTHROPIC_API_KEY, Kicktipp-Zugangsdaten

# Einzelner Spieltag
python bot.py --start-index 10 --end-index 10

# Alle Spieltage (Trockenlauf)
python bot.py --no-submit
```

### Option 2: OpenAI GPT-5

```bash
cd openai
pip install -r requirements.txt

# Config erstellen
cp config.ini.example config.ini
# Bearbeite config.ini: OPENAI_API_KEY, Kicktipp-Zugangsdaten

# Einzelner Spieltag
python bot.py --start-index 10 --end-index 10

# Alle Spieltage (Trockenlauf)
python bot.py --no-submit
```

## 🎯 Warum Claude Sonnet 4.5?

Die **Claude-Version** wurde speziell entwickelt, um **den ersten Platz** im Tippspiel zu erreichen:

### 1. **Extended Thinking Mode**
- 10.000 Token Budget für interne Reasoning-Prozesse
- Claude analysiert **schrittweise** jedes Spiel
- Sichtbare Denkprozesse in Logs (`out/raw_claude/`)
- Beispiel: *"Bayern: 4W-1D letzte 5, xG 2.3, Leipzig: Orban verletzt → 3:1 wahrscheinlich"*

### 2. **Optimierte Analyse-Checkliste**
- Aktuelle Tabellenposition und Punktzahl
- Form der letzten 5 Spiele (Siege/Niederlagen/Tore)
- **Verletzte oder gesperrte Schlüsselspieler (SEHR WICHTIG!)**
- Head-to-Head Bilanz
- Heimvorteil (statistisch ~0.4 Tore Unterschied)
- Besondere Umstände (Derby, Europacup-Belastung, Trainerwechsel)

### 3. **Kontext-Bewusstsein**
Claude berücksichtigt automatisch:
- **Tabellenposition & Saisonziele** (Titel, Europa, Abstieg)
- **Druck-Situationen** (Muss-Siege)
- **Derby-Charakter** oder Rivalität
- **Europäische Spiele** (Müdigkeit)
- **Wetter** (Extrembedingungen)

### 4. **Anti-Degeneration**
- Vermeidet monotone Muster (z.B. alle 2:1)
- Realistische Ergebnis-Varianz
- 1:1 nur bei echter Remis-Indikation
- Mutige, aber fundierte Prognosen

### 5. **Live Web-Recherche**
- Automatische Suche pro Spiel
- Aktuelle Verletzungen, Form, News
- Wettquoten, xG-Statistiken
- Trainer-Statements

## 📊 Vergleich der Ansätze

### Claude-Ansatz (Natürlich & Fokussiert)
```python
# Konversationeller Prompt mit klaren Richtlinien
prompt = """
Erstelle eine fundierte Prognose für den X. Bundesliga-Spieltag.

**Wichtig:** Recherchiere zunächst die aktuelle Bundesliga-Tabelle,
Form der Teams (letzte 5 Spiele), Verletzungen und aktuelle News.

**Für jedes Spiel berücksichtige:**
- Aktuelle Tabellenposition und Punktzahl
- Form der letzten 5 Spiele (SEHR WICHTIG: Verletzungen!)
- Head-to-Head Bilanz
- Heimvorteil (~0.4 Tore Unterschied)
- Besondere Umstände (Derby, Europacup-Belastung)

**Realistische Ergebnisse:** Bundesliga-Durchschnitt ~2.8 Tore/Spiel,
Variation wichtig, keine monotonen Muster, mutige aber fundierte Tipps.
"""
```

### OpenAI-Ansatz (Flexibel)
```python
# Allgemeine Forschungs-Anweisung
prompt = """
Du bist FootballPred LHM, ein Prognose-Assistent.
Nutze Quoten, xG, Form, Verletzungen, Websuche.
Gib JSON zurück mit Predictions.
"""
```

**Ergebnis:** Claude's natürlicher, aber fokussierter Ansatz führt zu realistischeren und ausgewogeneren Prognosen.

## 🔧 Systemvoraussetzungen

### Beide Versionen
- Python 3.10+
- `requests`, `beautifulsoup4`
- Kicktipp-Account

### Claude-spezifisch
- `anthropic>=0.39.0`
- `duckduckgo-search>=7.0.0`
- Anthropic API Key ([console.anthropic.com](https://console.anthropic.com))

### OpenAI-spezifisch
- `openai>=1.40.0`
- OpenAI API Key ([platform.openai.com](https://platform.openai.com))

## 💡 Empfehlungen

### Für maximale Genauigkeit:
✅ **Nutze Claude Sonnet 4.5**
- Extended Thinking optional (Standard: deaktiviert für bessere Performance)
- Temperature: 0.7 (Standard)
- Web Search für Live-Daten

### Für schnelle Tests:
✅ **Nutze OpenAI GPT-4o-mini**
- Günstiger
- Schneller
- Immer noch gute Ergebnisse

### Für Ensemble-Predictions:
✅ **Beide parallel nutzen**
```bash
# Terminal 1
cd claude && python bot.py --no-submit

# Terminal 2
cd openai && python bot.py --no-submit

# Dann: Ergebnisse vergleichen und beste wählen
```

## 📈 Wie der Bot arbeitet

### 1. Login & Formularabruf
- Login bei `kicktipp.de`
- Abruf des Tippformulars für Spieltag X
- Extraktion der 9 Paarungen (Bundesliga)
- Parsing: Teamnamen, Eingabefelder, Quoten, Status

### 2. KI-Analyse
**Claude:**
- Natürliche Konversations-Prompts mit Faktor-Checkliste
- Extended Thinking optional (10k tokens, Standard: deaktiviert)
- Web-Recherche für Live-Daten
- Output: JSON mit 9 Predictions + Reasons

**OpenAI:**
- Research-Prompt mit Websuche
- Responses API (mit Tools) oder Chat Completions
- Output: JSON mit 9 Predictions

### 3. Validierung
- Exakt 9 Items?
- Korrekte Team-Namen?
- Integer-Tore (0-9)?
- Keine Degeneration (zu viele 1:1)?
- Bei Fehler: Retry mit angepasstem Prompt

### 4. Submit & Verifikation
- Formular mit Predictions befüllen
- POST an Kicktipp
- Seite neu laden
- Feld-für-Feld Verifikation
- Bei Abweichung: Retry

### 5. Audit-Trail
- `out/forms/` - Geparste Formulare
- `out/predictions/` - Finale Tipps
- `out/raw_claude/` - Claude Rohantworten + Thinking
- `out/raw_openai/` - OpenAI Rohantworten

## 🛠️ Konfiguration

### Claude (`claude/config.ini`)
```ini
[auth]
username = dein.loginname
password = dein.passwort

[pool]
pool_slug = deine-gruppe

[anthropic]
api_key = sk-ant-...
model = claude-sonnet-4-5-20250929
temperature = 0.7
timeout = 180
max_retries = 3

[run]
start_index = 1
end_index = 34
no_submit = false
```

### OpenAI (`openai/config.ini`)
```ini
[auth]
username = dein.loginname
password = dein.passwort

[pool]
pool_slug = deine-gruppe

[openai]
api_key = sk-...
model = gpt-5
temperature = 0.4
oa_timeout = 120
max_retries = 3
promptprofile = research

[run]
start_index = 1
end_index = 34
no_submit = false
```

## 📝 Beispiel-Logs

### Claude
```
2025-10-17 14:23:15 | INFO | Claude[sonnet-4.5] call: model=claude-sonnet-4-5-20250929, md=10, matches=9
2025-10-17 14:23:18 | INFO | [Claude Thinking] Bayern: 4W-1D last 5, xG 2.3, home advantage...
2025-10-17 14:23:20 | INFO | [Claude Thinking] Leipzig: Orban injury critical, xGA 1.8...
2025-10-17 14:23:45 | INFO | Claude predictions validated: 9 items
2025-10-17 14:23:50 | INFO | [Submit] Spieltag 10: 9/9 Spiele gespeichert.
```

### OpenAI
```
2025-10-17 14:25:10 | INFO | OpenAI[responses] call: model=gpt-5, md=10, matches=9 (Websuche aktiv)
2025-10-17 14:25:15 | INFO | Websuche: JA | queries=['Bayern form', 'Leipzig injuries'] | urls=[...]
2025-10-17 14:25:40 | INFO | Validierung erfolgreich: 9 Items
2025-10-17 14:25:45 | INFO | [Submit] Spieltag 10: 9/9 Spiele gespeichert.
```

## 🚨 Troubleshooting

### Claude
| Problem | Lösung |
|---------|--------|
| `Anthropic SDK nicht verfügbar` | `pip install anthropic>=0.39.0` |
| `Web search failed` | `pip install duckduckgo-search>=7.0.0` |
| Zu viele 1:1 | Temperature erhöhen (0.7 → 0.8) |
| Timeout | `timeout = 240` in config.ini |

### OpenAI
| Problem | Lösung |
|---------|--------|
| `401 Unauthorized` (Responses API) | Key braucht `api.responses.write` scope |
| `400 Invalid schema` | Chat Completions nutzt Schema, Responses nicht |
| Alle Tipps 1:1 | STRICT-Validator verwirft → Retry automatisch |
| Keine Websuche | Responses API nutzen, nicht Chat Completions |

### Beide
| Problem | Lösung |
|---------|--------|
| `Keine Paarungen erkannt` | Kicktipp DOM geändert → Parser anpassen |
| `Kein Feldnamen-Mapping` | Teamnamen-Synonyme erweitern |
| Login fehlgeschlagen | Zugangsdaten prüfen, CAPTCHA? |

## 💰 Kostenvergleich

### Claude Sonnet 4.5
- Input: ~$3 / 1M tokens
- Output: ~$15 / 1M tokens
- Extended Thinking: ~$3 / 1M tokens
- **Pro Spieltag: ~$0.05-0.15** (mit Thinking)

### OpenAI GPT-5
- Input: ~$3 / 1M tokens (estimated)
- Output: ~$15 / 1M tokens (estimated)
- Web Search: Inkludiert
- **Pro Spieltag: ~$0.10-0.20**

### OpenAI GPT-4o-mini (Budget)
- Input: $0.15 / 1M tokens
- Output: $0.60 / 1M tokens
- **Pro Spieltag: ~$0.01-0.03**

## 🎓 Erweiterte Nutzung

### Ensemble-Predictions
```python
# Beide Modelle nutzen, Ergebnisse kombinieren
claude_preds = run_claude_bot(matchday=10)
openai_preds = run_openai_bot(matchday=10)

# Consensus: Wo beide übereinstimmen
consensus = [c for c in claude_preds if c in openai_preds]

# Oder: Gewichteter Durchschnitt
final_preds = weighted_average(claude_preds, openai_preds, weights=[0.6, 0.4])
```

### Eigene Datenquellen
```python
# In claude/bot.py oder openai/bot.py
def web_search_tool(query: str) -> str:
    # Custom sources: Transfermarkt, Understat, etc.
    if "xG" in query:
        return fetch_from_understat(team)
    elif "injuries" in query:
        return fetch_from_transfermarkt(team)
    else:
        return duckduckgo_search(query)
```

### Fine-Tuning Gewichtungen (Claude)
```python
# In claude/bot.py → build_prompt_claude_advanced()
lines.append("### 1. AKTUELLE FORM (Gewichtung: 35%)")  # Erhöht von 30%
lines.append("### 3. NEWS & KADERSITUATION (Gewichtung: 20%)")  # Reduziert von 25%
```

## 🔒 Sicherheit & Compliance

### Configuration Setup

**Setup:**
1. Kopiere `config.ini.example` zu `config.ini` im jeweiligen Ordner (claude/ oder openai/)
2. Fülle deine persönlichen Credentials ein:
   - **OpenAI API Key** - Von: https://platform.openai.com/api-keys
   - **Anthropic API Key** - Von: https://console.anthropic.com
   - **Kicktipp Login** - Deine persönlichen Zugangsdaten
3. `config.ini` ist bereits in `.gitignore` und bleibt lokal

### Compliance

- **Rate Limiting**: Sequentielle Verarbeitung, built-in timeouts
- **Audit Trail**: Alle Responses gespeichert für Debugging
- **Wett-Compliance**: Prognosen sind statistische Schätzungen, keine Garantien
- **Kicktipp ToS**: Respektiere die Nutzungsbedingungen

## 📚 Vollständige Dokumentation

- **Claude**: Siehe [`claude/README.md`](claude/README.md) und [`claude/AGENTS.md`](claude/AGENTS.md)
- **OpenAI**: Siehe [`openai/README.md`](openai/README.md) und [`openai/AGENTS.md`](openai/AGENTS.md)

## 🤝 Welche Version soll ich wählen?

### Nutze **Claude Sonnet 4.5**, wenn du:
- ✅ Maximale Genauigkeit willst (Ziel: 1. Platz)
- ✅ Tiefe Analysen mit sichtbaren Reasoning bevorzugst
- ✅ Strukturierte, methodische Vorhersagen schätzt
- ✅ Bereit bist, etwas mehr zu bezahlen

### Nutze **OpenAI GPT-5**, wenn du:
- ✅ Eine bewährte Lösung willst
- ✅ Built-in Web Search bevorzugst (keine externe Lib)
- ✅ Flexiblere Prompts magst
- ✅ Bereits OpenAI-Credits hast

### Nutze **Beide**, wenn du:
- ✅ Ensemble-Predictions willst (höchste Genauigkeit)
- ✅ Vergleichen und lernen möchtest
- ✅ Redundanz für kritische Spieltage brauchst

## 📊 Beispiel-Output

```json
{
  "row_index": 1,
  "matchday": 10,
  "home_team": "FC Bayern München",
  "away_team": "RB Leipzig",
  "predicted_home_goals": 3,
  "predicted_away_goals": 1,
  "reason": "Form+Heimvorteil(+0.4xG)+Orban-Ausfall. H2H: 7W-2D. Odds: 1.65 → 60%."
}
```

## 🏆 Ziel: Erster Platz

Dieses Projekt wurde entwickelt, um **systematisch** bessere Predictions zu liefern als:
- Bauchgefühl-Tipper
- Quoten-basierte Bots (zu konservativ)
- Einfache KI-Prompts (zu generisch)

**Strategie:**
1. **Claude** für Hauptvorhersagen (natürliche, aber fokussierte Analyse)
2. **OpenAI** für Vergleich und Validierung
3. **Web Search** für aktuelle Infos (Verletzungen!)
4. **Optimierte Prompts** basierend auf erfolgreichen Tests
5. **Anti-Degeneration** für realistische Varianz

**Viel Erfolg beim Erreichen des ersten Platzes! 🥇**

## 📄 Lizenz & Haftungsausschluss

Dieses Projekt ist ein Automations-Prototyp für Bildungszwecke. Fußball ist stochastisch; **keine** Vorhersage ist garantiert richtig. Benutzung **auf eigene Verantwortung**.

Die Nutzung erfolgt im Rahmen der Kicktipp-Nutzungsbedingungen. Keine Gewinngarantie. Kein Wettanreiz.

## 🌟 Credits & Entwicklung

### Technologie-Stack
- **Claude Sonnet 4.5**: [Anthropic](https://www.anthropic.com) - Reasoning & Extended Thinking
- **OpenAI GPT-5**: [OpenAI](https://openai.com) - Alternative Implementation
- **Web Search**: DuckDuckGo (Claude), OpenAI Built-in
- **Kicktipp**: [kicktipp.de](https://www.kicktipp.de)

### Entwicklungsmethodik

Dieses Projekt ist ein **Experiment in KI-gestützter Softwareentwicklung**:

- **100% Vibe Coding**: Der gesamte Code wurde durch iterative AI-Pair-Programming-Sessions erstellt
- **AI-Generated Documentation**: Alle Markdown-Dateien, Prompts und Kommentare wurden von KI geschrieben
- **Entwicklungstools**: Claude Code, Anthropic Claude Sonnet 4.5
- **Menschliche Rolle**: Produktvision, Testing, Feedback, Quality Control

**Ziel des Experiments:** Demonstrieren der Möglichkeiten und Grenzen von AI-gestützter Softwareentwicklung in einem realen, funktionalen Projekt.

---

**Made with ⚽ + 🤖 through Vibe Coding for reaching 🥇**
