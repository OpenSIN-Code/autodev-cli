# Swarm Mode

> "N Agenten. Eine Aufgabe. Erste verifizierte Lösung gewinnt."

## Konzept

Inspiriert von **SIN-Code v3.6.0**: Statt einen Agenten eine Lösung suchen zu lassen,
starten wir **mehrere Agenten parallel** mit unterschiedlichen Strategien:

| Profil | Modell | Temperature | Strategie |
|---|---|---|---|
| `fast` | gpt-4o-mini | 0.3 | Schnelle, simple Fixes |
| `precise` | gpt-4o | 0.1 | Konservative, sichere Lösungen |
| `creative` | claude-3-opus | 0.9 | Radikale Refactors |

**Erste verifizierte Lösung gewinnt** — alle anderen werden abgebrochen (Token-Sparen!).

## Nutzung

```bash
# Standard-Schwarm
autodev swarm -p "Optimiere die Datenbank-Queries in src/repo.py"

# Mit spezifischen Profilen
autodev swarm -p "..." --agents fast,precise --budget-minutes 20

# Alle 4 Profile
autodev swarm -p "..." --agents fast,precise,creative,audit
```

## Sicherheits-Invarianten (SIN-Code M3/M4)

1. **No gate → no swarm**: `verify_cmd` ist Pflicht
2. **First verified wins**: Nur verifizierte Lösungen gewinnen
3. **Budget exhausted → human**: Bei Timeout wird abgebrochen

## Architektur

```
┌─────────────────────────────────────────┐
│           Swarm Coordinator             │
│  (verteilt Prompt, sammelt Results)     │
└───────────────┬─────────────────────────┘
                │
    ┌───────────┼───────────┬──────────────┐
    ▼           ▼           ▼              ▼
┌────────┐ ┌────────┐ ┌────────┐     ┌────────┐
│  fast  │ │precise │ │creative│ ... │ audit  │
│ Agent  │ │ Agent  │ │ Agent  │     │ Agent  │
└───┬────┘ └───┬────┘ └───┬────┘     └───┬────┘
    │          │          │              │
    └──────────┴──────────┴──────────────┘
                │
                ▼
    ┌──────────────────────────┐
    │   Verification Race      │
    │   Erste bestandene       │
    │   Prüfung gewinnt        │
    └──────────────────────────┘
```

## Konfiguration

In `.autodev/profiles.toml`:

```toml
[[profiles]]
name = "fast"
model = "gpt-4o-mini"
temperature = 0.3
max_tokens = 2000

[[profiles]]
name = "precise"
model = "gpt-4o"
temperature = 0.1
max_tokens = 4000

[[profiles]]
name = "creative"
model = "claude-3-opus"
temperature = 0.9
max_tokens = 6000
```

## Use Cases

| Szenario | Profile | Warum |
|---|---|---|
| Bug fixen | `precise` + `fast` | Schnelle Lösung mit Safety-Check |
| Refactoring | `creative` + `audit` | Innovative Lösung mit Review |
| Performance | `fast` + `precise` | Quick wins + nachhaltige Fixes |
| Security | `precise` + `audit` | Conservative + explizite Prüfung |

## Status

> ✅ Implementiert in **v0.3.0**. `autodev swarm` und das MCP-Tool
> `autodev_swarm` laufen mit ThreadPool-basierter parallel-execution.
> First-verified-wins race mit Loser-Forensics unter
> `.autodev/swarm-lost/`. Lessons werden aus allen Agents in die
> gemeinsame KB geschrieben (SIN-Code closed learning loop bleibt aktiv).

## Verifikation

```bash
# CLI smoke
autodev swarm \
  -p "Reduce /api/users latency by 30%" \
  --agents fast,precise,creative \
  --verify-cmd "pytest -q" \
  --budget-minutes 5 --json

# MCP smoke
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call",
      "params":{"name":"autodev_swarm",
                "arguments":{"project_root":"/path/to/repo",
                             "prompt":"...","verify_cmd":"pytest -q"}}}' \
  | autodev-mcp
```

## Konfiguration (Profile TOML)

`.autodev/profiles.toml` ist optional. Ohne Datei fallen
`--agents=fast,precise,creative` auf die Built-in-Defaults zurück.
Mit Datei überschreiben deren Einträge die Defaults (shallow-merge).
