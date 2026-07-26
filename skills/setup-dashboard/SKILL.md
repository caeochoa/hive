---
name: setup-dashboard
description: "Configure the Comb web dashboard for an existing Hive Worker. Reads what files the Worker produces, recommends the right cell types, and writes the [comb] section in hive.toml. Can also scaffold app cells with a FastAPI router. Use when: setup dashboard, add dashboard, configure comb, add comb cells, I want a dashboard, show worker data, visualise worker, add chart, add metrics."
---

# Set Up a Comb Dashboard

You are configuring a Comb dashboard for an existing Hive Worker. Comb serves all Worker dashboards from a single web server at `http://localhost:8080/workers/<name>`. Dashboards are config-driven — no custom code required unless using `app` cells.

Your job is to read what data the Worker produces, then configure the right cells.

## How Comb cells work (essential context)

Cells are defined in `hive.toml` under `[comb]`:

```toml
[comb]
theme = "terminal-dark"   # optional, defaults to "terminal-dark"
cells = [
  { type = "...", title = "...", source = "..." },
]
```

`source` is always relative to the Worker folder.

### Cell types

| Type | What it shows | Source | Extra fields |
|---|---|---|---|
| `log` | Live log tail via SSE | append-only log file | — |
| `file` | Plain text (`.md` auto-renders as HTML) | file or directory | — |
| `markdown` | Markdown rendered as HTML | file or directory | — |
| `metric` | Single value from a JSON object | JSON file | `key` (required) |
| `status` | Like metric with semantic coloring | JSON file | `key` (required) |
| `table` | JSON array of objects as HTML table | JSON array file | — |
| `chart` | Numeric data as a chart | JSON file | `key` (optional) |
| `app` | Full-page FastAPI app (opens in new view) | Python file with `make_app()`, `make_router()`, or `router` | — |

**`status` color mapping** (case-insensitive):
- Green: `ok`, `success`, `pass`, `true`, `running`, `1`
- Yellow: `warn`, `warning`, `degraded`
- Red: `error`, `fail`, `failed`, `false`, `stopped`, `down`, `0`

**Directory source behavior** (`file` / `markdown`): if `source` is a directory, Comb automatically picks the most recently modified file in it. Useful when the agent writes rotating or timestamped files.

**`chart` input formats:**
- Array of numbers: `[4, 7, 2, 9]`
- Labeled values: `[{"label": "Mon", "value": 4}, ...]`
- JSON object with a `key` pointing to either of the above

**`app` cells:** Render as a card with an **Open** button. The `source` file must export one of:
- `make_app(worker_dir: Path) -> FastAPI` — a full app, for when you need static assets (e.g. a built React frontend), middleware, or exception handlers alongside API routes.
- `make_router(worker_dir: Path) -> APIRouter` (preferred for simple interactivity) — no static/middleware capability of its own.
- a bare `router: APIRouter`.

