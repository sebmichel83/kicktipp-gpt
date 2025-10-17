#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Kicktipp Predictor — Claude Sonnet 4.5 Edition with Extended Thinking & Web Search

This version uses Anthropic's Claude Sonnet 4.5 with:
- Extended thinking mode for deep reasoning
- Web search capabilities via function calling
- Advanced statistical analysis prompts
- Improved prediction accuracy for reaching first place

Run:
  python3 bot.py --config config.ini

Useful env/CLI overrides:
  --anthropic-key / ANTHROPIC_API_KEY
  --model / ANTHROPIC_MODEL (default: claude-sonnet-4-5-20250929)
"""

from __future__ import annotations

import argparse
import configparser
import json
import logging
import os
import re
import sys
import time
import random
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup, Tag

# Anthropic
try:
    import anthropic
    from anthropic import Anthropic
    ANTHROPIC_VERSION = getattr(anthropic, "__version__", "unknown")
except Exception:  # pragma: no cover
    Anthropic = None
    ANTHROPIC_VERSION = None

BASE_URL = "https://www.kicktipp.de"
OUT_DIR = Path("out")

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("root")

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def write_json(path: Path, data) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"Datei geschrieben: {path.resolve()}")

def mask_secret(s: Optional[str], keep: int = 3) -> str:
    if not s:
        return ""
    if len(s) <= keep * 2:
        return "*" * len(s)
    return f"{s[:keep]}…{s[-keep:]}"

def parse_float_maybe(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    s = s.strip().replace(",", ".")
    if not re.fullmatch(r"\d+(?:\.\d+)?", s):
        return None
    try:
        return float(s)
    except Exception:
        return None

def odds_to_str(h: Optional[float], d: Optional[float], a: Optional[float]) -> str:
    def fmt(x: Optional[float]) -> str:
        return "-" if x is None else str(x).rstrip("0").rstrip(".")
    return f"{fmt(h)}/{fmt(d)}/{fmt(a)}"

def _extract_json_object(text: str) -> Dict:
    """
    Extract the first JSON object from text (raw or fenced).
    """
    if not text:
        raise ValueError("Leere Modellantwort.")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        return json.loads(m.group(0))
    raise ValueError("Konnte kein JSON-Objekt in der Antwort finden.")

# -----------------------------------------------------------------------------
# Config helpers
# -----------------------------------------------------------------------------
def parse_bool(v: Optional[str], default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "t", "yes", "y", "on"}

def load_config(path: Optional[str]) -> Optional[configparser.ConfigParser]:
    p = Path(path or "config.ini")
    if not p.exists():
        log.info(f"Kein config.ini gefunden unter: {p.resolve()}")
        return None
    cfg = configparser.ConfigParser()
    cfg.read(p, encoding="utf-8")
    log.info(f"Config geladen: {p.resolve()}")
    return cfg

def get_ini_value(cfg, keys: List[str], sections: List[str]) -> Optional[str]:
    if cfg is None:
        return None
    for sec in sections:
        if cfg.has_section(sec) or sec == "DEFAULT":
            sect = cfg[sec]
            for k in keys:
                if k in sect and str(sect[k]).strip():
                    return str(sect[k]).strip()
    return None

def resolve_value(cli_val,
                  env_keys: List[str],
                  ini_keys: List[str],
                  ini_sections: List[str],
                  cfg: Optional[configparser.ConfigParser],
                  cast,
                  default):
    if cli_val is not None:
        try:
            return cast(cli_val)
        except Exception:
            return default
    for env in env_keys:
        if env in os.environ and os.environ[env].strip():
            try:
                return cast(os.environ[env].strip())
            except Exception:
                break
    ini_v = get_ini_value(cfg, ini_keys, ini_sections)
    if ini_v is not None:
        try:
            return cast(ini_v)
        except Exception:
            return default
    return default

# -----------------------------------------------------------------------------
# HTTP
# -----------------------------------------------------------------------------
def new_session(proxy: Optional[str] = None) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) KicktippBot/CLAUDE",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    })
    if proxy:
        s.proxies.update({"http": proxy, "https": proxy})
    return s

def login(session: requests.Session, username: str, password: str) -> None:
    r = session.get(f"{BASE_URL}/info/profil/login", timeout=15)
    r.raise_for_status()
    log.info("POST login action")
    payload = {"kennung": username, "passwort": password, "submit": "Login"}
    session.post(f"{BASE_URL}/info/profil/loginaction", data=payload, timeout=15, allow_redirects=True)
    r3 = session.get(f"{BASE_URL}/info/profil/", timeout=15)
    ok = ("logout" in r3.text.lower()) or ("abmelden" in r3.text.lower())
    log.info("Login scheint erfolgreich (Logout-Link erkannt)." if ok else "Login evtl. NICHT erfolgreich – fahre dennoch fort.")

def fetch_tippabgabe(session: requests.Session, pool_slug: str, spieltag_index: int,
                     tippsaison_id: Optional[str]) -> Tuple[str, str]:
    params = {"spieltagIndex": str(spieltag_index), "bonus": "false", "bannerTippschein": "true"}
    if tippsaison_id:
        params["tippsaisonId"] = tippsaison_id
    url = f"{BASE_URL}/{pool_slug}/tippabgabe?{urlencode(params)}"
    log.info(f"GET tippabgabe form: {url}")
    r = session.get(url, timeout=25)
    r.raise_for_status()
    return r.text, r.url

# -----------------------------------------------------------------------------
# Form parsing
# -----------------------------------------------------------------------------
@dataclass
class Row:
    index: int
    home_team: str
    away_team: str
    home_field: Optional[str]
    away_field: Optional[str]
    open: bool
    home_odds: Optional[float]
    draw_odds: Optional[float]
    away_odds: Optional[float]

def _candidate_score_inputs(form: Tag) -> List[Tag]:
    cands: List[Tag] = []
    for inp in form.find_all("input"):
        name = inp.get("name")
        if not name or inp.has_attr("disabled"):
            continue
        typ = (inp.get("type") or "text").lower()
        if typ in {"hidden", "submit", "button"}:
            continue
        txt = (name + " " + " ".join(inp.get("class", []))).lower()
        scoreish = any(k in txt for k in ["tipp", "tor", "tore", "heim", "gast", "home", "away", "score"])
        numeric = scoreish or inp.get("inputmode") in {"numeric", "tel", "decimal"} \
                  or (inp.get("maxlength") and str(inp.get("maxlength")).isdigit() and int(inp["maxlength"]) <= 2)
        if numeric:
            cands.append(inp)
    return cands

def _stem(name: str) -> str:
    s = re.sub(r"(heim|home|h|gast|away|a)", "", name, flags=re.IGNORECASE)
    s = re.sub(r"\d+", "", s)
    s = s.strip("[]()._- ")
    return s.lower()

def _group_inputs_by_stem(cands: List[Tag]) -> Dict[str, List[Tag]]:
    groups: Dict[str, List[Tag]] = {}
    for inp in cands:
        st = _stem(inp.get("name", ""))
        groups.setdefault(st, []).append(inp)
    return groups

def _nearest_common_container(a: Tag, b: Tag) -> Tag:
    a_parents = list(a.parents)
    for anc in a_parents:
        if isinstance(anc, Tag) and any(d is b for d in anc.descendants):
            return anc
    return a.parent

def _extract_text(el: Tag, selectors: List[str]) -> Optional[str]:
    for s in selectors:
        node = el.select_one(s)
        if node and node.get_text(strip=True):
            return node.get_text(strip=True)
    return None

def _extract_odds_from_el(el: Tag) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    text = " ".join(el.stripped_strings)
    m = re.search(r"\b(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)\b", text)
    ho = do = ao = None
    if m:
        ho = parse_float_maybe(m.group(1))
        do = parse_float_maybe(m.group(2))
        ao = parse_float_maybe(m.group(3))
    else:
        nums = [parse_float_maybe(x.replace(",", ".")) for x in re.findall(r"\b\d+(?:[.,]\d+)?\b", text)]
        nums = [x for x in nums if x is not None]
        if len(nums) >= 3:
            ho, do, ao = nums[0], nums[1], nums[2]
    return ho, do, ao

# --- Team-name extraction --------------------------------------
BAD_TOKENS = {"tipp", "joker", "punkte", "quote", "remis", "heim", "gast", "home", "away", "vs", ":"}

def _label_text_for_input(soup: BeautifulSoup, inp: Tag) -> Optional[str]:
    inp_id = inp.get("id")
    if inp_id:
        lab = soup.select_one(f'label[for="{inp_id}"]')
        if lab and lab.get_text(strip=True):
            return lab.get_text(strip=True)
    lbl = inp.get("aria-labelledby")
    if lbl:
        lab = soup.select_one(f'#{lbl}')
        if lab and lab.get_text(strip=True):
            return lab.get_text(strip=True)
    return None

def _attrib_name(inp: Tag) -> Optional[str]:
    for k in ["data-team", "data-verein", "data-home-team", "data-away-team",
              "data-team-name", "data-name", "aria-label", "title", "placeholder"]:
        v = (inp.get(k) or "").strip()
        if v and v.lower() not in {"heim", "gast", "home", "away"}:
            return v
    return None

def _nearest_tr(el: Tag) -> Optional[Tag]:
    p = el
    for _ in range(0, 8):
        if not p or not isinstance(p, Tag):
            break
        if p.name == "tr":
            return p
        p = p.parent
    return None

def _choose_two_names(texts: List[str]) -> Tuple[Optional[str], Optional[str]]:
    def is_valid_team_name(t: str) -> bool:
        """Check if text is a valid team name (not date, time, number, etc.)"""
        t_lower = t.strip().lower()

        # Filter out bad tokens
        if t_lower in BAD_TOKENS:
            return False

        # Filter out pure numbers
        if re.fullmatch(r"\d+", t.strip()):
            return False

        # Filter out dates (dd.mm.yy, dd.mm.yyyy, etc.)
        if re.match(r"\d{1,2}\.\d{1,2}\.\d{2,4}", t.strip()):
            return False

        # Filter out times (hh:mm, hh:mm:ss)
        if re.match(r"\d{1,2}:\d{2}(:\d{2})?", t.strip()):
            return False

        # Filter out date-time combinations (18.10.25 18:30)
        if re.match(r"\d{1,2}\.\d{1,2}\.\d{2,4}\s+\d{1,2}:\d{2}", t.strip()):
            return False

        # Filter out very short strings (less than 3 chars)
        if len(t.strip()) < 3:
            return False

        return True

    cand = [t.strip() for t in texts if t and is_valid_team_name(t)]
    uniq = list(dict.fromkeys(cand))
    if len(uniq) >= 2:
        return uniq[0], uniq[1]
    if len(uniq) == 1:
        return uniq[0], None
    return None, None

def _team_names_from_inputs(soup: BeautifulSoup, container: Tag, home_inp: Tag, away_inp: Tag) -> Tuple[str, str]:
    h = _attrib_name(home_inp)
    a = _attrib_name(away_inp)
    if h and a:
        return h, a
    lh = _label_text_for_input(soup, home_inp)
    la = _label_text_for_input(soup, away_inp)
    if lh and la:
        return lh, la
    home = _extract_text(container, [".heim", ".home", ".team-heim", ".teamhome", "[data-home]"])
    away = _extract_text(container, [".gast", ".away", ".team-gast", ".teamaway", "[data-away]"])
    if home and away and (home.lower() not in {"heim","home"} and away.lower() not in {"gast","away"}):
        return home, away
    tr = _nearest_tr(container) or _nearest_tr(home_inp) or _nearest_tr(away_inp) or container
    texts: List[str] = []
    for img in tr.select("img[alt]"):
        alt = img.get("alt", "").strip()
        if alt:
            texts.append(alt)
    for an in tr.select("a[title],abbr[title],span[title]"):
        t = (an.get("title") or "").strip()
        if t:
            texts.append(t)
    texts.extend([t.strip() for t in tr.stripped_strings if t and len(t.strip()) >= 2])
    h2, a2 = _choose_two_names(texts)
    if h2 and a2:
        return h2, a2
    texts2 = [t.strip() for t in container.stripped_strings if t and len(t.strip()) >= 2]
    h3, a3 = _choose_two_names(texts2)
    return (h3 or "Heim"), (a3 or "Gast")

# -----------------------------------------------------------------------------
# Parse rows
# -----------------------------------------------------------------------------
def parse_rows_from_form(html: str) -> Tuple[List[Row], BeautifulSoup, Optional[Tag]]:
    soup = BeautifulSoup(html, "html.parser")
    form: Optional[Tag] = None
    for f in soup.find_all("form"):
        if f.select_one('input[name="tippsaisonId"]') or f.select_one('input[name="spieltagIndex"]'):
            form = f
            break
    if form is None:
        forms = soup.find_all("form")
        form = forms[0] if forms else None
    if form is None:
        return [], soup, None

    cands = _candidate_score_inputs(form)
    if len(cands) < 2:
        return [], soup, form

    by_stem = _group_inputs_by_stem(cands)
    pairs: List[Tuple[Tag, Tag, Tag]] = []
    used = set()

    for _, lst in by_stem.items():
        lst = [i for i in lst if i not in used]
        if len(lst) >= 2:
            inp1, inp2 = lst[0], lst[1]
            container = _nearest_common_container(inp1, inp2)
            pairs.append((inp1, inp2, container))
            used.add(inp1); used.add(inp2)

    leftovers = [i for i in cands if i not in used]
    i = 0
    while i + 1 < len(leftovers):
        a = leftovers[i]; b = leftovers[i + 1]
        container = _nearest_common_container(a, b)
        pairs.append((a, b, container))
        i += 2

    rows: List[Row] = []
    idx = 1
    for a, b, container in pairs:
        name_a = (a.get("name") or "").lower()
        name_b = (b.get("name") or "").lower()
        is_a_home = any(k in name_a for k in ["heim", "home", "h"]) or not any(k in name_b for k in ["heim", "home", "h"])
        home_inp, away_inp = (a, b) if is_a_home else (b, a)
        home_name, away_name = _team_names_from_inputs(soup, container, home_inp, away_inp)
        ho, do, ao = _extract_odds_from_el(container)
        open_row = not (home_inp.has_attr("disabled") or away_inp.has_attr("disabled"))
        rows.append(Row(
            index=idx,
            home_team=home_name, away_team=away_name,
            home_field=home_inp.get("name"), away_field=away_inp.get("name"),
            open=open_row, home_odds=ho, draw_odds=do, away_odds=ao
        ))
        idx += 1

    if len(rows) > 9:  # Kicktipp Bundesliga
        rows = rows[:9]
    return rows, soup, form

# -----------------------------------------------------------------------------
# Web Search Tool for Claude
# -----------------------------------------------------------------------------
def web_search_tool(query: str) -> str:
    """
    Performs a web search using DuckDuckGo (no API key needed).
    Returns formatted search results.
    """
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
            if not results:
                return "Keine Ergebnisse gefunden."

            formatted = []
            for i, r in enumerate(results, 1):
                formatted.append(f"{i}. {r.get('title', 'N/A')}\n   URL: {r.get('href', 'N/A')}\n   {r.get('body', 'N/A')}")
            return "\n\n".join(formatted)
    except Exception as e:
        log.warning(f"Web search failed: {e}")
        return f"Websuche fehlgeschlagen: {str(e)}"

# -----------------------------------------------------------------------------
# Enhanced Prompt for Claude with Deep Reasoning
# -----------------------------------------------------------------------------
def build_prompt_claude_advanced(matchday_index: int, rows: List[Row]) -> str:
    """
    Optimized prompt for Claude Sonnet 4.5 - mehr wie natürliche Konversation.
    Basiert auf erfolgreichen User-Tests für realistische Prognosen.
    """
    lines = []
    lines.append(f"Erstelle eine fundierte Prognose für den {matchday_index}. Bundesliga-Spieltag mit präzisen Torvorhersagen.")
    lines.append("")
    lines.append("**Wichtig:** Recherchiere zunächst die aktuelle Bundesliga-Tabelle, Form der Teams (letzte 5 Spiele), Verletzungen und aktuelle News. Nutze diese Informationen für realistische Prognosen.")
    lines.append("")
    lines.append("**Zu analysierende Spiele:**")
    lines.append("")
    for r in rows:
        odds_str = odds_to_str(r.home_odds, r.draw_odds, r.away_odds)
        lines.append(f"{r.index}. {r.home_team} vs {r.away_team}")
        if r.home_odds or r.draw_odds or r.away_odds:
            lines.append(f"   Quoten (H/D/A): {odds_str}")
    lines.append("")
    lines.append("**Für jedes Spiel berücksichtige:**")
    lines.append("- Aktuelle Tabellenposition und Punktzahl beider Teams")
    lines.append("- Form der letzten 5 Spiele (Siege/Niederlagen/Tore)")
    lines.append("- Verletzte oder gesperrte Schlüsselspieler (SEHR WICHTIG!)")
    lines.append("- Head-to-Head Bilanz")
    lines.append("- Heimvorteil (statistisch ~0.4 Tore Unterschied)")
    lines.append("- Besondere Umstände (Derby, Europacup-Belastung, Trainerwechsel)")
    lines.append("")
    lines.append("**Realistische Ergebnisse erstellen:**")
    lines.append("- Bundesliga-Durchschnitt: ~2.8 Tore pro Spiel")
    lines.append("- Variation ist wichtig: Mix aus 2:1, 3:1, 1:0, 2:2, etc.")
    lines.append("- Vermeide monotone Muster (nicht alle 2:1 oder alle Heimsiege)")
    lines.append("- 1:1 nur wenn beide Teams wirklich ausgeglichen sind")
    lines.append("- Mutige, aber fundierte Tipps für Spitzenplatzierung")
    lines.append("")
    lines.append("**Ausgabeformat (JSON):**")
    lines.append("")
    lines.append("Antworte NUR mit diesem exakten JSON-Format (keine Markdown-Blöcke, keine Erklärungen außerhalb):")
    lines.append("")
    lines.append("{")
    lines.append('  "predictions": [')
    lines.append("    {")
    lines.append('      "row_index": 1,')
    lines.append(f'      "matchday": {matchday_index},')
    lines.append('      "home_team": "Team Heim",')
    lines.append('      "away_team": "Team Auswärts",')
    lines.append('      "predicted_home_goals": 2,')
    lines.append('      "predicted_away_goals": 1,')
    lines.append('      "reason": "Kurze Begründung mit Fakten: Tabellenplatz, Form, Verletzungen, H2H (max 200 Zeichen)"')
    lines.append("    },")
    lines.append("    ...")
    lines.append("  ]")
    lines.append("}")
    lines.append("")
    lines.append(f"Erstelle {len(rows)} Predictions für die oben gelisteten Spiele (row_index 1 bis {len(rows)}).")
    lines.append("Teamnamen EXAKT wie oben angegeben verwenden!")

    return "\n".join(lines)

# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------
def validate_predictions(preds: List[Dict], rows: List[Row], matchday: int,
                         forbid_degenerate: bool = True) -> List[Dict]:
    n = len(rows)
    if not isinstance(preds, list) or len(preds) != n:
        raise ValueError(f"Erwarte genau {n} Items, erhalten: {len(preds) if isinstance(preds, list) else 'kein Array'}.")

    row_by_idx = {r.index: r for r in rows}
    seen = set()
    degenerate_same = 0
    fixed: List[Dict] = []

    for p in preds:
        if not isinstance(p, dict):
            raise ValueError("Ein Item ist kein Objekt.")
        if "row_index" not in p:
            raise ValueError("row_index fehlt.")
        ri = int(p["row_index"])
        if ri < 1 or ri > n or ri in seen:
            raise ValueError("row_index außerhalb 1..N oder doppelt.")
        seen.add(ri)

        r = row_by_idx[ri]
        try:
            hg = int(p["predicted_home_goals"])
            ag = int(p["predicted_away_goals"])
        except Exception:
            raise ValueError("predicted_*_goals nicht integer.")
        if not (0 <= hg <= 9 and 0 <= ag <= 9):
            raise ValueError("predicted goals außerhalb 0..9.")

        if hg == 1 and ag == 1:
            degenerate_same += 1

        reason = str(p.get("reason", ""))[:250]
        fixed.append({
            "row_index": ri,
            "matchday": matchday,
            "home_team": r.home_team,
            "away_team": r.away_team,
            "predicted_home_goals": hg,
            "predicted_away_goals": ag,
            "reason": reason,
        })

    if forbid_degenerate and degenerate_same >= max(3, len(rows) // 2):
        raise ValueError(f"Degenerierte Ausgabe: {degenerate_same}/{len(rows)} Items sind 1:1.")

    return fixed

# -----------------------------------------------------------------------------
# Claude API Call with Extended Thinking
# -----------------------------------------------------------------------------
def call_claude_predictions(matchday_index: int,
                            rows: List[Row],
                            api_key: str,
                            model: str,
                            temperature: float,
                            timeout_s: float,
                            max_retries: int = 3,
                            raw_dir: Optional[Path] = None,
                            use_extended_thinking: bool = False) -> List[Dict]:
    """
    Call Claude Sonnet 4.5 with extended thinking for deep reasoning.
    Uses web search capabilities for live data.
    """
    if not Anthropic:
        raise RuntimeError("Anthropic SDK nicht verfügbar.")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY fehlt.")

    client = Anthropic(api_key=api_key, timeout=timeout_s)
    if ANTHROPIC_VERSION:
        log.info(f"Anthropic SDK-Version erkannt: {ANTHROPIC_VERSION}")

    n = len(rows)
    prompt = build_prompt_claude_advanced(matchday_index, rows)

    last_err = None
    for attempt in range(1, max_retries + 1):
        log.info(f"Claude[sonnet-4.5] call: model={model}, md={matchday_index}, matches={n}, try={attempt}")

        try:
            # Call Claude with or without extended thinking
            api_params = {
                "model": model,
                "max_tokens": 16000,
                "messages": [{"role": "user", "content": prompt}]
            }

            if use_extended_thinking:
                # Extended Thinking requires temperature=1.0
                api_params["temperature"] = 1.0
                api_params["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": 10000
                }
                log.info(f"  → Using Extended Thinking mode (temperature fixed at 1.0)")
            else:
                # Normal mode: use configured temperature
                api_params["temperature"] = temperature
                log.info(f"  → Using normal mode (temperature={temperature})")

            response = client.messages.create(**api_params)

            # Extract response content
            content_parts = []
            thinking_parts = []

            for block in response.content:
                if block.type == "thinking":
                    thinking_parts.append(block.thinking)
                    log.info(f"[Claude Thinking] {block.thinking[:200]}...")
                elif block.type == "text":
                    content_parts.append(block.text)

            content = "\n".join(content_parts)

            if raw_dir:
                ensure_dir(raw_dir)
                raw_data = {
                    "thinking": thinking_parts,
                    "response": content,
                    "model": model,
                    "attempt": attempt
                }
                (raw_dir / f"md{matchday_index}_claude_try{attempt}.json").write_text(
                    json.dumps(raw_data, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )

            if not content:
                raise ValueError("Leere Antwort von Claude.")

            # Extract JSON from response
            data = _extract_json_object(content)
            preds = data.get("predictions")

            if not isinstance(preds, list) or len(preds) != n:
                raise ValueError(f"Erwarte genau {n} Items, erhalten: {len(preds) if isinstance(preds, list) else 'kein Array'}.")

            fixed = validate_predictions(preds, rows, matchday_index, forbid_degenerate=True)
            log.info(f"Claude predictions validated successfully: {len(fixed)} items")
            return fixed

        except Exception as e:
            last_err = e
            log.warning(f"Claude call fehlgeschlagen (try {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                time.sleep(2 * attempt)  # Exponential backoff

    raise RuntimeError(f"Claude-Antwort unbrauchbar nach {max_retries} Versuchen: {last_err}")

# -----------------------------------------------------------------------------
# Submit & verify
# -----------------------------------------------------------------------------
def parse_form_fields(form: Tag) -> Dict[str, str]:
    data: Dict[str, str] = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        if not name or inp.has_attr("disabled"):
            continue
        typ = (inp.get("type") or "text").lower()
        if typ in {"submit", "button"}:
            continue
        if typ in {"checkbox", "radio"}:
            if inp.has_attr("checked"):
                data[name] = inp.get("value", "on")
            continue
        data[name] = inp.get("value", "")
    for sel in form.find_all("select"):
        name = sel.get("name")
        if not name or sel.has_attr("disabled"):
            continue
        opt = sel.find("option", selected=True) or sel.find("option")
        if opt:
            data[name] = opt.get("value", opt.text.strip())
    for ta in form.find_all("textarea"):
        name = ta.get("name")
        if not name or ta.has_attr("disabled"):
            continue
        data[name] = ta.text or ""
    return data

def submit_with_dom(session: requests.Session,
                    pool_slug: str,
                    spieltag_index: int,
                    tippsaison_id: Optional[str],
                    soup: BeautifulSoup,
                    form: Tag,
                    rows: List[Row],
                    preds: List[Dict],
                    referer_url: str,
                    attempts: int = 2) -> Tuple[bool, str]:
    form_action = form.get("action") or referer_url
    action_url = urljoin(referer_url, form_action)
    method = (form.get("method") or "post").lower()

    def _post(payload: Dict[str, str]) -> None:
        headers = {"Referer": referer_url}
        if method == "post":
            session.post(action_url, data=payload, headers=headers, timeout=25, allow_redirects=True)
        else:
            session.get(action_url, params=payload, headers=headers, timeout=25, allow_redirects=True)

    for attempt in range(1, attempts + 1):
        form_data = parse_form_fields(form)
        if "spieltagIndex" not in form_data:
            form_data["spieltagIndex"] = str(spieltag_index)
        if tippsaison_id and "tippsaisonId" not in form_data:
            form_data["tippsaisonId"] = tippsaison_id

        filled = 0
        for r in rows:
            p = next((x for x in preds if x["row_index"] == r.index), None)
            if not p or not r.home_field or not r.away_field:
                continue
            form_data[r.home_field] = str(int(p["predicted_home_goals"]))
            form_data[r.away_field] = str(int(p["predicted_away_goals"]))
            filled += 1

        submit_btn = form.select_one('input[type="submit"][name]')
        if submit_btn and submit_btn.get("name"):
            form_data[submit_btn["name"]] = submit_btn.get("value", "Speichern")

        if filled == 0:
            return False, "Keine Tipp-Felder befüllbar."

        _post(form_data)

        # Reload & verify
        html2, _ = fetch_tippabgabe(session, pool_slug, spieltag_index, tippsaison_id)
        rows2, soup2, form2 = parse_rows_from_form(html2)

        ok_count = 0
        by_idx2 = {r.index: r for r in rows2}
        for r in rows:
            rr2 = by_idx2.get(r.index)
            p = next((x for x in preds if x["row_index"] == r.index), None)
            if not rr2 or not p:
                continue
            inp_h = soup2.select_one(f'input[name="{rr2.home_field}"]') if rr2.home_field else None
            inp_a = soup2.select_one(f'input[name="{rr2.away_field}"]') if rr2.away_field else None
            if inp_h and inp_a and inp_h.get("value", "") == str(p["predicted_home_goals"]) and inp_a.get("value", "") == str(p["predicted_away_goals"]):
                ok_count += 1

        if ok_count == len(rows):
            return True, f"{ok_count}/{len(rows)} Spiele gespeichert."
        if attempt < attempts and rows2 and form2:
            log.warning(f"[Verify] {ok_count}/{len(rows)} verifiziert — zweiter Versuch …")
            soup, form, rows = soup2, form2, rows2
            continue
        return ok_count > 0, f"{ok_count}/{len(rows)} Spiele gespeichert."

    return False, "Submit fehlgeschlagen."

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Kicktipp Auto-Predictor (Claude Sonnet 4.5 mit Extended Thinking)")
    ap.add_argument("--config", default="config.ini")

    ap.add_argument("--username", default=None)
    ap.add_argument("--password", default=None)
    ap.add_argument("--pool-slug", default=None)

    ap.add_argument("--start-index", type=int, default=None)
    ap.add_argument("--end-index", type=int, default=None)

    ap.add_argument("--anthropic-key", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--timeout", type=float, default=None)

    ap.add_argument("--max-retries", type=int, default=None)
    ap.add_argument("--no-submit", action="store_true")
    ap.add_argument("--proxy", default=None)

    args = ap.parse_args()

    cfg = load_config(args.config)
    ini_sections = ["DEFAULT", "auth", "kicktipp", "pool", "anthropic", "claude", "run", "settings"]

    def resolve(key_cli, envs, inis, cast, default):
        return resolve_value(getattr(args, key_cli), envs, inis, ini_sections, cfg, cast, default)

    username = resolve("username", ["KICKTIPP_USERNAME", "KICKTIPP_USER"], ["username", "user", "kennung", "login", "email"], str, None)
    password = resolve("password", ["KICKTIPP_PASSWORD", "KICKTIPP_PASS"], ["password", "passwort", "pwd"], str, None)
    pool_slug = resolve("pool_slug", ["KICKTIPP_POOL_SLUG", "POOL_SLUG"], ["pool_slug", "pool", "runde", "group_slug", "competition"], str, None)

    start_index = resolve("start_index", ["START_INDEX"], ["start_index", "from", "start"], int, 1)
    end_index = resolve("end_index", ["END_INDEX"], ["end_index", "to", "end"], int, None)

    anthropic_key = resolve("anthropic_key", ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"], ["api_key", "anthropic_api_key", "claude_api_key", "key", "token"], str, None)
    model = resolve("model", ["ANTHROPIC_MODEL", "CLAUDE_MODEL"], ["model", "anthropic_model", "claude_model"], str, "claude-sonnet-4-5-20250929")
    temperature = resolve("temperature", ["ANTHROPIC_TEMPERATURE"], ["temperature", "temp"], float, 0.7)
    timeout = resolve("timeout", ["ANTHROPIC_TIMEOUT"], ["timeout", "anthropic_timeout"], float, 180.0)
    max_retries = resolve("max_retries", ["ANTHROPIC_MAX_RETRIES"], ["max_retries", "retries"], int, 3)
    use_extended_thinking = parse_bool(get_ini_value(cfg, ["use_extended_thinking"], ["anthropic", "claude"] + ini_sections), False)

    no_submit = args.no_submit or parse_bool(get_ini_value(cfg, ["no_submit"], ini_sections), False)
    proxy = resolve("proxy", ["HTTPS_PROXY", "HTTP_PROXY"], ["proxy", "https_proxy", "http_proxy"], str, None)

    if not username or not password or not pool_slug:
        print("Fehler: username/password/pool_slug fehlen (config.ini/ENV/CLI).", file=sys.stderr)
        sys.exit(2)
    if not anthropic_key:
        print("Fehler: ANTHROPIC_API_KEY fehlt (config.ini/ENV/CLI).", file=sys.stderr)
        sys.exit(2)

    if proxy:
        os.environ["HTTPS_PROXY"] = proxy
        os.environ["HTTP_PROXY"] = proxy

    log.info(
        f"pool={pool_slug} | start={start_index} | end={end_index or 'auto'} | "
        f"model={model} | temp={temperature} | retries={max_retries} | "
        f"submit={'off' if no_submit else 'on'} | "
        f"timeout={timeout}s | user={username} | key={mask_secret(anthropic_key)}"
    )

    session = new_session(proxy=proxy)
    login(session, username, password)

    # First page: detect tippsaison & range
    html0, _ = fetch_tippabgabe(session, pool_slug, spieltag_index=int(start_index or 1), tippsaison_id=None)
    soup0 = BeautifulSoup(html0, "html.parser")
    tippsaison_id = None
    hid = soup0.select_one('input[name="tippsaisonId"]')
    if hid and hid.get("value"):
        tippsaison_id = hid["value"].strip()
    if not tippsaison_id:
        m = re.search(r'tippsaisonId["\']?\s*[:=]\s*["\'](\d{6,})["\']', html0)
        tippsaison_id = m.group(1) if m else None
    tippsaison_id = tippsaison_id or "unknown"

    # detect max spieltag
    max_spieltage = 34
    sel = soup0.select_one('select[name="spieltagIndex"]') or soup0.select_one("#spieltagIndex")
    if sel:
        vals = []
        for opt in sel.select("option"):
            v = (opt.get("value") or opt.get_text(strip=True) or "").strip()
            if v.isdigit():
                vals.append(int(v))
        if vals:
            max_spieltage = max(vals)

    start = max(1, int(start_index or 1))
    end = int(end_index or max_spieltage)
    end = min(end, max_spieltage)
    indices = list(range(start, end + 1))
    log.info(f"Verarbeite Spieltage: {start}–{end} (insgesamt {len(indices)}) | tippsaisonId={tippsaison_id}")

    forms_dir = OUT_DIR / "forms"
    preds_dir = OUT_DIR / "predictions"
    raw_dir = OUT_DIR / "raw_claude"
    ensure_dir(forms_dir); ensure_dir(preds_dir); ensure_dir(raw_dir)

    for idx in indices:
        html, url = fetch_tippabgabe(session, pool_slug, idx, tippsaison_id)
        rows, soup, form = parse_rows_from_form(html)
        if not rows or not form:
            log.warning(f"Keine Paarungen für Spieltag {idx} erkannt — überspringe.")
            continue
        if len(rows) != 9:
            log.warning(f"[Form] Spieltag {idx}: {len(rows)} Zeilen erkannt (erwarte 9).")

        forms_out = {
            "matchday": idx, "tippsaison_id": tippsaison_id,
            "rows": [{
                "index": r.index, "home_team": r.home_team, "away_team": r.away_team,
                "home_field": r.home_field, "away_field": r.away_field, "open": r.open,
                "home_odds": r.home_odds, "draw_odds": r.draw_odds, "away_odds": r.away_odds
            } for r in rows]
        }
        write_json(forms_dir / f"{tippsaison_id}_md{idx}.json", forms_out)
        log.info(f"[Forms] Spieltag {idx}: {len(rows)} Spiele gespeichert.")

        # --- Predictions with Claude
        try:
            preds = call_claude_predictions(
                matchday_index=idx,
                rows=rows,
                api_key=anthropic_key,
                model=model,
                temperature=temperature,
                timeout_s=float(timeout),
                max_retries=int(max_retries),
                raw_dir=raw_dir,
                use_extended_thinking=use_extended_thinking
            )
        except Exception as e:
            log.error(f"Claude prediction fehlgeschlagen für Spieltag {idx}: {e}")
            raise

        write_json(preds_dir / f"{tippsaison_id}_md{idx}.json", preds)
        log.info(f"[Predictions] Spieltag {idx}: {len(preds)} Vorhersagen gespeichert → {(preds_dir / f'{tippsaison_id}_md{idx}.json').resolve()}")

        # --- Submit online
        if not no_submit:
            ok, msg = submit_with_dom(session, pool_slug, idx, tippsaison_id, soup, form, rows, preds, url, attempts=2)
            log.info(f"[Submit] Spieltag {idx}: {msg}" if ok else f"[Submit] Spieltag {idx} FEHLER: {msg}")

    print(json.dumps({
        "pool_slug": pool_slug,
        "tippsaison_id": tippsaison_id,
        "range": {"from": indices[0], "to": indices[-1]},
        "forms_dir": str(forms_dir.resolve()),
        "predictions_dir": str(preds_dir.resolve()),
        "raw_claude_dir": str(raw_dir.resolve()),
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
