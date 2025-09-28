# Kicktipp Bundesliga Auto‑Predictor (GPT‑5 + Web Search)

Automatisiert **Bundesliga‑Tipps** für deine Kicktipp‑Runde: Das Skript loggt sich ein, generiert **fundierte Ergebnisprognosen** mit **OpenAI GPT‑5** inklusive **Websuche & Quellenangaben** und **trägt die Tipps direkt im Kicktipp‑Portal** ein. Alle Prognosen werden zusätzlich **lokal versioniert** gespeichert (Reproduzierbarkeit & Debugging).

---

## Highlights

- ✅ **Portal‑Submission**: Füllt die Tippfelder im Kicktipp‑Formular inkl. CSRF‑Handling und verifiziert den Erfolg (Re‑Fetch & Abgleich).
- 🔎 **Live‑Recherche** (optional): Aktiviert **`web_search`** (Responses‑API) für frische Infos zu Aufstellungen, Verletzungen, Wetter, Quoten – mit **Zitaten/Links**.
- 🧠 **Starker Prompt**: Integrierter **FootballPred LLM**‑Prompt (Evidenz, xG/Elo, bivariate Poisson, Kalibrierung, Konsistenzchecks).
- 🧭 **100 % Coverage‑Guard**: Kein „1:1‑Fallback“. Wenn das Schema fehlschlägt oder Spiele fehlen → **neuer API‑Call / Eskalation** (GPT‑5 heavy), **keine Platzhalter**.
- 🧩 **Fuzzy‑Mapping**: Robust gegen Teamnamen‑Varianten (Synonyme, Ligakürzel, Sonderzeichen). Konfigurierbare **Schwelle** + **Synonym‑Datei**.
- 🧪 **Dry‑Run & Inspektions‑Modus**: HTML‑Dump, Mapping‑Tabelle, ohne Submission – ideal zum Troubleshooting.
- 🧰 **Konfigurierbar**: `config.ini` **oder** Umgebungsvariablen; CLI‑Flags haben oberste Priorität.
- 📝 **Transparente Logs**: Detaillierte DEBUG/INFO‑Logs, damit du sofort siehst, **warum** etwas nicht gemappt/gespeichert wurde.

> **Wichtig:** Bitte beachte die Nutzungsbedingungen von Kicktipp und lokales Recht (z. B. bzgl. Wetten). Dieses Projekt liefert **statistische Einschätzungen**, **keine Gewinnzusagen**.

---

## Architektur in Kürze

1. **Login & Session** → liest CSRF & Session‑Cookies, prüft Erfolg (Logout‑Link / Profil‑Redirect).
2. **Spieltag‑Erfassung** → ruft `tippabgabe?spieltagIndex=X` ab, extrahiert **9 Paarungen** (idempotent).
3. **Vorhersage (OpenAI)**  
   - **Primär:** **GPT‑5** via **Responses‑API** mit `tools=[{"type": "web_search"}]`.  
   - **Fallback:** Chat Completions mit **strict JSON Schema** (keine Websuche), **oder** `gpt-5-mini`.
   - Prompt: FootballPred LLM (Evidenz, xG/Elo, Poisson, Quellenpflicht).
4. **Parser & Guards** → validiert Schema, verhindert **1:1‑Degeneration**, prüft Plausibilität (Summe 1X2=1 etc.).
5. **Mapping** → fuzzy Zuordnung *Vorhersage ↔ Formularfeld* (Synonyme + Levenshtein‑Score). Wenn Ambiguität: Top‑Kandidat + Log‑Hinweis.
6. **Submission** → POST mit allen Tipps; Verifikation durch erneutes Laden & Abgleich.
7. **Persistenz** → speichert JSON je Spieltag unter `out/predictions/{tippsaisonId}_md{X}.json`.

Weitere Details: siehe **[agents.md](./agents.md)** (Agenten, Prompts, Tools, Fehlerpfade).

---

