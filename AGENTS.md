# Agents & Orchestration – Kicktipp Prediction Bot

This document describes the **agent-style architecture** used by `bot.py` to log in to Kicktipp, fetch fixtures, generate predictions with **OpenAI GPT‑5 + Web Search**, and submit tips to the portal with verification and retry. It also covers prompts, tools, routing, failure handling, and how to extend the system.

> **Goal:** *Every open game must receive a valid, non-degenerate score prediction and be saved to the Kicktipp portal.*


## TL;DR

- **Predictor Agent** uses **GPT‑5 with `web_search`** (Responses API) and falls back to Chat Completions (JSON Schema) when needed.
- **Parser/Submit Agents** scrape Kicktipp forms, map teams → input fields (fuzzy), post tips, and **verify** via page reload; **retry once** if needed.
- Guards against **degenerate outputs** (e.g., 1:1 everywhere) and **backfills** missing pairs from odds (no 1:1 default).
- All configuration via `config.ini` (or ENV). **Responses API requires `api.responses.write` scope** for web search.


## High-Level Architecture

```mermaid
flowchart LR
  subgraph Kicktipp
    TK[Login & Pages]
    TForm[Tippabgabe Form]
  end

  subgraph Bot
    O[Orchestrator]
    P["Parser Agent\n+ Fuzzy Mapper"]
    PR["Predictor Agent\nGPT-5 + Web Search"]
    S["Submit Agent\n+ Verify and Retry"]
    J["Persistence (Audit JSON)"]
  end

  %% edges
  TK <--|GET| O
  O --> P
  P --> PR
  PR --> J
  PR --> S
  S -->|POST| TForm
  S <--|GET verify| TForm
  O -->|loop 1..34| TK

```

### Agents (Conceptual Roles)

1. **Orchestrator**
   - Controls matchday loop (1..34), backoff, and logging.
2. **Parser Agent**
   - Loads Tippabgabe page, extracts `tippsaisonId`, hidden fields (CSRF), and **rows** (team names + input names for home/away).
   - Team normalization + fuzzy mapping helpers.
3. **Predictor Agent**
   - Builds prompts and calls OpenAI:
     - **Primary**: Responses API with `model=gpt-5` and `tools=[{"type":"web_search"}]`.
     - **Fallback**: Chat Completions with JSON Schema (`model=gpt-5-mini`) when Responses is unavailable or unscoped.
   - Post-processes predictions:
     - Schema validation & clipping
     - Anti-degeneration (limit draw share)
     - **Backfill** missing pairs from odds (no 1:1 default)
4. **Submit Agent**
   - Posts tips to Kicktipp with all CSRF inputs.
   - **Verify** (reload) and **retry once** for missing values.
5. **Persistence**
   - Audits predictions to `out/predictions/{tippsaisonId}_md{N}.json` for reproducibility.


## Prompts & Schemas

### System Prompt (Predictor Agent)

The bot uses a **source-aware system prompt** to enforce web use, compact reasoning, and consistency. Shortened excerpt (see `bot.py` for full text):

```
Du bist FootballPred LLM ... 
- Nutze die Websuche (Tool) aktiv ...
- Konsistenz: ... bivariate Poisson / Skellam ...
- Keine 1:1-Serie; bei Datenlücken Backfill aus Quoten ...
Format: NUR JSON-Objekt mit 'predictions'.
```

### User Template

```
Bundesliga {season}, Spieltag: {matchday}
Gib ausschließlich ein JSON-Objekt mit 'predictions' (Array) zurück.
Felder: matchday, home_team, away_team, predicted_home_goals, predicted_away_goals, reason (<=250 Zeichen, inkl. knapper Quellen).
Spiele (Heim → Auswärts, Quoten H/D/A):
- A vs B | Quoten H/D/A: 1.90 / 3.60 / 3.70
- ...
Hinweise: Nutze Websuche aktiv ... keine Platzhalter, keine 1:1-Serie.
```

