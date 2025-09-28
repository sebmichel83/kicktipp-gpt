# Kicktipp-GPT Bot

Automatisierte Tippabgabe für Kicktipp-Spielrunden mit einer OpenAI-gestützten
Prognose-Pipeline. Das Projekt sammelt die offenen Spiele eines Spieltages,
fordert das Modell zu quellengestützten Vorhersagen auf und trägt die Tipps im
Portal ein.

Der Bot

1) loggt sich in `kicktipp.de` ein,  
2) lädt für jeden Spieltag das **Tippformular**, parst **genau die 9 Paarungen** (Index 1..9) samt Eingabefeldern, Quoten (falls angezeigt) und Status (offen/gesperrt),  
3) erzeugt mit **OpenAI** für **jede** Paarung **konkrete Ergebnisprognosen (Integer‑Tore)** in einem strikten JSON‑Schema,  
4) **trägt die Ergebnisse im Portal ein**, sendet das Formular ab und **verifiziert durch Reload**,  
5) speichert Rohdaten & Diagnosen lokal ab.

> **Wichtig:**  
> - Die in `bot.py` verwendete Vorhersagefunktion **nutzt aktuell die Websuche/Tools**. Sie ruft das **Chat Completions API** mit einem **JSON‑Schema** auf.  
> - Das Log zeigt den Text `OpenAI[responses] ... (Websuche aktiv)`, **faktisch** wird aber *Chat* verwendet (kein `tools=[{"type": "web_search"}]`).  
> - Eine echte Websuche per **Responses API** ist in `openai_predictor.py` (Klasse `OpenAIPredictor`) vorbereitet; `bot.py` verwendet diese Klasse derzeit **nicht**. Unten steht, wie man Websuche optional aktiviert.
---

## Features

- **STRICT Mode** (Standard):
  - Erwartet **exakt N** Items vom LLM (N = Anzahl gelisteter Spiele).  
  - **Kein 1:1‑Fallback**. Antworten mit zu vielen `1:1` werden verworfen.  
  - **Portal‑Submit + Verifikation**: Nach Absenden wird das Formular erneut geladen und Feld‑für‑Feld geprüft.
- **Heuristische Notbremse** (optional via `--allow-heuristic-fallback`):  
  Wenn OpenAI fehlschlägt, wird **aus Quoten** ein Ergebnis geschätzt (z. B. `2:0`, `0:2`, `2:1`; `1:1` nur bei klarer Remis‑Quote).
- **Lokal‑Artefakte**:
  - `out/forms/{tippsaison}_md{X}.json` – geparste Formularzeilen inkl. Feldnamen
  - `out/predictions/{tippsaison}_md{X}.json` – final genutzte Tipps (nach Validierung)
  - `out/raw_openai/md{X}_try{n}.json` – Rohantworten des LLM (für Debug)

---

## Highlights

- **Websuche standardmäßig aktiv** – sowohl `bot.py` als auch
  `openai_predictor.py` nutzen die OpenAI Responses API inklusive
  `web_search`-Tool, um Quoten, Verletzungsnews und weitere Evidenz live
  nachzuschlagen.
- Strenges JSON-Schema mit Validierung der Modellantworten, um fehlerhafte
  Tippreihen zu erkennen.
- Optionaler Fallback auf Chat Completions (ohne Websuche), falls die
  Responses-API nicht verfügbar ist.

---

## Systemvoraussetzungen

- Python 3.10+ (getestet mit 3.11)
- Abhängigkeiten:
  - `requests`
  - `beautifulsoup4`
  - `openai>=1.40.0` (getestet mit 1.109.1)
- Ein Kicktipp‑Account mit Zugriffsrechten für den Ziel‑Pool
- OpenAI API Key

Installation (in einer venv empfohlen):

```bash
pip install -U requests beautifulsoup4 "openai>=1.40,<2"
```

---

## Konfiguration

### Reihenfolge der Werteauflösung
**CLI > ENV > config.ini > Default**

### `config.ini` (optional)

Die Keys können in `DEFAULT`, `auth`, `kicktipp`, `pool`, `openai`, `run`, `settings` liegen.

```ini
[auth]
username = dein.loginname
password = dein.passwort

[pool]
pool_slug = group-name

[openai]
api_key = sk-...
model = gpt-4o-mini        ; Standard im Code
temperature = 0.4
oa_timeout = 45
max_retries = 3
promptprofile = research    ; nutzt "Research"-Prompt, allerdings ohne Tools (siehe Hinweis)

[run]
start_index = 1
end_index   = 34
no_submit   = false
allow_heuristic_fallback = false

[settings]
proxy = http://127.0.0.1:8080
```

### Umgebungsvariablen (Auszug)

- `KICKTIPP_USERNAME`, `KICKTIPP_PASSWORD`, `POOL_SLUG`
- `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_TEMPERATURE`, `OPENAI_TIMEOUT`, `OPENAI_MAX_RETRIES`, `OPENAI_PROMPT_PROFILE`
- `HTTPS_PROXY`, `HTTP_PROXY` (optional)

