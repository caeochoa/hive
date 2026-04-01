import asyncio
import atexit
import logging
import socket
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from hive.comb.cells import (
    CellRenderError,
    render_chart_cell,
    render_file_cell,
    render_markdown_cell,
    render_metric_cell,
    render_status_cell,
    render_table_cell,
    resolve_latest_in_dir,
    tail_log_file,
)
from hive.shared.config import WorkerConfig, load_worker_config
from hive.shared.registry import HiveRegistry

PORT_FILE = Path.home() / ".config" / "hive" / "comb.port"


def _find_free_port(start: int = 8080) -> int:
    port = start
    while True:
        with socket.socket() as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                port += 1

logger = logging.getLogger(__name__)

_worker_cache: dict[str, WorkerConfig] = {}
_worker_cache_time: float = 0.0
_WORKER_CACHE_TTL: float = 5.0

def _load_workers() -> dict[str, WorkerConfig]:
    global _worker_cache, _worker_cache_time
    now = time.monotonic()
    if now - _worker_cache_time < _WORKER_CACHE_TTL and _worker_cache:
        return _worker_cache
    registry = HiveRegistry()
    workers = {}
    for entry in registry.list_workers():
        try:
            cfg = load_worker_config(Path(entry.path))
            workers[cfg.name] = cfg
        except Exception:
            logger.warning("Failed to load config for %s", entry.name, exc_info=True)
    _worker_cache = workers
    _worker_cache_time = now
    return workers

app = FastAPI(title="Hive Comb", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    workers = _load_workers()
    return templates.TemplateResponse(request, "index.html", {"workers": sorted(workers.keys())})

@app.get("/workers/{name}", response_class=HTMLResponse)
async def worker_dashboard(request: Request, name: str):
    workers = _load_workers()
    if name not in workers:
        raise HTTPException(404, f"Worker '{name}' not found")
    cfg = workers[name]
    cell_types = [c.type for c in cfg.comb_cells]
    return templates.TemplateResponse(request, "worker.html", {
        "name": name, "cells": cfg.comb_cells, "cell_types": cell_types,
        "theme": cfg.comb_theme,
    })

@app.get("/workers/{name}/cells/{i}")
async def get_cell(name: str, i: int):
    workers = _load_workers()
    if name not in workers:
        raise HTTPException(404)
    cfg = workers[name]
    if i < 0 or i >= len(cfg.comb_cells):
        raise HTTPException(404, "Cell index out of range")
    cell = cfg.comb_cells[i]
    source = cfg.worker_dir / cell.source
    subtitle = None
    is_markdown = False
    try:
        if cell.type == "file":
            resolved = resolve_latest_in_dir(source)
            subtitle = resolved.name if resolved != source else None
            if resolved.suffix == ".md":
                content = render_markdown_cell(resolved)
                is_markdown = True
            else:
                content = render_file_cell(resolved)
        elif cell.type == "metric":
            content = render_metric_cell(source, cell.key)
        elif cell.type == "log":
            lines = tail_log_file(source)
            content = "\n".join(lines)
        elif cell.type == "status":
            content = render_status_cell(source, cell.key)
        elif cell.type == "table":
            content = render_table_cell(source)
        elif cell.type == "chart":
            content = render_chart_cell(source, cell.key)
        else:
            raise HTTPException(400, f"Unknown cell type: {cell.type}")
    except CellRenderError as e:
        logger.error("Cell render error [worker=%s cell=%d]: %s", name, i, e)
        raise HTTPException(500, str(e))
    except Exception:
        logger.exception("Unexpected error rendering cell [worker=%s cell=%d]", name, i)
        raise
    return JSONResponse({
        "content": content, "title": cell.title, "type": cell.type,
        "subtitle": subtitle, "is_markdown": is_markdown,
    })

@app.get("/workers/{name}/cells/{i}/stream")
async def stream_cell(name: str, i: int):
    workers = _load_workers()
    if name not in workers:
        raise HTTPException(404)
    cfg = workers[name]
    if i < 0 or i >= len(cfg.comb_cells):
        raise HTTPException(404)
    cell = cfg.comb_cells[i]
    if cell.type != "log":
        raise HTTPException(400, "SSE streaming only for log cells")
    source = cfg.worker_dir / cell.source
    return StreamingResponse(_sse_log_generator(source), media_type="text/event-stream")

async def _sse_log_generator(log_path: Path):
    """Async generator: open file, seek to end, yield SSE events as new lines appear."""
    try:
        if not log_path.exists():
            yield "data: (waiting for log file...)\n\n"
            while not log_path.exists():
                await asyncio.sleep(1)

        with open(log_path) as f:
            f.seek(0, 2)  # Seek to end
            while True:
                line = f.readline()
                if line:
                    yield f"data: {line.rstrip()}\n\n"
                else:
                    await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("SSE stream error for %s", log_path)

def serve(host: str = "127.0.0.1", port: int | None = None) -> None:
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    resolved = _find_free_port(port if port is not None else 8080)
    PORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    PORT_FILE.write_text(str(resolved))
    atexit.register(lambda: PORT_FILE.unlink(missing_ok=True))
    uvicorn.run(app, host=host, port=resolved)