### Expected JSON (Responses & Chat)

```json
{
  "predictions": [
    {
      "matchday": 7,
      "home_team": "FC Bayern München",
      "away_team": "RB Leipzig",
      "predicted_home_goals": 2,
      "predicted_away_goals": 1,
      "reason": "Form & xG-Vorsprung + Heimvorteil. [Liga, Teamnews]"
    }
  ]
}
```

A strict **JSON Schema** is enforced in Chat Completions fallback to guarantee structure.


## Tooling & Routing

### Primary Path: Responses API + Web Search

- **Model:** `gpt-5`
- **Tools:** `[{"type":"web_search"}]`
- **Why:** pull **live** lineup/injury/weather data and cite sources.

> **Scopes:** Requires `api.responses.write`. If the API returns `401` with a *Missing scopes* message, the bot automatically falls back to Chat Completions (no web). Provide a key with this scope for best results.

### Fallback Path: Chat Completions (No Web)

- **Model:** `gpt-5-mini`
- **Response Format:** JSON Schema (`response_format={"type":"json_schema", ...}`)
- Used when Responses is not available or unscoped; still applies anti-degeneration and backfill.


## Anti-Degeneration & Backfill

### Draw Guard

- If too many predictions are draws (`home_goals == away_goals`) and `len>=5`, clamp to a **max draw share** (default **45%**).
- Adjust a subset minimally (e.g., 1:1 → 2:1) to avoid a flat 1:1 series.

Config:
```ini
[predictions]
reject_degenerate_draws = true
max_draw_share = 0.45
```

### Odds-Based Backfill

For any game not returned by the LLM (schema miss or mapping failure), the bot produces a **robust score** from implied market probabilities:

```text
implied pH, pD, pA  ← odds (overround removed by normalization)
total_xG ≈ 2.95; diff = 0.85 * (pH - pA) * 2.4
home_xG = (total + diff)/2; away_xG = (total - diff)/2
goals = round(xG with small bias), clipped to [0..4]
if result == 1:1 → nudge toward favorite (2:1 or 1:2)
```

> This avoids unsafe defaults like **1:1** and keeps outcomes plausible.


## Parsing & Mapping (Kicktipp)

- Extract main form (action, CSRF hidden inputs).
- Find goal fields per match by names/classes (`tipp`, `tore`, `heim`, `gast`, `home`, `away`) and **group** by numeric id (`\d{3,}`) in `name`.
- **Team names**:
  - Prefer labeled elements (`.heim`, `.gast`, `.team-home`, `.team-away`).
  - Fallback via text splitting: `A vs B`, `A - B`.
- **Fuzzy mapping** to predictions:
  - Normalize (strip accents, lower, token set) + synonyms (e.g., `Bor. Mönchengladbach` → `Borussia Monchengladbach`).
  - Score = `0.6 * sim(home) + 0.4 * sim(away)`; accept if ≥ 0.86 (configurable in code).
  - If not mapped on first pass, run a **second aggressive pass** (e.g., `"M'gladbach"` fixups).

**Verification:** After POST, the page is reloaded; the agent compares the **input `value` attributes** to the sent scores; if any mismatch, it **retries once**.


## Configuration (`config.ini`)

```ini
[openai]
api_key = sk-xxx
model = gpt-5
fallback_model = gpt-5-mini
temperature = 0.4
use_web_search = true
timeout_seconds = 30
max_retries = 1

[kicktipp]
basis_url = https://www.kicktipp.de/
gruppe = jhb-grosse-jungs
benutzer = YOUR_LOGIN
passwort = YOUR_PASSWORD

[predictions]
out_dir = out/predictions
force_fill_all_open_games = true
reject_degenerate_draws = true
max_draw_share = 0.45
```

ENV overrides exist for all keys (see `bot.py`).


## Running

```bash
export OPENAI_API_KEY=sk-xxx
python3 bot.py
```

