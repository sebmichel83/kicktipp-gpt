# openai_predictor.py
from __future__ import annotations
import os, json, logging, re, math, unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI
from httpx import HTTPStatusError

log = logging.getLogger(__name__)

# -----------------------------
# Prompt: FootballPred (verkürzt & an Ausgabeformat angepasst)
# -----------------------------
FOOTBALLPRED_SYSTEM = """Du bist FootballPred LLM, ein sachlicher, quellengestützter Prognose-Assistent für Vereinsfußball.
Ziele: für jeden Input ein *konkretes Ergebnis* (Integer-Tore) liefern.
Prinzipien:
- Nutze **Websuche** (Tool) aktiv: Aufstellungen/Verletzungen, Marktquoten, Wetter, Form – belege Kernaussagen mit Quellenangaben (Kurzverweis) in 'reason'.
- Konsistenz: Ergebnisse dürfen NICHT alle gleich sein; setze bivariate Poisson / Skellam oder Monte Carlo basierend auf xG/Teamstärken & HFA.
- Rechne implizite 1X2 aus Quoten (Overround entfernen) als Kalibrier-Referenz.
- Transparente Unsicherheit: Formuliere 'reason' kurz (<=250 Zeichen) mit 1–2 Treibern + 1–2 Quellen.
- **Kein** pauschales 1:1. Wenn Daten dünn: schätze robust aus Quoten + Liga-Torgleichgewicht (keine Einheitswerte).
Formatvorgabe: Gib NUR ein JSON-Objekt mit Schlüssel 'predictions' aus. Keine Einleitung.
"""

FOOTBALLPRED_USER_TMPL = """Bundesliga {season}, Spieltag: {matchday}
Gib ausschließlich ein JSON-Objekt mit 'predictions' (Array) zurück.
Felder pro Spiel: matchday (int), home_team (string), away_team (string),
predicted_home_goals (int), predicted_away_goals (int), reason (<= 250 Zeichen, inkl. knapper Quellenangaben).

Spiele (Heim → Auswärts, Quoten H/D/A):
{lines}

Hinweise:
- Nutze Websuche-Tool aktiv (Lineups, Verletzungen, Quoten-Checks, Wetter); zitiere kurz in 'reason'.
- Ergebnis = wahrscheinlichstes korrekteres Scoreline (Integer).
- Keine doppelten Paarungen, keine Platzhalter, keine "N/A", keine 1:1-Serie.
- Liefere EXAKT das Schema (nur 'predictions').
"""

# JSON-Schema nur für Chat-Fallback (bei Responses-Scopes-Mangel)
PREDICTIONS_JSON_SCHEMA = {
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
                    "properties": {
                        "matchday": {"type": "integer"},
                        "home_team": {"type": "string"},
                        "away_team": {"type": "string"},
                        "predicted_home_goals": {"type": "integer"},
                        "predicted_away_goals": {"type": "integer"},
                        "reason": {"type": "string", "maxLength": 250},
                    },
                    "required": [
                        "matchday","home_team","away_team",
                        "predicted_home_goals","predicted_away_goals","reason"
                    ],
                },
            }
        },
        "required": ["predictions"]
    }
}

@dataclass
class MatchLine:
    matchday: int
    home_team: str
    away_team: str
    odds_h: Optional[float] = None
    odds_d: Optional[float] = None
    odds_a: Optional[float] = None

