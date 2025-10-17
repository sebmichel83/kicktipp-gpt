# Kicktipp-GPT Bot - Claude Sonnet 4.5 Edition

Professionelle automatisierte Tippabgabe für Kicktipp-Spielrunden mit **Anthropic Claude Sonnet 4.5**. Diese Version nutzt modernste KI-Technologie mit optimierten Prompts für maximale Vorhersagegenauigkeit.

## 🎯 Projektübersicht

Der Bot automatisiert den gesamten Tippprozess:
1. **Login** bei Kicktipp.de
2. **Parsing** aller offenen Spiele mit Quoten
3. **KI-Analyse** mit Claude Sonnet 4.5 (inkl. Live-Recherche)
4. **Validierung** der Predictions (Anti-Degeneration)
5. **Submit** zum Portal mit Verifikation
6. **Audit Trail** aller Predictions und Prozesse

## ⭐ Hauptmerkmale

### KI-gestützte Analyse
- **Claude Sonnet 4.5** - Neuestes Reasoning-Modell von Anthropic
- **Natürliche Prompts** - Optimiert basierend auf erfolgreichen Tests
- **Live-Recherche** - Automatische Suche nach aktuellen Daten
- **Realistische Prognosen** - Keine monotonen Muster, fundierte Varianz

### Intelligente Verarbeitung
- **Robustes HTML-Parsing** - Automatische Team-Erkennung mit Datumsfilterung
- **Quoten-Integration** - H/D/A-Quoten in die Analyse einbezogen
- **Form-Analyse** - Letzte 5 Spiele, Tabellenposition, Momentum
- **Kontext-Bewusstsein** - Derby, Europa-Belastung, Verletzungen

### Qualitätssicherung
- **Strict Validation** - Exakte Anzahl Items, korrekte Indizes
- **Anti-Degeneration** - Verhindert zu viele 1:1 oder monotone Muster
- **Submit-Verifikation** - Reload & Feld-für-Feld-Check nach Submit
- **Retry-Logic** - Automatische Wiederholung bei Fehlern

## 🚀 Schnellstart

### Voraussetzungen

```bash
# Python 3.10+ erforderlich
python --version

# Virtual Environment erstellen (empfohlen)
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# oder
.venv\Scripts\activate  # Windows
```

### Installation

```bash
cd claude
pip install -r requirements.txt
```

**Wichtige Dependencies:**
- `anthropic>=0.39.0` - Claude API Client
- `requests` - HTTP-Requests
- `beautifulsoup4` - HTML-Parsing
- `duckduckgo-search>=7.0.0` - Web-Recherche (optional, aber empfohlen)

### Konfiguration

```bash
# Beispiel-Config kopieren
cp config.ini.example config.ini

# Config bearbeiten
nano config.ini  # oder vim, code, etc.
```

**Minimale config.ini:**
```ini
[auth]
username = dein.loginname@email.de
password = dein.passwort

[pool]
pool_slug = deine-gruppe

[anthropic]
api_key = sk-ant-...
model = claude-sonnet-4-5-20250929
temperature = 0.7
timeout = 180
max_retries = 3
use_extended_thinking = false

[run]
start_index = 1
end_index = 34
no_submit = false
```

### Erste Schritte

**1. Dry Run (ohne Submit):**
```bash
python bot.py --start-index 7 --end-index 7 --no-submit
```

Prüfe die Ausgabe:
- `out/forms/` - Geparste Formular-Daten
- `out/predictions/` - Generierte Tipps
- `out/raw_claude/` - Raw API-Responses

**2. Einzelner Spieltag (mit Submit):**
```bash
python bot.py --start-index 10 --end-index 10
```

**3. Alle Spieltage:**
```bash
python bot.py
# oder explizit:
python bot.py --start-index 1 --end-index 34
```

## 📊 Funktionsweise

### 1. Login & Formularabruf

```python
# Login mit Session-Management
login(session, username, password)

# Formular für Spieltag abrufen
html, url = fetch_tippabgabe(session, pool_slug, spieltag_index, tippsaison_id)
```

