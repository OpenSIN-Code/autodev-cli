# Safety & Bounded Autonomy

> "Autonome Agenten brauchen harte Grenzen — oder sie verwüsten dein Repo."

## Die drei harten Invarianten (SIN-Code M3/M4)

### 🔒 Invariante 1: No Gate → No Daemon

```
verify_cmd ist mandatory.
Ohne Verifizierung startet der Daemon nicht.
```

**Warum?** Ein autonomer Agent ohne Oracle produziert Müll in industriellem Maßstab.

```bash
# ❌ Fehlt verify_cmd → Exit 2
autodev daemon
# Error: Missing option '--verify-cmd'

# ✅ So ist es richtig
autodev daemon --verify-cmd "pytest -q"
```

### 🔒 Invariante 2: Budget Exhausted → Hook Summons Human

```
Wenn Zeit oder Experimente aufgebraucht sind,
stoppt der Agent SOFORT und ruft den Menschen.
```

**Implementierung**: `BudgetWatcher.check()` prüft jede Iteration:

```python
def check(self) -> BudgetStatus:
    exhausted = time_remaining <= 0 or experiments_remaining <= 0
    if exhausted:
        self.save_report()  # Kein weiterer LLM-Call!
        return BudgetStatus(exhausted=True)
```

### 🔒 Invariante 3: Headless → Ask=Deny

```
Im CI/CD-Modus (AUTODEV_HEADLESS=1) sind alle
destruktiven Operationen automatisch verweigert.
```

```bash
# Im Headless-Modus:
AUTODEV_HEADLESS=1 autodev goal add "..." --execute
# → PermissionDenied: Mutating ops require human confirmation
```

## Scope-Beschränkung

### AGENTS.md als Firewall

```markdown
## Forbidden Actions
- Modifying AGENTS.md
- Running destructive git commands (force push, reset --hard)
- Installing system packages without explicit approval
```

Der Agent Loop prüft **jede Mutation** gegen diese Liste:

```python
if target_file in config.forbidden_files:
    raise PermissionDenied(f"{target_file} is forbidden by AGENTS.md")
```

### Erlaubte Dateien (`allowed_files`)

```markdown
## Allowed Files
- src/data_pipeline.py
- src/utils.py
```

**Effekt**: Der Agent kann **nur diese Dateien mutieren**. Alles andere ist read-only.

## Secrets-Schutz

```python
# In mutator.py:
PATTERNS_BLOCKED = [
    r"sk-[a-zA-Z0-9]{48}",      # OpenAI Keys
    r"ghp_[a-zA-Z0-9]{36}",     # GitHub Tokens
    r"AKIA[A-Z0-9]{16}",        # AWS Keys
]

for pattern in PATTERNS_BLOCKED:
    if re.search(pattern, mutated_code):
        raise SecurityViolation("Potential secret in LLM output")
```

## Rollback-Strategie

### Git Stash Snapshots

```python
def _git_snapshot(self) -> str:
    subprocess.run(
        ["git", "stash", "push", "-m", f"autodev-snapshot-{int(time.time())}"],
        cwd=self.project_root,
    )

def _rollback(self):
    subprocess.run(["git", "checkout", "."], cwd=self.project_root)
```

**Vorteile**:
- Atomar
- Kein Datenverlust
- Jede Session ist reproduzierbar

## Threat Model

| Bedrohung | Abwehr |
|---|---|
| LLM schreibt destruktiven Code | `verify_cmd` fängt es ab |
| Endlos-Loop frisst Token | `BudgetWatcher` stoppt nach N Minuten |
| Agent modifiziert Config-Dateien | `allowed_files`-Whitelist |
| Prompt Injection via Code | Secrets-Detection + Scope-Limit |
| CI läuft Amok | `AUTODEV_HEADLESS=1` → ask=deny |

## Notausstieg

```bash
# Strg+C unterbricht sofort
# Daemon speichert Report und endet gracefully

# Alternativ: Budget auf 0 setzen
autodev daemon --budget-minutes 0  # Beendet sofort nach Setup
```

## Audit-Log

Jedes Experiment wird in SQLite protokolliert:

```sql
CREATE TABLE experiments (
    id INTEGER PRIMARY KEY,
    metric_value REAL,
    metric_delta REAL,
    duration_seconds REAL,
    success BOOLEAN,
    diff TEXT,
    created_at TEXT
);
```

**Forensik**: Nach einer Session kannst du genau nachvollziehen, welche Mutationen funktioniert haben und welche nicht.

## MCP-Bridge & AutoDev

Der MCP-Server (`autodev-mcp`) ist ein Verteidigungselement:

- Liest ausschließlich JSON aus dem CLI-Unterprozess (kein LLM-Call)
- Hat einen 5-Minuten Timeout pro Tool-Call (siehe `_run_cli`)
- Stille Degradation wenn `autodev` Binary fehlt — kein Crash

Angreifer können den Agent über die MCP-Schnittstelle **nicht** direkt beeinflussen,
da jede Mutation weiterhin der `verify_cmd` unterworfen ist.
