# Cookbook — Praxis-Rezepte

## 🚀 Quick Wins

### 1. Hot Function optimieren

```bash
autodev optimize src/crypto/hash.py \
  --metric-cmd "python bench/hash_bench.py" \
  --budget-minutes 15
```

**Ergebnis**: Agent probiert Algorithmen, misst Execution-Time, behält nur Verbesserungen.

### 2. Test-Coverage pushen

```bash
autodev daemon \
  --verify-cmd "pytest --cov=src --cov-fail-under=95" \
  --budget-minutes 60
```

**Ergebnis**: Agent schreibt Tests, bis Coverage ≥ 95%.

### 3. Memory Leak fixen

```bash
# program.md
## Metric
- **Target**: `peak_memory_mb`
- **Measurement**: `python -X tracemalloc=5 bench.py`

autodev daemon --verify-cmd "pytest && python bench.py"
```

### 4. API Latency senken

```bash
autodev daemon \
  --verify-cmd "pytest -q && ./bench/api_latency.sh" \
  --budget-minutes 45
```

## 🎯 Advanced Patterns

### Goal-Queue für Backlog

```bash
# Mehrere Ziele priorisieren
autodev goal add "Reduce /api/users latency by 30%" --priority 9
autodev goal add "Add rate limiting" --priority 7
autodev goal add "Refactor auth module" --priority 5

# Cron-Job für nachts
0 2 * * * cd /repo && autodev daemon --verify-cmd "pytest -q"
```

### Swarm-Mode für Architektur-Entscheidungen

```bash
autodev swarm -p "Implement OAuth2 flow" \
  --agents fast,precise,creative \
  --budget-minutes 20
```

**Ergebnis**: Drei Agenten mit unterschiedlichen Strategien arbeiten parallel.
Der erste mit **verifizierter** Lösung gewinnt.

### TDD-Workflow mit Superpowers

```bash
# Skills installieren
autodev superpowers install
autodev superpowers init  # Injiziert TDD-Prompt

# Agent arbeitet strikt: Red → Green → Refactor
autodev daemon --verify-cmd "pytest -q"
```

## 🛠️ Troubleshooting

### "Baseline verification failed"

```
Ursache: verify_cmd schlägt schon vor Mutationen fehl.
Lösung:
  1. pytest manuell ausführen
  2. verify_cmd in program.md korrigieren
  3. Dependencies installieren
```

### "Budget exhausted, no improvements"

```
Ursache: Agent findet keine besseren Lösungen.
Lösung:
  1. Ziel relaxieren (z. B. "10% besser" statt "50%")
  2. Mehr Experimente erlauben (--max-experiments 50)
  3. Ziel-Datei erweitern (mehr Files in allowed_files)
```

### "LLM error: rate limit"

```
Ursache: API-Rate-Limit erreicht.
Lösung:
  - OPENAI_API_KEY wechseln
  - Sleep zwischen Experimenten (in agent_loop.py)
  - Lokales Modell nutzen (Ollama)
```

## 📊 Erfolgsmetriken

| Metrik | Gut | Schlecht |
|---|---|---|
| Improvement Rate | >30% | <10% |
| Lessons Applied | >100/Session | <10 |
| Experiments/Hour | 8-12 | <5 |
| Token Cost/Improvement | <0.50€ | >2€ |

## 🔌 MCP-Server via SIN-Code WebUI

Du kannst `autodev-mcp` ohne lokale Shell auch aus **SIN-Code WebUI v2** heraus benutzen.
Das WebUi lädt den MCP-Server automatisch (graceful degradation wenn Binary fehlt) und
stellt folgende Tools zur Verfügung:

| MCP Tool | CLI-Äquivalent |
|---|---|
| `autodev_status` | `autodev status --json` |
| `autodev_lessons` | `autodev knowledge list` |
| `autodev_run_experiment` | `autodev optimize … --json` |
| `autodev_init` | `autodev init … --json` |

Siehe `docs/MCP.md` und WebUI `lib/sin/mcp.ts` für die Verkabelung.
