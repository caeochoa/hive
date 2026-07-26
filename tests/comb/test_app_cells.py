from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from hive.comb.server import _load_app_router, _mount_worker_apps, app
from hive.shared.config import WorkerConfig
from hive.shared.models import CombCell

ROUTER_SOURCE = '''
from fastapi import APIRouter

router = APIRouter()


@router.get("/ping")
def ping():
    return {"ok": "router"}
'''

MAKE_APP_SOURCE = '''
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def make_app(worker_dir):
    sub_app = FastAPI()
    sub_app.mount(
        "/static",
        StaticFiles(directory=str(worker_dir / "static_assets")),
        name="static",
    )

    @sub_app.get("/api/ping")
    def ping():
        return {"ok": "app"}

    return sub_app
'''

NO_EXPORT_SOURCE = "x = 1\n"


def _make_config(tmp_path: Path, worker_name: str, cells: list[CombCell]) -> WorkerConfig:
    return WorkerConfig(
        name=worker_name,
        worker_dir=tmp_path,
        telegram_bot_token="tok",
        telegram_allowed_user_ids=[1],
        comb_cells=cells,
    )


@pytest.mark.asyncio
async def test_make_router_app_cell_mounts_router(tmp_path):
    (tmp_path / "router_app.py").write_text(ROUTER_SOURCE)
    config = _make_config(
        tmp_path,
        "router-worker",
        [CombCell(type="app", title="Router App", source="router_app.py")],
    )
    with patch("hive.comb.server._load_workers", return_value={"router-worker": config}):
        _mount_worker_apps()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/workers/router-worker/apps/router-app/ping")
    assert resp.status_code == 200
    assert resp.json() == {"ok": "router"}


@pytest.mark.asyncio
async def test_make_app_app_cell_mounts_full_fastapi_app(tmp_path):
    (tmp_path / "app_app.py").write_text(MAKE_APP_SOURCE)
    static_dir = tmp_path / "static_assets"
    static_dir.mkdir()
    (static_dir / "hello.txt").write_text("hello from static")

    config = _make_config(
        tmp_path,
        "make-app-worker",
        [CombCell(type="app", title="Make App App", source="app_app.py")],
    )
    with patch("hive.comb.server._load_workers", return_value={"make-app-worker": config}):
        _mount_worker_apps()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        api_resp = await client.get("/workers/make-app-worker/apps/make-app-app/api/ping")
        static_resp = await client.get(
            "/workers/make-app-worker/apps/make-app-app/static/hello.txt"
        )

    assert api_resp.status_code == 200
    assert api_resp.json() == {"ok": "app"}
    assert static_resp.status_code == 200
    assert static_resp.text == "hello from static"


def test_load_app_router_requires_a_known_export(tmp_path):
    source = tmp_path / "no_export.py"
    source.write_text(NO_EXPORT_SOURCE)

    with pytest.raises(AttributeError, match="router.*make_router.*make_app"):
        _load_app_router(source, tmp_path, "some-worker")
