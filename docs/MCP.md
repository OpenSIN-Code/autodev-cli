# Model Context Protocol (MCP)

> "Externe Tools als standardisierte MCP-Server anbinden."

## Konzept

MCP (Model Context Protocol) ist ein offener Standard, um LLMs mit externen Tools
zu verbinden. AutoDev-CLI nutzt MCP für:

- 🔍 **Websearch** — Dokumentation finden
- 🌐 **Browser** — APIs testen
- 📊 **Analytics** — Metriken aus Grafana/Plausible
- 🔧 **Custom Tools** — eigene MCP-Server schreiben
- 🤖 **AutoDev selbst** — von einem LLM wie Claude Code oder dem SIN-Code WebUI Model steuern

## AutoDev als MCP-Server (`autodev-mcp`)

Ab v0.2.0 wird AutoDev-CLI **gleichzeitig** als MCP-Server ausgeliefert.
Das LLM einer anderen Anwendung (z. B. Claude Code, SIN-Code WebUI v2)
kann AutoDev über stdio mit JSON-RPC steuern.

### Vier exportierte Tools

| Tool Name | CLI-Äquivalent | Beschreibung |
|---|---|---|
| `autodev_status` | `autodev status --json` | Project-Status, Lektionen-Stats |
| `autodev_lessons` | `autodev knowledge list` | Recent Lessons aus der SQLite KB |
| `autodev_run_experiment` | `autodev optimize … --json` | Mutation vorschlagen + verifizieren |
| `autodev_init` | `autodev init … --json` | Neues Program in einem Repo initialisieren |

### Smoke-Test

```bash
# Handshake gegen autodev-mcp
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | autodev-mcp
# → {"jsonrpc":"2.0","id":1,"result":{"tools":[...]}}

# Direkter Tool-Aufruf
echo '{"jsonrpc":"2.0","id":2,"method":"tools/call",
      "params":{"name":"autodev_status",
                "arguments":{"project_root":"/path/to/repo"}}}' | autodev-mcp
```

### Architektur (Bridge-Pattern)

```
┌──────────────┐  stdio / JSON-RPC   ┌───────────────┐  shell  ┌──────────────┐
│ LLM-Client   │ ──────────────────▶│  cli_mcp.py   │ ──────▶ │  cli.py      │
│ (Claude /    │ ◀────────────────── │ (no business  │  stdout │ (--json)     │
│  WebUI)      │    NDJSON result    │   logic)      │ ◀────── │              │
└──────────────┘                     └───────────────┘  stderr  └──────────────┘
```

**Designprinzip**: `cli_mcp.py` enthält **keine Geschäftslogik**.
Es ist eine dünne JSON-Parser-Schicht, die `autodev … --json` aufruft und
das Ergebnis 1:1 weiterreicht. Die ganze Logik lebt in `cli.py` und ist
PYTEST-getestet.

### Timeout & Sicherheit

- Pro Tool-Aufruf: **300 Sekunden Timeout** (`subprocess.run(timeout=300)`)
- Bei Nicht-JSON-Output: `RuntimeError("non-JSON stdout from CLI")`
- Bei Exit ≠ 0: Tool-Result `isError: true` mit stderr im Output

Damit können Endlosschleifen im LLM das WebUI nicht blockieren; jede
Mutation hat trotzdem ihr eigenes `verify_cmd`-Gate.

## Setup mit externen MCP-Servern

### 1. Konfiguration erstellen

`.autodev/mcp.json`:

```json
{
  "servers": [
    {
      "name": "websearch",
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-websearch"],
      "env": {
        "BRAVE_API_KEY": "..."
      }
    },
    {
      "name": "filesystem",
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-filesystem", "/tmp"]
    }
  ]
}
```

### 2. Verfügbare Tools auflisten

```bash
autodev mcp list
# Server: websearch
#   - websearch__search
#   - websearch__get_page
#
# Server: filesystem
#   - filesystem__read_file
#   - filesystem__write_file
```

### 3. Tool direkt aufrufen

```bash
autodev mcp call websearch search --query "python asyncio best practices"
```

## Custom MCP Server

### Beispiel: JSON Formatter

`skills/json-fmt/server.py`:

```python
from mcp.server import Server
import json

app = Server("json-fmt")

@app.tool()
def format_json(input: str, indent: int = 2) -> str:
    """Format a JSON string with specified indent."""
    return json.dumps(json.loads(input), indent=indent)

if __name__ == "__main__":
    app.run()
```

### Registrieren

```bash
# Manuell
autodev mcp register json-fmt python skills/json-fmt/server.py

# Oder via Bootstrap (SIN-Code v3.6.0)
SIN_ALLOW_BOOTSTRAP=1 autodev chat \
  -p "use bootstrap_skill to add a json-fmt tool"
```

## Security

MCP-Server laufen **isoliert** mit eigenen Permission-Gates:

```json
{
  "servers": [{
    "name": "dangerous",
    "command": "...",
    "permissions": {
      "filesystem": "deny",
      "network": "ask"
    }
  }]
}
```

## Bekannte MCP-Server

| Server | Zweck | Installation |
|---|---|---|
| `@anthropic/mcp-websearch` | Websuche | `npx -y @anthropic/mcp-websearch` |
| `@anthropic/mcp-filesystem` | Dateisystem | `npx -y @anthropic/mcp-filesystem` |
| `@anthropic/mcp-browser` | Browser-Automation | `npx -y @anthropic/mcp-browser` |
| `@anthropic/mcp-github` | GitHub API | `npx -y @anthropic/mcp-github` |