**Erkannte Daten:**
- Teamnamen (Home/Away)
- Eingabefelder (IDs für Submit)
- Quoten (H/D/A)
- Status (offen/geschlossen)

### 2. HTML-Parsing

Das Parsing ist **robust** und erkennt:
- ✅ Teamnamen aus verschiedenen Quellen (Logos, Titles, Text)
- ✅ Filtert Datums-/Zeitangaben aus (z.B. "18.10.25 18:30")
- ✅ Paarung von Heim-/Auswärts-Eingabefeldern
- ✅ Disabled-Status (geschlossene Spiele)

**Parser-Hierarchie:**
1. `data-team` Attribute (falls vorhanden)
2. Label-Tags (`<label for="...">`)
3. CSS-Selektoren (`.heim`, `.gast`, etc.)
4. Logo-Alt-Texte (`<img alt="...">`)
5. Text-Extraktion mit Filterung

### 3. KI-Analyse mit Claude

**Optimierter Prompt-Ansatz:**

```
Erstelle eine fundierte Prognose für den X. Bundesliga-Spieltag mit präzisen Torvorhersagen.

**Wichtig:** Recherchiere zunächst die aktuelle Bundesliga-Tabelle, Form der Teams
(letzte 5 Spiele), Verletzungen und aktuelle News.

**Zu analysierende Spiele:**
1. Bayern München vs Borussia Dortmund
   Quoten (H/D/A): 1.65 / 4.20 / 5.50
2. ...

**Für jedes Spiel berücksichtige:**
- Aktuelle Tabellenposition und Punktzahl
- Form der letzten 5 Spiele (Siege/Niederlagen/Tore)
- Verletzte oder gesperrte Schlüsselspieler (SEHR WICHTIG!)
- Head-to-Head Bilanz
- Heimvorteil (statistisch ~0.4 Tore Unterschied)
- Besondere Umstände (Derby, Europacup-Belastung)

**Realistische Ergebnisse erstellen:**
- Bundesliga-Durchschnitt: ~2.8 Tore pro Spiel
- Variation wichtig: Mix aus 2:1, 3:1, 1:0, 2:2, etc.
- Vermeide monotone Muster
- 1:1 nur bei echter Ausgeglichenheit
```

**Claude führt dann aus:**
1. Web-Recherche nach aktueller Tabelle
2. Suche nach Verletzungen/Sperren
3. Form-Analyse der Teams
4. Head-to-Head Statistiken
5. Erstellung fundierter Prognosen

### 4. Validierung

**Strict Mode Checks:**
```python
validate_predictions(preds, rows, matchday, forbid_degenerate=True)
```

- ✅ Exakt N Items (= Anzahl Spiele)
- ✅ `row_index` 1 bis N, keine Duplikate
- ✅ Teamnamen exakt wie im Formular
- ✅ Integer-Tore 0-9
- ✅ Max. 2-3 Draws (bei 9 Spielen)

**Bei Validierungsfehler:**
- Retry mit angepasstem Prompt
- Max. 3 Versuche (konfigurierbar)
- Logging aller Fehler

### 5. Submit & Verifikation

```python
submit_with_dom(session, pool_slug, spieltag, tippsaison_id,
                soup, form, rows, preds, url, attempts=2)
```

**Prozess:**
1. Formular mit Predictions befüllen
2. POST/GET zum Portal
3. **Reload** der Seite
4. **Feld-für-Feld Verifikation** (Eingabefelder prüfen)
5. Bei Abweichung: **Retry** (max. 2 Versuche)

**Erfolgsquote:**
- Zeigt X/9 gespeicherte Spiele
- Log-Eintrag bei Teil-Erfolg oder Fehler

## ⚙️ Konfiguration (Detailliert)

### [auth] - Zugangsdaten

```ini
[auth]
username = s.michel@example.com
password = sicheres-passwort
```

