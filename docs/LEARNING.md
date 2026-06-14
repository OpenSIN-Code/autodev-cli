# Closed Learning Loop

> "Der Agent, der lernt, sich entwickelt, niemals vergisst."

## Das Problem

LLMs machen **dieselben Fehler immer wieder**:
- Falsche Imports (`import numpy` obwohl nicht erlaubt)
- Syntax-Fehler in spezifischen Kontexten
- Veraltete API-Aufrufe
- Performance-Fallen (z. B. O(n²) in Hot-Path)

Jeder Fehlschlag kostet Token und Zeit. **SIN-Code löst das mit persistenter Wissensbasis.**

## Architektur

```
        ┌──────────────────────────────────┐
        │     Failed Verification          │
        │   (stderr + pattern extraction)  │
        └────────────┬─────────────────────┘
                     │
                     ▼
        ┌──────────────────────────────────┐
        │   Pattern Classifier (Heuristik) │
        │   import_error / syntax_error /  │
        │   test_failure / timeout / ...   │
        └────────────┬─────────────────────┘
                     │
                     ▼
        ┌──────────────────────────────────┐
        │      SQLite Knowledge Base       │
        │  ~/.autodev/knowledge.db         │
        │  ┌─────────────────────────────┐ │
        │  │ lessons (pattern, failure,  │ │
        │  │          fix, context,      │ │
        │  │          applied_count)     │ │
        │  └─────────────────────────────┘ │
        └────────────┬─────────────────────┘
                     │
                     ▼
        ┌──────────────────────────────────┐
        │    Next PLAN-Phase: Query        │
        │    SELECT * FROM lessons         │
        │    WHERE pattern LIKE '%x%'      │
        │    → Injiziert in LLM-Prompt     │
        └──────────────────────────────────┘
```

## Pattern-Klassifikation

Die `_extract_lesson()`-Funktion im Agent Loop erkennt automatisch:

| Pattern | Trigger |
|---|---|
| `import_error` | `ImportError`, `ModuleNotFoundError` |
| `syntax_error` | `SyntaxError` |
| `test_failure` | `AssertionError`, `FAILED` |
| `timeout` | `TimeoutExpired` |
| `type_error` | `TypeError`, `AttributeError` |
| `runtime_error` | `RuntimeError`, `ValueError` |
| `unknown` | Fallback |

Aktuell implementiert in `autodev/agent_loop.py::_extract_lesson()`:
- `import_error`
- `syntax_error`
- `test_failure`
- `timeout`
- `unknown`

## Prompt-Injektion

Vor jeder Mutation fragt der Agent die KB ab und injiziert die Top-5 Lessons:

```
## Past Failures (AVOID THESE)
- Pattern: import_error
  Failure: ModuleNotFoundError: No module named 'numpy'
  Fix: Use built-in Python libraries only

- Pattern: timeout
  Failure: Execution exceeded 300s timeout
  Fix: Optimize nested loops
```

**Effekt**: Der LLM sieht diese Warnungen **bevor** er Code generiert und vermeidet bekannte Fallstricke.

## Manuelle Verwaltung

```bash
# Alle Lessons ansehen
autodev knowledge list

# Stats abrufen
autodev knowledge stats
# Total lessons: 47
# Applied: 238

# KB löschen (z. B. bei Paradigmenwechsel)
autodev knowledge clear
```

### MCP-Zugriff

Da unsere Wissensbasis auch über `autodev-mcp` als MCP-Tool exponiert wird,
kann jede LLM-fähige Anwendung (z. B. SIN-Code WebUI v2) auf sie zugreifen:

```json
{
  "method": "tools/call",
  "params": {
    "name": "autodev_lessons",
    "arguments": { "project_root": "/path/to/repo", "pattern": "timeout", "limit": 10 }
  }
}
```

## Team-Sync (Roadmap)

```bash
# Zukünftig: Lessons im Team teilen
autodev knowledge push --server https://team.example.com
autodev knowledge pull
```

## SQLite-Schema

```sql
CREATE TABLE lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL,
    failure TEXT NOT NULL,
    fix TEXT,
    context TEXT,
    applied_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_lessons_pattern ON lessons(pattern);
```

Die drei SQLite-Tabellen:

| Tabelle | Zweck |
|---|---|
| `lessons` | Erlernte Fehler + Fixes (closed-loop memory) |
| `experiments` | Audit-Log jeder Mutation (metric_value, delta, duration, success, diff) |
| `goals` | Goal-Queue für Priorisierung |

## Metriken

Eine gut trainierte KB zeigt:
- **Hohe `applied_count`** bei häufigen Patterns → Agent vermeidet diese Fehler
- **Wenige neue Einträge** pro Session → Code-Basis wird stabiler
- **Sinkende Fehlschlag-Rate** über Zeit → Learning Loop funktioniert
