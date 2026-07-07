import json
import pytest
from pathlib import Path
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport

from hive.shared.config import WorkerConfig
from hive.shared.models import CombCell
from hive.comb.server import app


def _make_config(tmp_path: Path) -> WorkerConfig:
    (tmp_path / "stats.json").write_text(json.dumps({"count": 42}))
    (tmp_path / "health.json").write_text(json.dumps({"status": "ok"}))
    (tmp_path / "notes.md").write_text("# Hello\nworld")
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "out.log").write_text("line1\nline2\n")
    return WorkerConfig(
        name="budget",
        worker_dir=tmp_path,
        telegram_bot_token="tok",
        telegram_allowed_user_ids=[1],
        comb_cells=[
            CombCell(type="metric", title="Count", source="stats.json", key="count"),
            CombCell(type="status", title="Health", source="health.json", key="status"),
            CombCell(type="markdown", title="Notes", source="notes.md"),
            CombCell(type="log", title="Log", source="logs/out.log"),
        ],
        comb_theme="terminal-dark",
    )


@pytest.fixture
def mock_workers(tmp_path):
    cfg = _make_config(tmp_path)
    with patch("hive.comb.server._load_workers", return_value={"budget": cfg}):
        yield cfg


@pytest.mark.asyncio
async def test_api_list_workers(mock_workers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/workers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "budget"
    assert data[0]["theme"] == "terminal-dark"
    assert data[0]["cell_count"] == 4


@pytest.mark.asyncio
async def test_api_worker_detail(mock_workers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/workers/budget")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "budget"
    assert len(data["cells"]) == 4
    assert data["cells"][0] == {"index": 0, "type": "metric", "title": "Count", "slug": None}


@pytest.mark.asyncio
async def test_api_worker_detail_not_found(mock_workers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/workers/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_cell_metric(mock_workers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/workers/budget/cells/0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "42"
    assert data["type"] == "metric"
    assert data["is_markdown"] is False


@pytest.mark.asyncio
async def test_api_cell_markdown_returns_raw_text(mock_workers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/workers/budget/cells/2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_markdown"] is True
    # Raw markdown text, NOT rendered HTML
    assert "<p>" not in data["content"]
    assert "# Hello" in data["content"]


@pytest.mark.asyncio
async def test_api_cell_index_out_of_range(mock_workers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/workers/budget/cells/99")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_worker_files_serves_file(mock_workers, tmp_path):
    # tmp_path is already the worker_dir with notes.md from _make_config
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/workers/budget/files/notes.md")
    assert resp.status_code == 200
    assert "Hello" in resp.text


@pytest.mark.asyncio
async def test_worker_files_rejects_path_traversal(mock_workers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/workers/budget/files/../../etc/passwd")
    # The ASGI layer normalizes `../../` away before the route handler sees it,
    # so the request never reaches the worker_static_file handler — it falls through to
    # the SPA fallback (200 with built dist, 503 without). Either way, /etc/passwd is
    # never served directly: verify the response body does not contain typical passwd content.
    assert "root:" not in resp.text


@pytest.mark.asyncio
async def test_spa_fallback_returns_503_when_no_dist(mock_workers):
    """SPA fallback returns 503 when frontend dist is not built."""
    from unittest.mock import patch as _patch
    import hive.comb.server as _server
    # Temporarily point _frontend_dist at a non-existent path to simulate no built dist
    nonexistent = Path("/tmp/nonexistent-hive-dist-xyz")
    with _patch.object(_server, "_frontend_dist", nonexistent):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/some-react-route")
    assert resp.status_code == 503