**Sicherheit:**
- Niemals in Git committen (`.gitignore` beachten)
- Alternativ: Umgebungsvariablen (`KICKTIPP_USERNAME`, `KICKTIPP_PASSWORD`)

### [pool] - Kicktipp-Gruppe

```ini
[pool]
pool_slug = meine-gruppe-2025
```

**So findest du den Slug:**
- URL: `https://www.kicktipp.de/meine-gruppe-2025/...`
- Der Teil nach `.de/` ist der Slug

### [anthropic] - Claude API

```ini
[anthropic]
api_key = sk-ant-api03-...
model = claude-sonnet-4-5-20250929
temperature = 0.7
timeout = 180
max_retries = 3
use_extended_thinking = false
```

**Parameter erklärt:**

| Parameter | Empfohlen | Beschreibung |
|-----------|-----------|--------------|
| `api_key` | - | API Key von [console.anthropic.com](https://console.anthropic.com) |
| `model` | `claude-sonnet-4-5-20250929` | Neuestes Sonnet 4.5 Modell |
| `temperature` | `0.6-0.8` | 0.5=konservativ, 0.7=balanced, 0.9=kreativ |
| `timeout` | `180` | Timeout in Sekunden (3 Min empfohlen) |
| `max_retries` | `3` | Anzahl Wiederholungen bei Validierungsfehler |
| `use_extended_thinking` | `false` | **false** = schneller (empfohlen), **true** = tieferes Reasoning |

**Extended Thinking:**
- `false` (Standard): Normale Analyse, Temperature=0.7, ~30-60s pro Spieltag
- `true`: Tiefere Analyse mit sichtbarem Reasoning, Temperature=1.0 (Anthropic-Anforderung), ~60-120s

### [run] - Ausführungsoptionen

```ini
[run]
start_index = 1
end_index = 34
no_submit = false
```

**Überschreibbar per CLI:**
```bash
python bot.py --start-index 10 --end-index 12 --no-submit
```

### [settings] - Erweitert

```ini
[settings]
# proxy = http://127.0.0.1:8080  # Optional: für Debugging (Burp, Fiddler)
```

## 📁 Ausgabe-Struktur

```
out/
├── forms/
│   └── 4001464_md7.json      # Geparste Formulardaten
├── predictions/
│   └── 4001464_md7.json      # Finale Tipps (nach Validierung)
└── raw_claude/
    └── md7_claude_try1.json  # Raw API-Response (inkl. Thinking)
```

### Beispiel: forms/4001464_md7.json

```json
{
  "matchday": 7,
  "tippsaison_id": "4001464",
  "rows": [
    {
      "index": 1,
      "home_team": "FC Bayern München",
      "away_team": "Borussia Dortmund",
      "home_field": "tipp[123][heim]",
      "away_field": "tipp[123][gast]",
      "open": true,
      "home_odds": 1.65,
      "draw_odds": 4.20,
      "away_odds": 5.50
    }
  ]
}
```

### Beispiel: predictions/4001464_md7.json

```json
[
  {
    "row_index": 1,
    "matchday": 7,
    "home_team": "FC Bayern München",
    "away_team": "Borussia Dortmund",
    "predicted_home_goals": 3,
    "predicted_away_goals": 1,
    "reason": "Bayern führt Tabelle mit 18 Punkten, 6 Siege. BVB Platz 2. Heimvorteil + Offensive (Kane, Musiala) entscheidend. H2H: 7W-2D für Bayern."
  }
]
```

### Beispiel: raw_claude/md7_claude_try1.json

```json
{
  "thinking": [],
  "response": "{\"predictions\": [...]}",
  "model": "claude-sonnet-4-5-20250929",
  "attempt": 1
}
```

## 🐛 Troubleshooting

### Häufige Probleme

#### 1. "Anthropic SDK nicht verfügbar"

**Lösung:**
```bash
pip install --upgrade anthropic>=0.39.0
```

#### 2. "ANTHROPIC_API_KEY fehlt"

**Ursache:** API Key nicht in config.ini oder ENV

**Lösung:**
```bash
# Option 1: config.ini
[anthropic]
api_key = sk-ant-...

# Option 2: ENV
export ANTHROPIC_API_KEY="sk-ant-..."
python bot.py
```

#### 3. "Keine Paarungen für Spieltag X erkannt"

**Ursachen:**
- Spieltag existiert nicht (z.B. Spieltag 35 bei 34-Spieltage-Liga)
- Kicktipp zeigt CAPTCHA
- DOM-Struktur geändert

**Debug:**
```bash
# Log-Ausgabe prüfen
python bot.py --start-index 7 --end-index 7 2>&1 | tee debug.log

# Formular-Daten prüfen
cat out/forms/4001464_md7.json | jq '.rows'
```

**Lösung:**
- Bei CAPTCHA: Manuell im Browser öffnen, CAPTCHA lösen, dann erneut versuchen
- Bei DOM-Änderung: Parser-Code anpassen (siehe AGENTS.md)

#### 4. "Teamnamen sind Datum/Zeit (z.B. 18.10.25 18:30)"

**Status:** ✅ Behoben seit v1.1

Der Parser filtert jetzt:
- Datums-Formate (dd.mm.yy)
- Zeit-Formate (hh:mm)
- Datums-Zeit-Kombinationen

**Falls trotzdem auftritt:**
```bash
# Prüfe out/forms/*.json
cat out/forms/4001464_md7.json | jq '.rows[] | {index, home_team, away_team}'
```

#### 5. "Claude predictions validated successfully, aber Submit fehlt"

**Ursache:** Alle Spiele geschlossen (disabled inputs)

**Prüfung:**
```json
// out/forms/4001464_md7.json
{
  "rows": [
    {
      "index": 1,
      "open": false  // <-- Problem!
    }
  ]
}
```

**Lösung:** Spieltag bereits abgeschlossen, nichts zu tun.

#### 6. "Validierung fehlgeschlagen: row_index außerhalb 1..N"

**Ursache:** Claude hat falsche Indizes generiert

**Lösung:** Automatischer Retry (max. 3x), normalerweise behebt sich selbst

**Falls persistent:**
```ini
[anthropic]
temperature = 0.6  # Konservativer (war 0.7)
max_retries = 5    # Mehr Versuche
```

#### 7. "Degenerierte Ausgabe: 5/9 Items sind 1:1"

**Ursache:** Claude generiert zu viele Unentschieden

**Lösung:** Automatischer Retry mit angepasstem Prompt

**Falls persistent:**
- Temperature erhöhen: `0.7 → 0.8`
- Prompt anpassen (siehe Abschnitt "Erweiterte Anpassung")

### Log-Analyse

**Wichtige Log-Zeilen:**

```
✅ Login scheint erfolgreich (Logout-Link erkannt).
✅ [Forms] Spieltag 7: 9 Spiele gespeichert.
✅ Claude predictions validated successfully: 9 items
✅ [Submit] Spieltag 7: 9/9 Spiele gespeichert.
```

**Fehler-Beispiele:**

```
❌ WARNING | Keine Paarungen für Spieltag 7 erkannt
   → DOM-Problem oder CAPTCHA

❌ WARNING | [Form] Spieltag 7: 8 Zeilen erkannt (erwarte 9)
   → Parser hat eine Zeile verpasst

❌ WARNING | Claude call fehlgeschlagen (try 1/3): ...
   → API-Error oder Validierungsfehler

❌ WARNING | [Verify] 7/9 verifiziert — zweiter Versuch …
   → 2 Spiele nicht korrekt gespeichert, Retry läuft
```

## 🔧 Erweiterte Anpassung

### Prompt-Optimierung

Datei: `claude/bot.py`, Funktion `build_prompt_claude_advanced()`

**Beispiel: Mehr Gewicht auf Verletzungen**

```python
lines.append("**Für jedes Spiel berücksichtige:**")
lines.append("- Verletzte oder gesperrte Schlüsselspieler (HÖCHSTE PRIORITÄT!)")  # Geändert
lines.append("- Aktuelle Tabellenposition und Punktzahl beider Teams")
# ...
```

**Beispiel: Spezifische Liga-Hinweise**

```python
lines.append("**Bundesliga-spezifisch:**")
lines.append("- Hohe Pressing-Intensität → Mehr Tore erwartet")
lines.append("- Heimvorteil besonders stark in Deutschland")
```

### Temperature-Tuning

**Richtlinien:**

| Temperature | Verhalten | Empfohlen für |
|-------------|-----------|---------------|
| 0.5 | Sehr konservativ, repetitiv | Test/Debug |
| 0.6 | Konservativ, konsistent | Sicherheit |
| **0.7** | **Balanced** (Standard) | **Normalfall** |
| 0.8 | Kreativ, variiert | Mutige Tipps |
| 0.9 | Sehr kreativ, überraschend | Experimentell |

**A/B-Testing:**

```bash
# Konservativ
python bot.py --temperature 0.6 --no-submit --start-index 10 --end-index 10
mv out/predictions/4001464_md10.json predictions_t06.json

# Kreativ
python bot.py --temperature 0.8 --no-submit --start-index 10 --end-index 10
mv out/predictions/4001464_md10.json predictions_t08.json

# Vergleichen
diff predictions_t06.json predictions_t08.json
```

### Extended Thinking aktivieren

**Wann sinnvoll:**
- Komplexe Spieltage (viele Derby, Topspiele)
- Nach schlechten Ergebnissen (Analyse vertiefen)
- Experimentell (Neugier auf Reasoning-Prozess)

**Aktivierung:**

```ini
[anthropic]
use_extended_thinking = true
timeout = 240  # Länger, da Extended Thinking mehr Zeit braucht
```

**Resultat:**
- Thinking-Prozess in `out/raw_claude/*.json`
- Temperature automatisch auf 1.0 gesetzt
- Längere Laufzeit (~60-120s statt 30-60s)

### Parser-Anpassung

**Falls Kicktipp DOM ändert:**

Datei: `claude/bot.py`

**1. Team-Namen-Selektoren erweitern:**

```python
# Zeile ~330
home = _extract_text(container, [
    ".heim", ".home", ".team-heim", ".teamhome", "[data-home]",
    ".team-name-home",  # NEU
    "[data-team-type='home']"  # NEU
])
```

**2. Input-Erkennung anpassen:**

```python
# Zeile ~225
scoreish = any(k in txt for k in [
    "tipp", "tor", "tore", "heim", "gast", "home", "away", "score",
    "prediction", "bet"  # NEU
])
```

**3. Debug-Output aktivieren:**

```python
# Zeile ~395
log.info(f"Gefundene Texte für Container: {texts}")  # DEBUG
home_name, away_name = _team_names_from_inputs(soup, container, home_inp, away_inp)
log.info(f"Extrahierte Namen: {home_name} vs {away_name}")  # DEBUG
```

## 📈 Performance-Optimierung

### Geschwindigkeit

**Standard-Laufzeit:**
- Login: ~2s
- Parsing pro Spieltag: <1s
- Claude API pro Spieltag: 30-60s (normal), 60-120s (Extended Thinking)
- Submit + Verify: ~3s
- **Gesamt pro Spieltag: ~40s**

**Für 34 Spieltage: ~20-25 Minuten**

**Optimierungen:**

1. **Parallele Verarbeitung** (manuell):
```bash
# Terminal 1
python bot.py --start-index 1 --end-index 17

# Terminal 2
python bot.py --start-index 18 --end-index 34
```

2. **Timeout reduzieren** (Risiko: Abbruch bei langsamem API):
```ini
[anthropic]
timeout = 120  # Statt 180
```

3. **Extended Thinking deaktivieren** (falls aktiviert):
```ini
[anthropic]
use_extended_thinking = false
```

### Kosten

**Claude Sonnet 4.5 Pricing (Stand Oktober 2025):**
- Input: ~$3 / 1M tokens
- Output: ~$15 / 1M tokens

**Schätzung pro Spieltag:**
- Prompt: ~1500 tokens (Input)
- Response: ~500 tokens (Output)
- Thinking (falls aktiviert): ~3000 tokens (Input)

**Kosten:**
- Normal: ~$0.012 pro Spieltag
- Extended Thinking: ~$0.020 pro Spieltag

**Saison (34 Spieltage):**
- Normal: ~$0.40
- Extended Thinking: ~$0.70

## 🏆 Best Practices

### 1. Dry Runs vor Live-Betrieb

```bash
# Immer zuerst testen
python bot.py --start-index 10 --end-index 10 --no-submit

# Predictions prüfen
cat out/predictions/4001464_md10.json | jq '.'

# Bei Zufriedenheit: Live
python bot.py --start-index 10 --end-index 10
```

### 2. Regelmäßige Updates

```bash
# Dependencies aktualisieren
pip install --upgrade anthropic requests beautifulsoup4

# Repository pullen (falls Git-basiert)
git pull origin main
```

### 3. Backup der Config

```bash
cp config.ini config.ini.backup.$(date +%Y%m%d)
```

### 4. Log-Rotation

```bash
# Alte Logs archivieren
mkdir -p logs/archive
mv *.log logs/archive/ 2>/dev/null || true
```

### 5. Predictions-Historie

```bash
# Predictions archivieren nach Saison
mkdir -p archive/2025-26
cp -r out/predictions/ archive/2025-26/
cp -r out/raw_claude/ archive/2025-26/
```

## 🔒 Sicherheit

### Zugangsdaten

**DO:**
- ✅ `config.ini` in `.gitignore`
- ✅ Umgebungsvariablen für CI/CD
- ✅ Separate Test-Accounts für Entwicklung

**DON'T:**
- ❌ Credentials in Code hardcoden
- ❌ Config-Dateien committen
- ❌ API Keys in Logs ausgeben (Masking aktiv)

### API-Limits

**Anthropic Limits (Typ 1 API Key):**
- 50 Requests / Minute
- 40,000 Tokens / Minute

**Bot-Verhalten:**
- Sequentielle Verarbeitung (1 Request pro Spieltag)
- Max. 3 Retries mit Backoff (2s, 4s, 6s)
- Keine Parallelisierung (Rate Limits schonen)

### Session-Handling

- Cookies nur im Memory (requests.Session)
- Kein persistentes Speichern von Session-Daten
- Automatisches Session-Cleanup nach Programmende

## 📚 Weiterführende Links

- **Anthropic Claude Docs**: https://docs.anthropic.com
- **Kicktipp**: https://www.kicktipp.de
- **Claude API Console**: https://console.anthropic.com
- **GitHub Issues**: (Pfad zu deinem Repository)

## 📄 Lizenz & Haftungsausschluss

Dieses Projekt ist ein Automations-Prototyp für Bildungszwecke. Fußball ist stochastisch; **keine** Vorhersage ist garantiert richtig. Benutzung **auf eigene Verantwortung**.

Die Nutzung erfolgt im Rahmen der Kicktipp-Nutzungsbedingungen. Keine Gewinngarantie. Kein Wettanreiz.

## 🤝 Support

Bei Problemen:
1. **README.md durchlesen** (dieses Dokument)
2. **Logs prüfen** (`debug.log`, Console-Output)
3. **out/ Dateien analysieren** (forms, predictions, raw_claude)
4. **AGENTS.md konsultieren** (technische Details)

---

**Version:** 1.1.0 (Oktober 2025)
**Autor:** AI-Assisted Development
**Status:** Production-Ready

**Letzte Änderungen:**
- ✅ Parser-Bugfix: Datum/Zeit-Filter
- ✅ Prompt-Optimierung: Natürlicher Stil
- ✅ Extended Thinking: Optional
- ✅ Temperature: Default 0.7
