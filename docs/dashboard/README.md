# Dashboard (Comb)

Comb is a centralised web server that serves dashboards for all registered Workers. It is config-driven — no custom code required per Worker.

Access your Worker's dashboard at:

```
http://localhost:8080/workers/<name>
```

Or from another device on the same network using the host machine's LAN IP. Comb binds to `0.0.0.0` by default.

The index at `http://localhost:8080/` lists all registered Workers.

## Managing Comb

```bash
hive comb start    # Start the Comb server
hive comb stop     # Stop the Comb server
hive comb restart  # Restart the Comb server
```

By default Comb listens on port `8080`. If that port is taken, it increments until it finds a free one.

## Configuration

Dashboard cells are defined in the `[comb]` section of `hive.toml`:

```toml
[comb]
theme = "terminal-dark"
cells = [
  { type = "log",    title = "Activity",    source = "logs/out.log" },
  { type = "metric", title = "Tasks Today", source = "memory/stats.json", key = "tasks_today" },
]
```

The `theme` field is optional and defaults to `"terminal-dark"`.

## Cell Types

Each cell is an inline table with at minimum `type`, `title`, and `source` fields. The `source` path is relative to the Worker folder.

### `log`

Tails a log file and streams new lines in real time via Server-Sent Events (SSE). Best for `logs/out.log` or any append-only log file.

```toml
{ type = "log", title = "Activity", source = "logs/out.log" }
```

The cell opens the file, seeks to the end, and pushes each new line to the browser as it appears. The browser auto-scrolls to the latest content.

### `file`

Displays the plain text contents of a file. If `source` is a directory, Comb automatically resolves to the most recently modified file in that directory and shows its name as a subtitle.

```toml
{ type = "file", title = "Notes", source = "memory/notes.txt" }
```

If the resolved file has a `.md` extension, Comb renders it as HTML automatically (same behavior as the `markdown` cell type).

### `markdown`

Renders a Markdown file as HTML. Same directory resolution behavior as `file`.

```toml
{ type = "markdown", title = "Summary", source = "memory/summary.md" }
```

Rendered using [mistune](https://mistune.lepture.com/).

### `metric`

Extracts a single top-level key from a JSON object file and displays it as a large number. Useful for counts, totals, or any scalar value.

```toml
{ type = "metric", title = "Tasks Today", source = "memory/stats.json", key = "tasks_today" }
```

The `key` field is required. Example JSON file:

```json
{ "tasks_today": 12, "tasks_week": 47 }
```

### `status`

Like `metric`, but applies semantic coloring based on the value. Useful for health checks and operational state indicators.

```toml
{ type = "status", title = "System Status", source = "memory/health.json", key = "status" }
```

Color mapping:

| Value | Color |
|---|---|
| `ok`, `success`, `pass`, `true`, `running`, `1` | Green |
| `warn`, `warning`, `degraded` | Yellow |
| `error`, `fail`, `failed`, `false`, `stopped`, `down`, `0` | Red |
| Anything else | Neutral |

Comparison is case-insensitive.

### `table`

Renders a JSON array of objects as an HTML table. Column headers are derived from the object keys.

```toml
{ type = "table", title = "Recent Tasks", source = "memory/tasks.json" }
```

Example JSON file:

```json
[
  { "task": "Send report", "status": "done", "date": "2026-03-27" },
  { "task": "Review PR",   "status": "pending", "date": "2026-03-27" }
]
```

The file must contain a JSON array. If it contains an object, Comb will show an error.

### `chart`

Renders numeric data as a chart. Accepts either a JSON array of numbers, a JSON array of `{"label": str, "value": number}` objects, or a JSON object with a specific key pointing to such an array.

```toml
{ type = "chart", title = "Daily Activity", source = "memory/activity.json" }
```

With a `key` to extract from a JSON object:

```toml
{ type = "chart", title = "Daily Activity", source = "memory/stats.json", key = "daily_counts" }
```

Example JSON file (array of numbers):

```json
[4, 7, 2, 9, 5, 11, 3]
```

Example JSON file (labeled values):

```json
[
  { "label": "Mon", "value": 4 },
  { "label": "Tue", "value": 7 },
  { "label": "Wed", "value": 2 }
]
```

### `app`

Embeds a full-page interactive application in your dashboard. The cell renders as a card with an **Open** button; clicking it navigates to a dedicated URL served by a FastAPI router you define in the Worker folder.

```toml
{ type = "app", title = "Browse Transactions", source = "dashboard/browse_app.py" }
```

The `source` path (relative to the Worker folder) must point to a Python file that exports either:

- **`make_router(worker_dir: Path) -> APIRouter`** *(preferred)* — a factory function called once at Comb startup with the Worker folder path as an argument. Use this when your app needs to read Worker files.
- **`router: APIRouter`** — a bare `APIRouter` instance. In this case, locate the Worker folder yourself (e.g. `Path(__file__).resolve().parent.parent`).

The app is served at `/workers/{name}/apps/{slug}`, where `slug` is derived from the cell title by lowercasing and replacing non-alphanumeric characters with hyphens (`"Browse Transactions"` → `"browse-transactions"`).

Any sub-routes defined on the router (`/api/data`, `/submit`, etc.) are automatically available under that prefix.

**Minimal example** (`dashboard/browse_app.py`):

```python
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pathlib import Path

def make_router(worker_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/")
    async def index():
        transactions = (worker_dir / "memory" / "transactions.json").read_text()
        return HTMLResponse(f"""
        <html><body>
          <h1>Transactions</h1>
          <pre>{transactions}</pre>
        </body></html>
        """)

    @router.post("/categorise")
    async def categorise(data: dict):
        # update memory/transactions.json ...
        return {"ok": True}

    return router
```

The router has access to the full FastAPI ecosystem — `Request`, `Form`, `HTMLResponse`, `JSONResponse`, `Jinja2Templates`, etc. Only packages installed in the Hive environment are available; Worker-specific `.venv` packages are not.

> **Note:** App routers are mounted when the Comb server starts. After adding or changing an `app` cell, run `hive comb restart` for the change to take effect.

## Directory Source Behavior

For `file` and `markdown` cell types, `source` can point to either a file or a directory. When it points to a directory, Comb selects the most recently modified file in that directory and renders it. The cell subtitle shows the selected filename.

This is useful for agent workflows where the agent writes timestamped or rotating files to a directory.

If the directory is empty, the cell shows an error.

## Complete Example

```toml
[worker]
name = "budget"

[agent]
model = "claude-haiku-4-5"
max_turns = 10

[comb]
theme = "terminal-dark"
cells = [
  { type = "log",     title = "Live Log",      source = "logs/out.log" },
  { type = "markdown",title = "Weekly Summary",source = "memory/weekly.md" },
  { type = "metric",  title = "Tasks Today",   source = "memory/stats.json",  key = "tasks_today" },
  { type = "status",  title = "Health",        source = "memory/health.json", key = "status" },
  { type = "table",   title = "Recent Tasks",  source = "memory/tasks.json" },
  { type = "chart",   title = "Daily Activity",source = "memory/activity.json" },
  { type = "app",     title = "Browse Transactions", source = "dashboard/browse_app.py" },
]
```
