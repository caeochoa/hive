import time
import asyncio
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from hive.shared.registry import HiveRegistry
from hive.shared.config import load_worker_config, WorkerConfig
from hive.comb.cells import render_file_cell, render_metric_cell, tail_log_file, CellRenderError

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
    try:
        if cell.type == "file":
            content = render_file_cell(source)
        elif cell.type == "metric":
            content = render_metric_cell(source, cell.key)
        elif cell.type == "log":
            lines = tail_log_file(source)
            content = "\n".join(lines)
        else:
            raise HTTPException(400, f"Unknown cell type: {cell.type}")
    except CellRenderError as e:
        raise HTTPException(500, str(e))
    return JSONResponse({"content": content, "title": cell.title, "type": cell.type})

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

        with open(log_path, "r") as f:
            f.seek(0, 2)  # Seek to end
            while True:
                line = f.readline()
                if line:
                    yield f"data: {line.rstrip()}\n\n"
                else:
                    await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        return

def serve(host: str = "127.0.0.1", port: int = 8080) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port)