## Voraussetzungen

- **Python 3.11+**
- **pip** / **uv** (optional)
- **OpenAI Python SDK** `>= 1.109.0`
- Netzwerkzugriff auf `api.openai.com` und `kicktipp.de`

---

## Installation

```bash
git clone <this-repo>
cd kicktipp

# (Empfohlen) Virtuelle Umgebung
python3 -m venv .venv
source .venv/bin/activate

# Abhängigkeiten
pip install -r requirements.txt
```

> Nutzt du **uv**: `uv pip install -r requirements.txt`

---

## Konfiguration

### 1) `config.ini` (empfohlen)

Erstelle eine Datei `config.ini` im Projektroot:

```ini
[openai]
api_key = sk-...
base_url = https://api.openai.com/v1
model_primary = gpt-5
model_fallback = gpt-5-mini
use_responses_api = true
allow_web_search = true
# Responses-API erfordert Key mit passendem Scope:
#   api.responses.write  (+ web_search capability)

[kicktipp]
base_url = https://www.kicktipp.de
group_slug = jhb-grosse-jungs
username = deine.email@example.com
password = deinPasswort
user_agent = KicktippBot/1.0 (+contact)

[predictions]
season = 2025/26
matchday_start = 1
matchday_end = 34
strict_coverage = true
anti_draw_degen = true            # verhindere triviale 1:1-Massen
min_total_goals_sigma = 0.15      # Anti-Degeneration (nur wenn plausibel)
backfill_strategy = odds_poisson  # nutzt Quoten zur Plausibilisierung

[mapping]
fuzzy_threshold = 86
synonyms_file = ./data/synonyms.yaml

[network]
timeout_sec = 20
max_retries = 3
proxy =

[storage]
out_dir = ./out
log_level = INFO
```

### 2) Umgebungsvariablen (override)

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://api.openai.com/v1
export OPENAI_USE_RESPONSES=true
export OPENAI_ALLOW_WEB_SEARCH=true

export KICKTIPP_USER=deine.email@example.com
export KICKTIPP_PASS=deinPasswort
export KICKTIPP_GROUP=jhb-grosse-jungs
```

> **Priorität:** **CLI‑Flags** → **ENV** → **config.ini**

---

## Nutzung (CLI)

### Standard‑Run (alle Spieltage)

```bash
python3 bot.py \
  --group jhb-grosse-jungs \
  --from 1 --to 34 \
  --model gpt-5 \
  --use-web \
  --save-portal
```

### Nur einen Spieltag laufen lassen

```bash
python3 bot.py --group jhb-grosse-jungs --md 7 --use-web --save-portal
```

### Dry‑Run (keine Submission, Mapping/Schema prüfen)

```bash
python3 bot.py --group jhb-grosse-jungs --md 7 --use-web --dry-run --dump-dom
```

### Fallback hart auf Chat‑Completions (ohne Websuche)

```bash
python3 bot.py --group jhb-grosse-jungs --md 7 --force-chat
```

**Wichtige Flags**

- `--use-web`: aktiviert `web_search` in der Responses‑API.
- `--force-chat`: überspringt Responses‑API & Tools, nutzt Chat Completions.
- `--dry-run`: keine Submission, nur Ausgabe/Logs.
- `--dump-dom`: speichert HTML‑Dump & Mapping‑Tabelle unter `out/debug`.
- `--strict-coverage`: bricht ab, wenn <9 Spiele gemappt/submittet werden konnten.

---

## Wie es mit OpenAI arbeitet

### Responses‑API (mit `web_search`)

```python
from openai import OpenAI
client = OpenAI(api_key=..., base_url=...)