---

## Benutzung

### Minimalbeispiel (nur ein Spieltag, mit Submit)

```bash
python bot.py \
  --username "$KICKTIPP_USERNAME" \
  --password "$KICKTIPP_PASSWORD" \
  --pool-slug "group-name" \
  --start-index 5 --end-index 5 \
  --openai-key "$OPENAI_API_KEY" \
  --model "gpt-5" \
  --temperature 0.4
```

### Range (alle Spieltage), **ohne** Submit (Trockenlauf)

```bash
python bot.py --config config.ini --no-submit
```

### Heuristik im Notfall erlauben

```bash
python bot.py --config config.ini --allow-heuristic-fallback
```

### Proxy (für Kicktipp & OpenAI)

```bash
python bot.py --proxy http://127.0.0.1:8080
# oder via ENV: HTTPS_PROXY/HTTP_PROXY
```

---

## Wie der Bot arbeitet (Details, passend zum Code)

### 1) Login & Formularabruf
- Login über `GET /info/profil/login` + `POST /info/profil/loginaction`  
- Danach `GET /{pool_slug}/tippabgabe?spieltagIndex={i}`
- Aus dem HTML werden **genau 9 Spiele** extrahiert:
  - Teamnamen (Heim/Gast)
  - **Eingabefeld‑Namen** für Heim‑/Gasttore (`home_field`, `away_field`)
  - Quoten H/D/A (falls im DOM erkennbar)
  - Offenheit (`open` = nicht `disabled`)

> Hinweis: Wenn Kicktipp das Markup ändert, können weniger/mehr als 9 Zeilen erkannt werden (es wird auf 9 gekappt). Die extrahierten Zeilen landen in `out/forms/...` – dort sieht man die tatsächlichen Feldnamen, die beim Submit benutzt werden.

### 2) Prompting & OpenAI‑Aufruf
- `bot.py` nutzt `call_openai_predictions_strict(...)` mit **Chat Completions** (**ohne Tools**) und einem **JSON‑Schema**.  
- **Profil `research`** (Standard) formuliert einen evidenzbasierten Prompt (Quellen, Quoten, Form etc.) – **es werden aber _keine_ Web‑Requests durch das Modell ausgeführt**, da Chat Completions hier keine Websuche erhält.
- Das Schema erzwingt pro Spiel:
  - `row_index` (1..N), `matchday`, `home_team`, `away_team`,
  - `predicted_home_goals` (int), `predicted_away_goals` (int),
  - `reason` (<= 250 Zeichen),
  - zusätzliche Felder `probabilities`, `top_scorelines`, `odds_used`, `sources` (dürfen `null`/leer sein).
- **Validierung**: exakt N Items, korrekte Reihenfolge/Indizes, Integer‑Tore 0..9, zu viele `1:1` ⇒ Fehler.

**Wichtig:** Das Log zeigt für das Research‑Profil
```
OpenAI[responses] call: model=..., (Websuche aktiv)
```
Der tatsächliche Call im Code ist aber:
```
client.chat.completions.create(...)
```
→ **Keine Tools/Websuche aktiv.**

### 3) Submit & Verifikation
- Die vorher gespeicherten `home_field`/`away_field`‑Namen werden mit den vorhergesagten Toren befüllt.  
- Formular wird abgesetzt (**POST** oder **GET**, je nach `form.method`), anschließend wird die Seite neu geladen.  
- **Verifikation:** Für jede Zeile wird geprüft, ob die Eingabefelder jetzt exakt die eingetragenen Werte tragen.  
- Ergebnis im Log:  
  `"[Submit] Spieltag X: Y/9 Spiele gespeichert."`  
  Bei Teil‑Erfolg wird ein zweiter Versuch unternommen (mit dem neu geladenen DOM).

### 4) Artefakte
- `out/forms/{tippsaison}_md{X}.json` – geparste Formularstruktur (wichtige Hilfe bei Parsing‑/Mapping‑Fehlern)
- `out/predictions/{tippsaison}_md{X}.json` – finale Tipps (nur die für den Submit benötigten Felder)
- `out/raw_openai/md{X}_try{n}.json` – Rohantwort pro Versuch

---

## Typische Logs verstehen

- **„[Forms] Spieltag X: 9 Spiele gespeichert.“**  
  → 9 Zeilen erkannt & lokal abgelegt.
- **„Keine Paarungen für Spieltag X erkannt — überspringe.“**  
  → DOM passte nicht zu den Heuristiken; siehe `out/forms` des angrenzenden Spieltags.
- **„Validierung fehlgeschlagen … Degenerierte Ausgabe: … 1:1 …“**  
  → LLM lieferte zu viele Remis; es wird erneut versucht (bis `--max-retries`).