Apps are mounted at `/workers/{name}/apps/{slug}` where slug is the title lowercased with spaces replaced by hyphens. Only packages in the Hive environment (not the Worker's `.venv`) are available — `make_app`/`make_router` code always runs inside the shared Comb process.

## Step 1: Read the Worker

Before recommending cells, understand what the Worker produces:

1. Read `hive.toml` — Worker name, agent config, existing `[comb]` section if any
2. List `memory/` — what JSON, markdown, and text files exist or are written
3. List `logs/` — confirm `logs/out.log` exists
4. List `dashboard/` — any existing app files
5. Read a few key memory files to understand their structure (flat JSON object? array? markdown?)

This tells you which cell types are appropriate for which files.

## Step 2: Recommend cells

Based on what you found, propose a complete `[comb]` configuration. Match each file to the most appropriate cell type:

- `logs/out.log` → `log` (always a good first cell)
- Markdown summaries/reports → `markdown`
- JSON with scalar values → `metric` or `status` (use `status` for health/state fields)
- JSON arrays of objects → `table` or `chart` (table for records, chart for time-series numeric data)
- Plain text notes → `file`
- Complex interactive views → `app` (only if the user needs interactivity or richer UI)

If the user mentions wanting something interactive (search, filter, form submission, custom layout) or if a table/chart doesn't give enough control, suggest an `app` cell.

Ask the user to confirm the proposed cells before writing, especially if the Worker has many files and the right choices aren't obvious.

## Step 3: Write the `[comb]` section

Update `hive.toml` with the confirmed cells. If a `[comb]` section already exists, update it in place.

## Step 4: Scaffold `app` cells (if needed)

If the user wants an `app` cell, first ask which of these three cases applies — they need different scaffolding:

**A. Simple interactivity (no static assets/frontend build needed).** Create `dashboard/<name>.py` with a `make_router()` function:

```python
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pathlib import Path

def make_router(worker_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/")
    async def index():
        # Read Worker files via worker_dir
        data = (worker_dir / "memory" / "data.json").read_text()
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html><body>
          <h1>Title</h1>
          <pre>{data}</pre>
        </body></html>
        """)

    return router
```

The router has access to the full FastAPI ecosystem: `Request`, `Form`, `HTMLResponse`, `JSONResponse`, `Jinja2Templates`, and so on. For POST routes or forms, add the appropriate FastAPI imports.

The app's sub-routes (e.g. `/api/data`, `/submit`) are available under the `/workers/{name}/apps/{slug}/` prefix automatically.

**B. A JS-framework frontend (React/Vue/etc.) with or without its own API.** Create `dashboard/<name>.py` with a `make_app()` function that mounts the frontend's build output as static files:

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

def make_app(worker_dir: Path) -> FastAPI:
    app = FastAPI()

    @app.get("/api/data")
    async def data():
        return {"items": [...]}  # read from worker_dir as needed

    # Mount last — matches anything not already handled by a route above.
    app.mount("/", StaticFiles(directory=worker_dir / "dashboard" / "frontend" / "dist", html=True))
    return app
```

Tell the user they need to build the frontend (`npm install && npm run build`, or equivalent) so `dashboard/frontend/dist` exists before `hive comb restart` will serve it. This won't work until that build step has run.

**C. Wrapping an existing standalone app the user already has** (e.g. turning an existing project with its own FastAPI dashboard into a Worker's app cell). Scaffold a thin wrapper around their existing app factory:

```python
from my_existing_project.web import create_app  # adjust to the real module/function

def make_app(worker_dir):
    return create_app(worker_dir / "data" / "app.db", worker_dir / "config.json")  # adjust args
```

Before doing this, walk the user through:
1. Add the external package to **Hive's own project** (e.g. `uv add --editable ../path-to-project` run from the Hive repo) — not the Worker's `.venv`. `make_app` code always runs inside Hive's shared Comb process.
2. Check that the package's own `fastapi`/`pydantic` (and any other shared-surface dependency) version requirements are compatible with Hive's pins — this isn't validated automatically and a conflict will only surface as an import error at Comb startup.
3. Point the import at the module that makes up the app's *web surface* only (e.g. its `web.py`), not the top-level package — so unrelated heavier dependencies used elsewhere in that project (a scraper, a CLI, etc.) aren't pulled into Hive's environment as transitive requirements.

## Step 5: Apply changes

After writing the config (and any app files):

1. Restart Comb to pick up the new cells:
   ```bash
   hive comb restart
   ```
2. Tell the user where to find the dashboard:
   ```
   http://localhost:8080/workers/<name>
   ```
3. Note that `app` cells specifically require `hive comb restart` — other cell types are polled live and don't need a restart.

## Important guidelines

- **Only add cells for data that actually exists or will exist.** Don't create placeholder cells for files the Worker doesn't produce yet.
- **Prefer simple cell types.** A `metric` or `table` is almost always sufficient. Only reach for `app` when interactivity or custom layout is genuinely needed.
- **Keep titles short and clear.** They appear as card headers in the dashboard.
- **For `status` cells, confirm the JSON value matches the expected color mapping.** If the Worker writes `"healthy"` instead of `"ok"`, the cell will render neutral — tell the user.
