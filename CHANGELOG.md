# Changelog - Kicktipp-GPT Bot

Alle wichtigen Änderungen am Projekt werden hier dokumentiert.

## [1.1.0] - 2025-10-17

### ✨ Neu hinzugefügt
- **Claude Sonnet 4.5 Version** in `claude/` Ordner
- **Optimierte Prompts** - Natürlicher Konversationsstil statt akademischer Struktur
- **Extended Thinking** optional (Standard: deaktiviert für bessere Performance)
- **Web-Recherche** mit DuckDuckGo für Live-Daten
- **Professionelle Dokumentation** in claude/README.md

### 🐛 Bugfixes
- **Parser-Bugfix**: Datums-/Zeitangaben werden nicht mehr als Teamnamen erkannt
  - Filtert `dd.mm.yy`, `hh:mm`, `dd.mm.yy hh:mm` Formate
  - Robustere Teamnamen-Extraktion
- **Temperature-Handling**: Automatische Anpassung basierend auf Extended Thinking Mode

### 🔧 Verbesserungen
- **Konfiguration**: `use_extended_thinking` Parameter hinzugefügt
- **Temperature**: Standard von 1.0 → 0.7 (fokussierter)
- **Validierung**: Verbesserte Fehlerbehandlung mit detaillierten Logs
- **Performance**: Schnellere Predictions ohne Extended Thinking (~30-60s statt 60-120s)

### 📚 Dokumentation
- Vollständig überarbeitete README.md (claude/)
- Detailliertes Troubleshooting mit häufigen Problemen
- Best Practices und Performance-Optimierung
- Erweiterte Konfigurationsoptionen dokumentiert

### 🔄 Migration
- **Alte OpenAI-Version** → `openai/` Ordner (unverändert)
- **Neue Claude-Version** → `claude/` Ordner (empfohlen)
- Beide Versionen parallel nutzbar

## [1.0.0] - 2025-10-15

### Initial Release
- OpenAI GPT-5 Implementation
- Robustes HTML-Parsing
- Submit & Verification
- Audit Trail (forms, predictions, raw)
- Strict Validation
- Anti-Degeneration Logic

---

**Format:** [Version] - YYYY-MM-DD
**Versionierung:** [Major.Minor.Patch]
- Major: Breaking Changes
- Minor: Neue Features (rückwärtskompatibel)
- Patch: Bugfixes