class OpenAIPredictor:
    def __init__(
        self,
        model: str,
        fallback_model: str = "gpt-5-mini",
        temperature: float = 0.4,
        use_web_search: bool = True,
        timeout_seconds: int = 30,
        max_retries: int = 1,
    ) -> None:
        self.model = model
        self.fallback_model = fallback_model
        self.temperature = temperature
        self.use_web_search = use_web_search
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.client = OpenAI()

    # -----------------------------
    # Öffentlicher Einstiegspunkt
    # -----------------------------
    def predict_matchday(
        self, season: str, matchday: int, lines: List[MatchLine]
    ) -> List[Dict[str, Any]]:
        """
        Gibt eine Liste von Tipobjekten zurück (siehe Schema).
        Enthält Schutz gegen Degeneration (zuviele 1:1) und
        Backfill für fehlende Paarungen via Quoten→Poisson.
        """
        user_prompt = self._format_user_prompt(season, matchday, lines)

        # 1) Bevorzugt: Responses-API + Websuche
        if self.use_web_search:
            try:
                return self._via_responses_with_websearch(user_prompt, matchday, lines)
            except HTTPStatusError as e:
                # 401 meist: fehlende Scopes für Responses API
                log.warning("Responses-API fehlgeschlagen (%s). Fallback auf Chat.", str(e))
            except TypeError as e:
                # ältere SDKs ohne 'tools'/'response_format' in Responses
                log.warning("SDK unterstützt Parameter für Responses nicht (%s). Fallback auf Chat.", str(e))
            except Exception as e:
                log.error("Responses-API unerwartet fehlgeschlagen: %s", e, exc_info=True)

        # 2) Chat-Fallback (ohne Websuche, aber mit JSON-Schema)
        return self._via_chat_json_schema(user_prompt, matchday, lines)

    # -----------------------------
    # Responses + Websuche
    # -----------------------------
    def _via_responses_with_websearch(
        self, user_prompt: str, matchday: int, lines: List[MatchLine]
    ) -> List[Dict[str, Any]]:
        # Wichtig: 'tools=[{"type": "web_search"}]' aktivieren
        # und NUR Textausgabe parsen (da einige SDKs response_format
        # auf Responses nicht unterstützen).
        from openai._base_client import make_request_options  # nur für timeout

        log.info("OpenAI[responses] call: model=%s, md=%s (Websuche aktiv)", self.model, matchday)
        resp = self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": FOOTBALLPRED_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            tools=[{"type": "web_search"}],
            temperature=self.temperature,
            # timeout via request options:
            extra_headers=None,
            extra_query=None,
            extra_body=None,
            **make_request_options(timeout=self.timeout_seconds),
        )

        # Robust JSON-Extraction
        text = getattr(resp, "output_text", None) or _join_output_text(resp)
        data = _extract_json_object(text)
        preds = _validate_and_fix_predictions(data, matchday)

        # Anti-Degeneration + Backfill
        preds = _guard_against_draw_degeneration(preds)
        preds = _ensure_all_games(preds, lines)

        return preds

    # -----------------------------
    # Chat-Fallback (JSON Schema)
    # -----------------------------
    def _via_chat_json_schema(
        self, user_prompt: str, matchday: int, lines: List[MatchLine]
    ) -> List[Dict[str, Any]]:
        log.info("OpenAI[chat] call: model=%s, md=%s (Fallback, ohne Websuche)", self.fallback_model, matchday)

        # Hinweis: Chat Completions versteht response_format mit json_schema
        resp = self.client.chat.completions.create(
            model=self.fallback_model,
            messages=[
                {"role": "system", "content": "Antworte ausschließlich in Deutsch. " +
                                              "Gib NUR ein JSON-Objekt mit dem Schlüssel 'predictions' aus."},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_schema", "json_schema": PREDICTIONS_JSON_SCHEMA},
            temperature=self.temperature,
            timeout=self.timeout_seconds,
        )
        raw = resp.choices[0].message.content
        data = json.loads(raw)
        preds = _validate_and_fix_predictions(data, matchday)

        preds = _guard_against_draw_degeneration(preds)
        preds = _ensure_all_games(preds, lines)

        return preds

    # -----------------------------
    # Helpers
    # -----------------------------
    @staticmethod
    def _format_user_prompt(season: str, matchday: int, lines: List[MatchLine]) -> str:
        def fmt(l: MatchLine) -> str:
            q = " / ".join(
                f"{v:.2f}" if v is not None else "?"
                for v in (l.odds_h, l.odds_d, l.odds_a)
            )
            return f"- {l.home_team} vs {l.away_team} | Quoten H/D/A: {q}"
        joined = "\n".join(fmt(l) for l in lines)
        return FOOTBALLPRED_USER_TMPL.format(season=season, matchday=matchday, lines=joined)

# ============================================================
# JSON & Validierung
# ============================================================

def _join_output_text(resp_obj: Any) -> str:
    """Fügt ggf. segmentierte Outputs (Responses API) zu Text zusammen."""
    try:
        # neuere SDKs: resp.output -> Liste von Blöcken
        chunks = getattr(resp_obj, "output", None) or []
        parts = []
        for ch in chunks:
            if getattr(ch, "type", "") == "output_text":
                parts.append(getattr(ch, "text", ""))
        return "\n".join(parts) if parts else json.dumps(getattr(resp_obj, "dict", resp_obj), ensure_ascii=False)
    except Exception:
        return str(resp_obj)

def _extract_json_object(text: str) -> Dict[str, Any]:
    """Extrahiert das erste JSON-Objekt aus einer evtl. erklärenden Textantwort."""
    if not text:
        raise ValueError("Leere Modellantwort.")
    # harte JSON?
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # in Codefence?
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        return json.loads(m.group(0))
    raise ValueError("Konnte kein JSON in der Antwort finden.")

def _validate_and_fix_predictions(data: Dict[str, Any], matchday: int) -> List[Dict[str, Any]]:
    if not isinstance(data, dict) or "predictions" not in data:
        raise ValueError("Ungültiges JSON: 'predictions' fehlt.")
    preds = data["predictions"]
    if not isinstance(preds, list) or not preds:
        raise ValueError("Leere 'predictions'-Liste.")

    cleaned: List[Dict[str, Any]] = []
    for p in preds:
        if not isinstance(p, dict):
            continue
        md = int(p.get("matchday", matchday))
        ht = str(p.get("home_team", "")).strip()
        at = str(p.get("away_team", "")).strip()
        hg = int(_safe_int(p.get("predicted_home_goals"), 0))
        ag = int(_safe_int(p.get("predicted_away_goals"), 0))
        reason = str(p.get("reason", ""))[:250]
        if not ht or not at:
            continue
        # harte Plausibilisierung
        hg = max(0, min(9, hg))
        ag = max(0, min(9, ag))
        cleaned.append({
            "matchday": md,
            "home_team": ht,
            "away_team": at,
            "predicted_home_goals": hg,
            "predicted_away_goals": ag,
            "reason": reason,
        })
    if not cleaned:
        raise ValueError("Keine gültigen Prediction-Objekte nach Validierung.")
    return cleaned

def _safe_int(x: Any, default: int) -> int:
    try:
        return int(x)
    except Exception:
        return default

# ============================================================
# Degenerationsschutz & Backfill
# ============================================================

def _guard_against_draw_degeneration(preds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    draws = sum(1 for p in preds if p["predicted_home_goals"] == p["predicted_away_goals"])
    if len(preds) >= 5 and draws / len(preds) > float(os.getenv("PRED_MAX_DRAW_SHARE", "0.45")):
        # minimaler Eingriff: drehe 1-2 knappe Remis in 2-1/1-2
        changed = 0
        for p in preds:
            if p["predicted_home_goals"] == p["predicted_away_goals"]:
                if changed < max(1, len(preds)//3):
                    if (p["predicted_home_goals"] <= 1):
                        p["predicted_home_goals"] += 1
                    else:
                        p["predicted_away_goals"] += 1
                    changed += 1
        log.warning("Degeneration erkannt: %d/%d Remis – leichte Diversifizierung angewendet.", draws, len(preds))
    return preds

def _ensure_all_games(
    preds: List[Dict[str, Any]],
    lines: List[MatchLine],
) -> List[Dict[str, Any]]:
    # Baue Map (normierte Namen)
    key = lambda t: _norm_team(t)
    have = {(key(p["home_team"]), key(p["away_team"])): p for p in preds}

    out = list(preds)
    for l in lines:
        k = (key(l.home_team), key(l.away_team))
        if k in have:
            continue
        # Fehlt -> Backfill aus Quoten
        hg, ag = _poisson_from_odds(l.odds_h, l.odds_d, l.odds_a)
        out.append({
            "matchday": l.matchday,
            "home_team": l.home_team,
            "away_team": l.away_team,
            "predicted_home_goals": hg,
            "predicted_away_goals": ag,
            "reason": "Backfill aus Quoten & Liga-Mittel; keine 1:1-Defaults.",
        })
        log.info("Backfill erstellt für fehlende Paarung: %s vs %s -> %d:%d",
                 l.home_team, l.away_team, hg, ag)
    return out

def _poisson_from_odds(oh: Optional[float], od: Optional[float], oa: Optional[float]) -> Tuple[int, int]:
    # Grobe, aber robuste Heuristik: implizite 1X2 -> erwartete Tordiff & Summe -> λ_home/λ_away -> gerundet
    # Bundesliga-Mittel total ~2.95
    total = 2.95
    pH, pD, pA = _implied_probs(oh, od, oa)
    diff = 0.85 * (pH - pA) * 2.4  # kalibriert für plausible Margins
    home_xg = max(0.2, (total + diff) / 2)
    away_xg = max(0.2, (total - diff) / 2)
    # diskrete Punktvorhersage = MAP Simplifikation
    hg = _map_goals(home_xg)
    ag = _map_goals(away_xg)
    if hg == ag == 1:
        # vermeide 1:1 als Default
        if pH >= pA:
            hg = 2
        else:
            ag = 2
    return hg, ag

def _implied_probs(oh, od, oa) -> Tuple[float, float, float]:
    def inv(x): return (1.0/x) if (x and x > 1e-9) else 0.0
    rh, rd, ra = inv(oh), inv(od), inv(oa)
    s = rh + rd + ra
    if s <= 0:
        return 0.45, 0.28, 0.27  # fallback
    return rh/s, rd/s, ra/s

def _map_goals(lmbda: float) -> int:
    # runde sinnvoll (0..4 gebunden)
    v = int(round(lmbda + (0.15 if lmbda >= 1.6 else 0)))
    return max(0, min(4, v))

def _norm_team(s: str) -> str:
    s = s.lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    # Synonyme
    repl = {
        "bor m nchengladbach":"borussia m nchengladbach",
        "monchengladbach":"borussia monchengladbach",
        "borussia monchengladbach":"borussia monchengladbach",
        "bayer 04 leverkusen":"bayer leverkusen",
        "tsg 1899 hoffenheim":"hoffenheim",
        "1899 hoffenheim":"hoffenheim",
        "rasenballsport leipzig":"rb leipzig",
        "1 fc koln":"koln",
        "fc koln":"koln",
        "1 fsv mainz 05":"mainz 05",
        "fsv mainz 05":"mainz 05",
        "hamburger sv":"hsv",
        "sv werder bremen":"werder bremen",
        "vfl wolfsburg":"wolfsburg",
        "vfb stuttgart":"stuttgart",
        "sc freiburg":"freiburg",
        "eintracht frankfurt":"frankfurt",
        "fc bayern munchen":"bayern munchen",
        "fc st pauli":"st pauli",
        "1 fc union berlin":"union berlin",
        "1 fc heidenheim 1846":"heidenheim",
        "1 fc heidenheim":"heidenheim",
    }
    s = repl.get(s, s)
    return s

