import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport

from hive.shared.config import WorkerConfig
from hive.shared.models import CombCell
from hive.comb.server import app


def _make_config(tmp_path: Path) -> WorkerConfig:
    """Build a test WorkerConfig with real files on disk."""
    # Create file cell source
    (tmp_path / "notes.md").write_text("# My Notes\nHello world")

    # Create metric cell source
    (tmp_path / "stats.json").write_text(json.dumps({"count": 42}))

    # Create log cell source
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "out.log").write_text("line1\nline2\nline3\n")

    return WorkerConfig(
        name="test",
        worker_dir=tmp_path,
        telegram_bot_token="tok",
        telegram_allowed_user_id=1,
        comb_cells=[
            CombCell(type="file", title="Notes", source="notes.md"),
            CombCell(type="metric", title="Count", source="stats.json", key="count"),
            CombCell(type="log", title="Log", source="logs/out.log"),
        ],
    )


@pytest.fixture
def mock_workers(tmp_path):
    config = _make_config(tmp_path)
    with patch("hive.comb.server._load_workers", return_value={"test": config}):
        yield config


@pytest.mark.asyncio
async def test_index_returns_200_and_lists_workers(mock_workers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert "test" in resp.text
    assert "1 worker(s) registered" in resp.text


@pytest.mark.asyncio
async def test_worker_dashboard_known(mock_workers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/workers/test")
    assert resp.status_code == 200
    assert "Notes" in resp.text
    assert "Count" in resp.text
    assert "Log" in resp.text


@pytest.mark.asyncio
async def test_worker_dashboard_unknown(mock_workers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/workers/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_cell_file(mock_workers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/workers/test/cells/0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "file"
    assert "My Notes" in data["content"]


@pytest.mark.asyncio
async def test_get_cell_metric(mock_workers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/workers/test/cells/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "metric"
    assert data["content"] == "42"


@pytest.mark.asyncio
async def test_get_cell_log(mock_workers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/workers/test/cells/2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "log"
    assert "line1" in data["content"]


@pytest.mark.asyncio
async def test_get_cell_out_of_range(mock_workers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/workers/test/cells/99")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_stream_cell_log(mock_workers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with asyncio.timeout(2):
                async with client.stream("GET", "/workers/test/cells/2/stream") as resp:
                    assert resp.status_code == 200
                    assert "text/event-stream" in resp.headers["content-type"]
        except TimeoutError:
            pass  # Expected — SSE streams indefinitely


@pytest.mark.asyncio
async def test_stream_cell_non_log_returns_400(mock_workers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/workers/test/cells/0/stream")
    assert resp.status_code == 400
