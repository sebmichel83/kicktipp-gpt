#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Kicktipp Predictor — STRICT mode (Responses API + optional Websuche)

This build fixes:
- OpenAI Chat JSON schema 400s: item schema has additionalProperties=false (strict mode requirement)
- Avoid useless web_search when team names are placeholders ("Heim/Gast"): skip to Chat fallback
- Much stronger team-name extraction around inputs (attributes, <label>, nearest <tr>, logos)
- Responses API still without response_format (unsupported in your SDK)
- Robust logging and raw dumps for auditability

Run:
  python3 bot.py --config config.ini
"""

from __future__ import annotations

import argparse
import configparser
import json
import logging
import os
import re
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup, Tag

# OpenAI
try:
    import openai as openai_pkg
    from openai import OpenAI
    OPENAI_VERSION = getattr(openai_pkg, "__version__", "unknown")
except Exception:
    OpenAI = None
    OPENAI_VERSION = None

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

def _responses_join_output_text(resp) -> str:
    """
    Join Responses API textual output blocks into a single string.
    """
    try:
        txt = getattr(resp, "output_text", None)
        if isinstance(txt, str) and txt.strip():
            return txt
        chunks = getattr(resp, "output", None) or []
        parts = []
        for ch in chunks:
            if isinstance(ch, dict):
                if ch.get("type") == "output_text" and isinstance(ch.get("text"), str):
                    parts.append(ch["text"])
            else:
                if getattr(ch, "type", "") == "output_text":
                    parts.append(getattr(ch, "text", ""))
        if parts:
            return "\n".join(parts)
    except Exception:
        pass
    try:
        return json.dumps(resp, default=str)
    except Exception:
        return str(resp)

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
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) KicktippBot/STRICT",
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

# --- NEW: stronger team-name extraction --------------------------------------
BAD_TOKENS = {"tipp", "joker", "punkte", "quote", "remis", "heim", "gast", "home", "away", "vs", ":"}

def _label_text_for_input(soup: BeautifulSoup, inp: Tag) -> Optional[str]:
    inp_id = inp.get("id")
    if inp_id:
        lab = soup.select_one(f'label[for="{inp_id}"]')
        if lab and lab.get_text(strip=True):
            return lab.get_text(strip=True)
    # aria-labelledby
    lbl = inp.get("aria-labelledby")
    if lbl:
        lab = soup.select_one(f'#{lbl}')
        if lab and lab.get_text(strip=True):
            return lab.get_text(strip=True)
    return None

def _attrib_name(inp: Tag) -> Optional[str]:
    # Try rich attributes
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
    cand = [t.strip() for t in texts if t and t.strip() and t.strip().lower() not in BAD_TOKENS and not re.fullmatch(r"\d+", t.strip())]
    # remove dupes, keep order
    uniq = list(dict.fromkeys(cand))
    if len(uniq) >= 2:
        return uniq[0], uniq[1]
    if len(uniq) == 1:
        return uniq[0], None
    return None, None

def _team_names_from_inputs(soup: BeautifulSoup, container: Tag, home_inp: Tag, away_inp: Tag) -> Tuple[str, str]:
    # 1) Direct attributes on inputs
    h = _attrib_name(home_inp)
    a = _attrib_name(away_inp)
    if h and a:
        return h, a
    # 2) Labels bound to inputs
    lh = _label_text_for_input(soup, home_inp)
    la = _label_text_for_input(soup, away_inp)
    if lh and la:
        return lh, la
    # 3) Tight container hints
    home = _extract_text(container, [".heim", ".home", ".team-heim", ".teamhome", "[data-home]"])
    away = _extract_text(container, [".gast", ".away", ".team-gast", ".teamaway", "[data-away]"])
    if home and away and (home.lower() not in {"heim","home"} and away.lower() not in {"gast","away"}):
        return home, away
    # 4) Nearest <tr> scanning: logos, anchors, spans with textual names
    tr = _nearest_tr(container) or _nearest_tr(home_inp) or _nearest_tr(away_inp) or container
    texts: List[str] = []
    # logo alts
    for img in tr.select("img[alt]"):
        alt = img.get("alt", "").strip()
        if alt:
            texts.append(alt)
    # anchors/title
    for an in tr.select("a[title],abbr[title],span[title]"):
        t = (an.get("title") or "").strip()
        if t:
            texts.append(t)
    # plain texts
    texts.extend([t.strip() for t in tr.stripped_strings if t and len(t.strip()) >= 2])
    h2, a2 = _choose_two_names(texts)
    if h2 and a2:
        return h2, a2
    # 5) Global fallback: still try tight container texts
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
# Prompt
# -----------------------------------------------------------------------------
def build_prompt_research(matchday_index: int, rows: List[Row]) -> str:
    lines = []
    lines.append("Du bist FootballPred LLM, ein sachlicher, quellengestützter Prognose-Assistent für Vereinsfußball.")
    lines.append("Ziele: je Spiel ein konkretes Ergebnis (Heim-/Auswärtstore) auf Basis von Quoten (overround-bereinigt),")
    lines.append("xG-/Elo-/Formdaten, Verletzungen/Sperren, vorauss. Aufstellungen, Heimvorteil/Kontext.")
    lines.append("Nutze das Websuche-Tool aktiv und zitiere Quellen (URLs).")
    lines.append("AUSGABEFORMAT (zwingend):")
    lines.append("{ 'predictions': [ {"
                 " 'row_index': int(1..N), 'matchday': int, 'home_team': str, 'away_team': str,"
                 " 'predicted_home_goals': int, 'predicted_away_goals': int, 'reason': str(<=250)"
                 " } ... ] }")
    lines.append("Regeln: Nur JSON; exakt N Items in gelisteter Reihenfolge; Teamnamen exakt; keine Serien gleicher Ergebnisse;")
    lines.append("1:1 nur bei klarer Remis-Tendenz; P(H)+P(D)+P(A)=1±0.01 (intern).")
    lines.append(f"\nSpieltag: {matchday_index}")
    lines.append("Spiele (index) Heim → Auswärts | Quoten H/D/A | Status:")
    for r in rows:
        status = "offen" if r.open else "geschlossen"
        lines.append(f"{r.index}) {r.home_team} vs {r.away_team} | Quoten: {odds_to_str(r.home_odds, r.draw_odds, r.away_odds)} | {status}")
    lines.append("\nGib ausschließlich das JSON-Objekt mit 'predictions' zurück.")
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
# Responses web_search detection
# -----------------------------------------------------------------------------
def _to_dict(resp_obj):
    for attr in ("to_dict", "model_dump", "dict"):
        f = getattr(resp_obj, attr, None)
        if callable(f):
            try:
                d = f()
                if hasattr(d, "items"):
                    return d
            except Exception:
                pass
    try:
        return json.loads(getattr(resp_obj, "model_dump_json", lambda: json.dumps(resp_obj, default=str))())
    except Exception:
        return json.loads(json.dumps(resp_obj, default=str))

def detect_web_search_usage(resp) -> Tuple[bool, Dict[str, List[str]]]:
    d = _to_dict(resp)
    used = False
    queries: List[str] = []
    urls: List[str] = []

    def visit(node):
        nonlocal used
        if isinstance(node, dict):
            t = str(node.get("type", "")).lower()
            tool_name = str(node.get("tool_name", "")).lower()
            if ("tool" in t and "web" in tool_name and "search" in tool_name) or \
               ("web" in t and "search" in t):
                used = True
                args = node.get("args") or node.get("action") or {}
                q = args.get("query") or args.get("search_query")
                if isinstance(q, str) and q.strip():
                    queries.append(q.strip())
                for key in ("results", "sources", "citations"):
                    items = node.get(key) or args.get(key) or []
                    if isinstance(items, list):
                        for it in items:
                            if isinstance(it, dict):
                                u = it.get("url") or it.get("link")
                                if isinstance(u, str) and u.startswith(("http://", "https://")):
                                    urls.append(u)
            for v in node.values():
                visit(v)
        elif isinstance(node, list):
            for v in node:
                visit(v)

    visit(d.get("output", d))
    queries = list(dict.fromkeys([q for q in queries if q]))
    urls = list(dict.fromkeys([u for u in urls if u]))
    return used, {"queries": queries, "urls": urls}

def _has_placeholder_teams(rows: List[Row]) -> bool:
    def is_placeholder(n: str) -> bool:
        return n.strip().lower() in {"heim", "gast", "home", "away"}
    return any(is_placeholder(r.home_team) or is_placeholder(r.away_team) for r in rows)

# -----------------------------------------------------------------------------
# OpenAI core
# -----------------------------------------------------------------------------
def call_openai_predictions_strict(matchday_index: int,
                                   rows: List[Row],
                                   api_key: str,
                                   model: str,
                                   temperature: float,
                                   timeout_s: float,
                                   max_retries: int = 3,
                                   raw_dir: Optional[Path] = None,
                                   prompt_profile: str = "research",
                                   require_sources_in_responses: bool = True) -> List[Dict]:
    if not OpenAI:
        raise RuntimeError("OpenAI SDK nicht verfügbar.")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY fehlt.")

    client = OpenAI(api_key=api_key, timeout=timeout_s)
    if OPENAI_VERSION:
        log.info(f"OpenAI SDK-Version erkannt: {OPENAI_VERSION}")

    n = len(rows)

    # Minimal strict schema for Chat (OpenAI requires additionalProperties=false under strict)
    item_props_chat = {
        "row_index": {"type": "integer", "minimum": 1, "maximum": n},
        "matchday": {"type": "integer"},
        "home_team": {"type": "string"},
        "away_team": {"type": "string"},
        "predicted_home_goals": {"type": "integer", "minimum": 0, "maximum": 9},
        "predicted_away_goals": {"type": "integer", "minimum": 0, "maximum": 9},
        "reason": {"type": "string", "maxLength": 250},
    }
    schema_chat = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "predictions": {
                "type": "array",
                "minItems": n,
                "maxItems": n,
                "items": {
                    "type": "object",
                    "additionalProperties": False,  # <-- strict requires this to be false
                    "properties": item_props_chat,
                    "required": list(item_props_chat.keys()),
                },
            }
        },
        "required": ["predictions"],
    }

    def _build_prompt(extra_hint: Optional[str] = None) -> str:
        base = build_prompt_research(matchday_index, rows)
        return base + ("\n" + extra_hint if extra_hint else "")

    # Skip web_search if team names are placeholders
    can_use_web = (prompt_profile == "research") and not _has_placeholder_teams(rows)

    # ----- Responses API (with web_search) -----
    if can_use_web:
        attempts = min(2, max_retries)
        for i in range(1, attempts + 1):
            extra = ""
            if i == 2 and require_sources_in_responses:
                extra = "WICHTIG: Verwende echte Quellen-URLs (http/https) pro Spiel."
            prompt = _build_prompt(extra)
            log.info("OpenAI[responses] call: model=%s, md=%s, matches=%s, profile=%s (Websuche aktiv, try=%s)",
                     model, matchday_index, n, prompt_profile, i)
            try:
                # NO response_format here (unsupported on Responses in this SDK)
                resp = client.responses.create(
                    model=model,
                    input=[
                        {
                            "role": "system",
                            "content": (
                                "Antworte ausschließlich in Deutsch. Gib NUR ein JSON-Objekt mit dem Schlüssel 'predictions' aus. "
                                "Nutze das Websuche-Tool für Quoten/News und nenne Quellen."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    tools=[{"type": "web_search"}],
                    temperature=temperature,
                )

                used, details = detect_web_search_usage(resp)
                if used:
                    log.info("Websuche: JA | queries=%s | urls=%s",
                             details["queries"][:3], details["urls"][:3])
                else:
                    log.warning("Websuche: NEIN – keine Web-Tool-Events erkannt.")

                content_text = _responses_join_output_text(resp)
                if raw_dir:
                    ensure_dir(raw_dir)
                    (raw_dir / f"md{matchday_index}_responses_try{i}.json").write_text(content_text or "", encoding="utf-8")

                data = _extract_json_object(content_text)
                preds = data.get("predictions")
                if not isinstance(preds, list) or len(preds) != n:
                    raise ValueError(f"Erwarte genau {n} Items, erhalten: {len(preds) if isinstance(preds, list) else 'kein Array'}.")

                fixed = validate_predictions(preds, rows, matchday_index, forbid_degenerate=True)
                # quick sanity for any sources urls inside JSON (optional)
                for item in preds or []:
                    for s in (item.get("sources") or []):
                        u = (s.get("url") or "").strip()
                        if u and not re.match(r"^https?://", u):
                            raise ValueError("Ungültige Quellen-URL erkannt.")
                return fixed
            except Exception as exc:
                log.warning("Responses-Websuche fehlgeschlagen (try %s/%s): %s", i, attempts, exc)
    else:
        if prompt_profile == "research":
            log.warning("Teamnamen Platzhalter ('Heim/Gast') erkannt — überspringe Websuche und nutze Chat-Fallback.")

    # ----- Chat Completions fallback (NO tools) -----
    last_err = None
    for attempt in range(1, max_retries + 1):
        extra_hint = ""
        if attempt >= 2:
            extra_hint = "Vermeide Serien gleicher Ergebnisse; 1:1 nur bei klarer Remis-Tendenz. Exakte Reihenfolge & row_index."
        prompt = _build_prompt(extra_hint)

        log.info("OpenAI[chat] call: model=%s, md=%s, matches=%s, try=%s, profile=%s",
                 model, matchday_index, n, attempt, prompt_profile)
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Antworte ausschließlich in Deutsch. Gib NUR ein JSON-Objekt mit dem Schlüssel 'predictions' aus. "
                            "Zeige KEINE Zwischenschritte, nur Ergebnisse."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "bundesliga_predictions", "strict": True, "schema": schema_chat},
                },
                temperature=temperature,
            )
            content = resp.choices[0].message.content if resp.choices else None
            if raw_dir:
                ensure_dir(raw_dir)
                (raw_dir / f"md{matchday_index}_chat_try{attempt}.json").write_text(content or "", encoding="utf-8")

            if not content:
                raise ValueError("Leere Antwort.")
            data = json.loads(content)
            preds = data.get("predictions")
            fixed = validate_predictions(preds, rows, matchday_index, forbid_degenerate=True)
            # optional URL sanity if model still emits 'sources'
            for item in preds or []:
                for s in (item.get("sources") or []):
                    u = (s.get("url") or "").strip()
                    if u and not re.match(r"^https?://", u):
                        raise ValueError("Ungültige Quellen-URL erkannt.")
            return fixed
        except Exception as e:
            last_err = e
            log.warning("Validierung fehlgeschlagen (chat try %s/%s): %s", attempt, max_retries, e)

    raise RuntimeError(f"OpenAI-Antwort unbrauchbar nach {max_retries} Versuchen: {last_err}")

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
    ap = argparse.ArgumentParser(description="Kicktipp Auto-Predictor (STRICT, Websuche via Responses API)")
    ap.add_argument("--config", default="config.ini")

    ap.add_argument("--username", default=None)
    ap.add_argument("--password", default=None)
    ap.add_argument("--pool-slug", default=None)

    ap.add_argument("--start-index", type=int, default=None)
    ap.add_argument("--end-index", type=int, default=None)

    ap.add_argument("--openai-key", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--oa-timeout", type=float, default=None)

    ap.add_argument("--max-retries", type=int, default=None)
    ap.add_argument("--prompt-profile", default=None)
    ap.add_argument("--allow-heuristic-fallback", action="store_true",
                    help="Nur für Notfälle. Wenn gesetzt, wird NIE 1:1 genommen; aber heuristisch aus Quoten geschätzt.")
    ap.add_argument("--no-submit", action="store_true")
    ap.add_argument("--proxy", default=None)

    args = ap.parse_args()

    cfg = load_config(args.config)
    ini_sections = ["DEFAULT", "auth", "kicktipp", "pool", "openai", "run", "settings"]

    def resolve(key_cli, envs, inis, cast, default):
        return resolve_value(getattr(args, key_cli), envs, inis, ini_sections, cfg, cast, default)

    username = resolve("username", ["KICKTIPP_USERNAME", "KICKTIPP_USER"], ["username", "user", "kennung", "login", "email"], str, None)
    password = resolve("password", ["KICKTIPP_PASSWORD", "KICKTIPP_PASS"], ["password", "passwort", "pwd"], str, None)
    pool_slug = resolve("pool_slug", ["KICKTIPP_POOL_SLUG", "POOL_SLUG"], ["pool_slug", "pool", "runde", "group_slug", "competition"], str, None)

    start_index = resolve("start_index", ["START_INDEX"], ["start_index", "from", "start"], int, 1)
    end_index = resolve("end_index", ["END_INDEX"], ["end_index", "to", "end"], int, None)

    openai_key = resolve("openai_key", ["OPENAI_API_KEY", "OPENAI_KEY"], ["api_key", "openai_api_key", "key", "token"], str, None)
    model = resolve("model", ["OPENAI_MODEL"], ["model", "openai_model"], str, "gpt-4o")
    temperature = resolve("temperature", ["OPENAI_TEMPERATURE"], ["temperature", "temp"], float, 0.8)
    oa_timeout = resolve("oa_timeout", ["OPENAI_TIMEOUT", "OA_TIMEOUT"], ["oa_timeout", "timeout", "openai_timeout"], float, 120.0)
    max_retries = resolve("max_retries", ["OPENAI_MAX_RETRIES"], ["max_retries", "retries"], int, 3)
    allow_heuristic = args.allow_heuristic_fallback or parse_bool(get_ini_value(cfg, ["allow_heuristic_fallback"], ini_sections), False)
    prompt_profile = resolve("prompt_profile", ["OPENAI_PROMPT_PROFILE"], ["promptprofile", "prompt_profile"], str, "research")

    no_submit = args.no_submit or parse_bool(get_ini_value(cfg, ["no_submit"], ini_sections), False)
    proxy = resolve("proxy", ["HTTPS_PROXY", "HTTP_PROXY"], ["proxy", "https_proxy", "http_proxy"], str, None)

    if not username or not password or not pool_slug:
        print("Fehler: username/password/pool_slug fehlen (config.ini/ENV/CLI).", file=sys.stderr)
        sys.exit(2)
    if not openai_key:
        print("Fehler: OPENAI_API_KEY fehlt (config.ini/ENV/CLI). STRICT-Modus benötigt die API.", file=sys.stderr)
        sys.exit(2)

    if proxy:
        os.environ["HTTPS_PROXY"] = proxy
        os.environ["HTTP_PROXY"] = proxy

    log.info(
        f"pool={pool_slug} | start={start_index} | end={end_index or 'auto'} | "
        f"model={model} | temp={temperature} | retries={max_retries} | "
        f"heuristic={'on' if allow_heuristic else 'off'} | submit={'off' if no_submit else 'on'} | "
        f"timeout={oa_timeout}s | user={username} | key={mask_secret(openai_key)}"
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
    raw_dir = OUT_DIR / "raw_openai"
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

        # --- Predictions
        try:
            preds = call_openai_predictions_strict(
                matchday_index=idx,
                rows=rows,
                api_key=openai_key,
                model=model,
                temperature=temperature,
                timeout_s=float(oa_timeout),
                max_retries=int(max_retries),
                raw_dir=raw_dir,
                prompt_profile=prompt_profile,
                require_sources_in_responses=True,
            )
        except Exception as e:
            if allow_heuristic:
                log.error(f"OpenAI fehlgeschlagen, nutze HEURISTIK (aktiviert): {e}")
                preds = []
                for r in rows:
                    ho, do, ao = r.home_odds, r.draw_odds, r.away_odds
                    # Simple odds-aware heuristic (never mass 1:1)
                    if ho and ao and ho < ao * 0.7:
                        hg, ag = 2, 0
                    elif ao and ho and ao < ho * 0.7:
                        hg, ag = 0, 2
                    elif do and ho and ao and do < min(ho, ao):
                        hg, ag = 1, 1  # draw only when draw is the shortest price
                    else:
                        hg, ag = 2, 1
                    preds.append({
                        "row_index": r.index, "matchday": idx,
                        "home_team": r.home_team, "away_team": r.away_team,
                        "predicted_home_goals": hg, "predicted_away_goals": ag,
                        "reason": f"Heuristik aus Quoten {odds_to_str(ho, do, ao)}"
                    })
            else:
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
        "raw_openai_dir": str(raw_dir.resolve()),
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
