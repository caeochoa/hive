import atexit
import logging
import socket
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

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


def _get_workers() -> dict[str, int | None]:
    """Return {name: comb_port} for all registered workers."""
    registry = HiveRegistry()
    return {e.name: e.comb_port for e in registry.list_workers()}


app = FastAPI(title="Hive Comb", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    workers = _get_workers()
    return templates.TemplateResponse(request, "index.html", {"workers": workers})


@app.get("/workers/{name}")
async def worker_redirect(name: str):
    from fastapi.responses import RedirectResponse
    workers = _get_workers()
    if name not in workers:
        raise HTTPException(404, f"Worker '{name}' not found")
    port = workers[name]
    if port is None:
        raise HTTPException(503, f"Worker '{name}' has no dashboard running")
    return RedirectResponse(url=f"http://localhost:{port}", status_code=302)


def serve(host: str = "127.0.0.1", port: int | None = None) -> None:
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    resolved = _find_free_port(port if port is not None else 8080)
    PORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    PORT_FILE.write_text(str(resolved))
    atexit.register(lambda: PORT_FILE.unlink(missing_ok=True))
    uvicorn.run(app, host=host, port=resolved)