resp = client.responses.create(
    model="gpt-5",
    input=render_prediction_prompt(fixtures_block, meta),
    tools=[{"type": "web_search"}],   # Live-Daten + Zitate
    temperature=0.4
)
text = resp.output_text  # enthält JSON (vom Prompt erzwungen)
```

> **401 „Missing scopes: api.responses.write“?**  
> Erzeuge einen **Project API Key** mit **Responses‑Rechten** und aktivierter **Websuche**. Alternativ: `--force-chat` verwenden.

### Chat Completions (Strict JSON Schema, ohne Websuche)

```python
resp = client.chat.completions.create(
  model="gpt-5-mini",
  messages=[
    {"role": "system", "content": "Antworte NUR mit JSON ..."},
    {"role": "user", "content": fixtures_block}
  ],
  response_format={
    "type": "json_schema",
    "json_schema": {
      "name": "bundesliga_predictions",
      "strict": True,
      "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
          "predictions": {
            "type": "array",
            "minItems": 1,
            "items": {
              "type": "object",
              "additionalProperties": False,
              "required": [
                "matchday","home_team","away_team",
                "predicted_home_goals","predicted_away_goals","reason"
              ],
              "properties": {
                "matchday": {"type": "integer"},
                "home_team": {"type": "string"},
                "away_team": {"type": "string"},
                "predicted_home_goals": {"type": "integer"},
                "predicted_away_goals": {"type": "integer"},
                "reason": {"type": "string","maxLength": 250}
              }
            }
          }
        },
        "required": ["predictions"]
      }
    }
  },
  temperature=0.4
)
```

> **Schema‑Fehler 400 „type: array“**: Bei Chat Completions **muss** das Top‑Level‑Schema **`type: object`** sein. (Der Fehler entstand, wenn direkt `type: array` verwendet wurde.)

---

## Prompt (gekürzt, integriert)

- **System‑Rolle:** „FootballPred LLM“ – evidenzbasiert, zitiert Quellen, modelliert bivariate Poisson / Skellam, kalibriert Wahrscheinlichkeiten, prüft Konsistenz, **keine Wetten**.
- **User‑Prompt:** Übergibt **Spieltags‑Block** (9 Spiele mit Quoten & Status), Liga/Saison/Matchday, Constraints (`max_data_age_hours`, Märkte).
- **Output‑Contract:** **Nur JSON** mit `predictions[]` (Pflichtfelder) – plus optional `probabilities`, `sources`.
- **Guards gegen 1:1‑Degeneration:** Der Parser **rejectet** uniforme/unkonsistente Outputs und fordert Neu‑Generierung an (ggf. mit `gpt-5`).

Details & Volltext siehe **agents.md**.

---

## Portal‑Submission & Mapping

- Formular‑Selectors (stabilisiert):  
  - Extrahiert jedes Spiel (Home/Away‑Text) + **Eingabefeld‑Namen** (z. B. `tipp_1_h`, `tipp_1_a` – je nach Runde).
  - **Synonyme & Normalisierung**: entfernt Punkte, Akzente, „1. FC“, „Bor.“, „TSG“, etc.
  - **Fuzzy**: Levenshtein‑Ähnlichkeit mit Schwelle (Default **86**).

### Typische Mapping‑Warnungen & Behebung

- `Kein Feldnamen-Mapping gefunden für: 1. FC Köln vs RB Leipzig`  
  → **Synonyme ergänzen** in `data/synonyms.yaml` (z. B. `"RB Leipzig": ["RasenBallsport Leipzig","Leipzig"]`).  
  → **Schwelle** in `[mapping] fuzzy_threshold` ggf. auf 82 senken.  
  → `--dump-dom` nutzen, um zu sehen, wie Kicktipp die Teams schreibt.

- `FC Augsburg vs FC Augsburg`  
  → Hinweis auf **Parser‑Artefakt** (z. B. doppeltes Node‑Match). Aktualisiere Selektoren/Regex; `--dump-dom` liefert die betroffenen HTML‑Zeilen.

- `…: Keine Tipp-Felder konnten befüllt werden (evtl. alle Spiele geschlossen?)`  
  → Prüf im DOM‑Dump, ob Felder `disabled` sind bzw. ob Kicktipp den Spieltag „geschlossen“ hat.

Nach Submission lädt das Skript die Seite erneut und verifiziert, ob die **eingegebenen Tore** im DOM stehen. Bei Abweichung → **Retry** mit kleiner Backoff‑Zeit.

---

## Logs lesen (Beispiele aus Praxis)

- `OpenAI[responses] call …` → Responses‑API; **401** mit *Missing scopes* ⇒ Key/Scope korrigieren **oder** `--force-chat` nutzen.
- `OpenAI[chat] call …` + `response_format: json_schema` → Chat‑Fallback mit **strict** Schema.
- `[Forms] Spieltag X: 9 Spiele gespeichert.` → DOM‑Parser fand **9 Paarungen** (gut).
- `[Predictions] Spieltag X: 9 Vorhersagen gespeichert` → LLM lieferte **9 valide Predictions** (lokal gespeichert).
- `[Submit] Spieltag X: n Spiele erfolgreich gespeichert.` → **n** Tipps wurden ins Portal übernommen (sollte **9** sein; bei weniger siehe Mapping‑Warnungen).

---

## Best Practices

- **Vor Lauf:** `--dry-run --dump-dom` einmal pro Runde (nach Kicktipp‑Updates).
- **Synonyme pflegen:** Besonders für Auf‑/Absteiger & Kurzschreibweisen („Bor. M’gladbach“).
- **Responses‑Scopes:** Für Websuche unbedingt Key mit **api.responses.write** nutzen.
- **Rate‑Limit:** Zwischen Submissionen kleine Pausen (das Skript tut das automatisch).
- **Compliance:** Keine automatischen Tippänderungen knapp vor Anstoß, wenn das Reglement es untersagt.

---

## Troubleshooting (bekannte Fälle)

1) **Alle Tipps 1:1**  
   - Ursache: LLM‑Output nicht geparst → früherer Fallback.  
   - Fix: **Strict JSON Schema** + **Anti‑Degeneration** + Retry/Eskalation auf `gpt-5`.

2) **„Invalid schema … type: array“ (400)**  
   - Bei **Chat Completions** muss das Top‑Level **`type: object`** sein.

3) **„Missing scopes: api.responses.write“ (401)**  
   - Key/Projektrollen prüfen **oder** `--force-chat` ohne Websuche nutzen.

4) **„Kein Feldnamen‑Mapping gefunden …“**  
   - Synonyme ergänzen, Fuzzy‑Schwelle justieren, `--dump-dom` auswerten.

5) **„Keine Paarungen erkannt — überskippe“**  
   - Selektoren nach Kicktipp‑Änderungen anpassen; `--dump-dom` liefert HTML zur Analyse.

---

## Entwicklung & Tests

- **Linters/Format:** `ruff`, `black` (optional)
- **Test‑Läufe:** `--dry-run` + lokale JSON‑Snapshots in `out/predictions/`
- **Debug HTML:** `out/debug/*.html` (nur mit `--dump-dom`)

---

## Sicherheit & Datenschutz

- **API‑Keys** nie committen. Nutze `.env` oder CI‑Secrets.
- **Credentials** (Kicktipp) nur lokal/gesichert speichern.
- **Robots / ToS** respektieren; exzessive Requests vermeiden.

---

## Lizenz

MIT – siehe `LICENSE` (oder anpassen, falls privat).

---

## Danksagung

- OpenAI API & Web Search
- Bundesliga Daten‑Communities & Analysen
- Alle Maintainer/Contributors ✌️

---

### Quickstart TL;DR

```bash
# 1) config.ini anlegen (siehe oben) oder ENV setzen
# 2) Dependencies installieren
pip install -r requirements.txt

# 3) Run – kompletter Spieltag inkl. Websuche & Portal‑Submission
python3 bot.py --group jhb-grosse-jungs --md 7 --use-web --save-portal
```

Viel Erfolg & gute Punkte! ⚽