- The bot logs in, discovers `tippsaisonId`, iterates matchdays 1..34.
- For each matchday:
  1. Parse page → rows (open games).
  2. Predict with GPT‑5 + web search (or fallback).
  3. Persist audit JSON to `out/predictions/`.
  4. Submit tips → verify → retry (if needed).


## Observability & Logs

Sample messages to look for (German log lines):

- `Login scheint erfolgreich (Logout-Link erkannt).`
- `[Forms] Spieltag X: 9 Spiele gespeichert.` → parser identified matches.
- `[Predictions] Spieltag X: 9 Vorhersagen gespeichert → ...json` → audit written.
- `[Submit] Spieltag X: N Spiele erfolgreich gespeichert.` → portal saved.
- `Kein Feldnamen-Mapping gefunden für: ...` → fuzzy threshold not met; backfill/force-fill covers, but improve synonyms.
- `Responses API fehlgeschlagen: Missing scopes: api.responses.write` → using fallback; provide scoped key for best results.
- `Degeneration erkannt: ... Remis – leichte Diversifizierung angewendet.` → guard triggered.


## Failure Modes & Fixes

| Symptom | Likely Cause | Fix |
|---|---|---|
| `401 Unauthorized` from `/responses` | API key missing `api.responses.write` scope | Create a key with Responses write scope or switch `use_web_search=false` |
| `400 Invalid schema ... type: "array"` | Response format passed to Responses API (not supported) | Our code only uses schema with Chat fallback; do not send `response_format` to Responses API |
| `Keine Paarungen ...` | DOM changes / selectors | Adjust HTML heuristics in `extract_teams_from_container` and `classify_home_away_inputs` |
| Many `Kein Feldnamen-Mapping ...` | Synonyms gap / fuzzy threshold too high | Extend `SYNONYMS`, lower threshold from 0.86 to ~0.80 for second pass |
| Many 1:1 results | Model degeneracy or parse bug | Guard already adjusts; ensure Prompt prohibits uniform draws; verify JSON post-processing |
| Only local JSON saved | Previous versions didn’t POST; now `submit_tips()` posts and verifies | Use the provided `bot.py` |


## Extensibility (Tools & Features)

- **Function Tools** (Responses/Assistants): Add your endpoints and let the model call them:
  - `get_odds(matchId)`, `get_injuries(team)`, `get_weather(stadium, time)`
- **Prompt Caching**: Cache stable prompt blocks (league rules, stadium data).
- **Odds Provider**: Inject live odds per game to improve backfill and calibration.
- **Hard Limits**: Add per‑game cap on scores, or distribution‑based sampling for multiple entries.


## Security & Compliance

- Store credentials in `config.ini` or environment variables; **never** commit secrets.
- Mark outputs as **statistical estimates**; no wagering inducement.
- Respect site ToS; gentle pacing (`sleep_s(1.2)`) implemented.


## Checklist (Production)

- [ ] API key has **Responses write** scope (for web search).
- [ ] `config.ini` present with group & credentials.
- [ ] Synonyms tuned for your league/team naming conventions on Kicktipp.
- [ ] Dry run on 1–2 matchdays; check logs for mapping warnings.
- [ ] Portal reflects all open games filled; verify line-by-line.
- [ ] Monitoring for DOM changes (selectors).


## FAQ

**Q: Why not always use Responses API?**  
A: We do, when scoped. If your key lacks `api.responses.write`, we gracefully fall back to Chat (no web).

**Q: Why are some predictions still missing initially?**  
A: The page may include disabled or duplicated inputs; our verify+retry ensures open inputs are filled; missing mappings are backfilled to avoid gaps.

**Q: Can I force a specific distribution (e.g., cap draws at 30%)?**  
A: Yes—adjust `max_draw_share` and the draw-guard code in `OpenAIPredictor._maybe_guard_draws`.

**Q: Can I plug in my own models or odds?**  
A: Yes—inject your features as tools or precompute and add to the prompt per match (the schema stays identical).