- **„[Submit] … FEHLER: Keine Tipp-Felder befüllbar.“**  
  → Alle Inputs sind `disabled` (Spiel(e) geschlossen) **oder** es wurden keine Feldnamen gefunden. Ohne offene Felder kann der Bot nichts eintragen.

---

## Aktivieren von Websuche (optional)

Aktuell nutzt `bot.py` **keine** Websuche. Zwei Wege, um Live‑Quellen zu erlauben:

### A) `openai_predictor.py` integrieren (empfohlen, vorhanden)
- Dort ist `OpenAIPredictor._via_responses_with_websearch(...)` bereits implementiert:
  ```py
  resp = self.client.responses.create(
      model=self.model,
      input=[{"role":"system","content": ...},
             {"role":"user","content": user_prompt}],
      tools=[{"type": "web_search"}],
      temperature=self.temperature,
      ...
  )
  ```
- **Schritte:**
  1. `from openai_predictor import OpenAIPredictor, MatchLine` in `bot.py` importieren.
  2. Statt `call_openai_predictions_strict(...)` den Predictor verwenden **und** die Matchzeilen (`Row`) in `MatchLine` konvertieren.
  3. Die geparste JSON‑Antwort mit `_validate_and_fix_predictions` o. ä. validieren (oder schlicht die Torwerte übernehmen).

### B) Minimal‑Patch in `bot.py` (direkt in `call_openai_predictions_strict`)  
Ersetze den Block im „Research“-Zweig durch einen **Responses**‑Aufruf **mit** Tools und parse das JSON aus `resp.output_text`.  
Beispiel‑Skizze (ohne Gewähr):

```py
resp = client.responses.create(
    model=model,
    input=[
        {"role": "system", "content": "Antworte ausschließlich in Deutsch. Gib NUR ein JSON-Objekt mit 'predictions' aus."},
        {"role": "user", "content": prompt},
    ],
    tools=[{"type": "web_search"}],
    temperature=temperature,
)
text = getattr(resp, "output_text", None) or _responses_join_output_text(resp)
data = _extract_json_object(text)
preds = data.get("predictions")
fixed = validate_predictions(preds, rows, matchday_index, forbid_degenerate=True)
```

> **Achtung:** Für die Responses‑API braucht dein API‑Key die **Scope** `api.responses.write`. Ohne diese kommt `401 Unauthorized`
> („You have insufficient permissions… Missing scopes: api.responses.write“).

---

## Troubleshooting

### „Nicht alle Spiele gespeichert“
- Ursache 1: Einige Spiele sind **geschlossen** (`disabled`‑Inputs). → Ohne offene Felder ist kein Submit möglich.  
- Ursache 2: DOM/Parsing hat falsche/fehlende `home_field`/`away_field` erkannt. → Öffne `out/forms/...` und prüfe die Feldnamen.  
  - Falls nur 8/9 Spiele erkannt wurden: Kicktipp‑Markup änderte sich; Heuristiken in `parse_rows_from_form()` anpassen (z. B. Selektoren für Teamnamen/Quoten, Gruppierung der Inputs).

### „Alle Tipps sind 1:1“
- Der **STRICT**‑Validator verwirft Ausgaben mit zu vielen `1:1` und versucht es erneut.  
- Falls du die heuristische Notbremse aktiviert hast (`--allow-heuristic-fallback`), nimmt die Heuristik **nur dann** `1:1`, wenn die **Remis‑Quote** klar dominiert.

### „401 Unauthorized“ beim (echten) Responses‑Call
- Deinem Key fehlt die Scope `api.responses.write`, oder du verwendest einen projektgebundenen Key ohne die Berechtigung.  
- Lösung: In der OpenAI‑Konsole Key mit entsprechender Berechtigung erzeugen.

### „Keine Paarungen erkannt“
- Prüfe, ob die Pool‑Seite CAPTCHA/Sicherheitsblockaden zeigt.  
- Prüfe HTML in `out/forms` des vorherigen/nächsten Tages – manchmal liefert Kicktipp Zwischenseiten.

---

## Sicherheit & Compliance

- Zugangsdaten werden **nicht** gespeichert; sie werden nur für die Session verwendet.  
- **Wett‑Compliance:** Prognosen sind **statistische Einschätzungen** ohne Gewinngarantie.  
- Nutze das Tool im Rahmen der Kicktipp‑Regeln und respektiere die AGB.

---

## Beispiel‑Outputs

```json
{
  "row_index": 5,
  "matchday": 10,
  "home_team": "Eintracht Frankfurt",
  "away_team": "Werder Bremen",
  "predicted_home_goals": 2,
  "predicted_away_goals": 1,
  "reason": "Odds 1.85 H; xG +0.35; Heimvorteil.",
  "probabilities": null,
  "top_scorelines": null,
  "odds_used": null,
  "sources": null
}
```

---

## Haftungsausschluss

Dieses Projekt ist ein praktischer Automations‑Prototyp. Fußball ist stochastisch; **keine** Vorhersage ist garantiert richtig. Benutzung **auf eigene Verantwortung**.

