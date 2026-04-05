from unittest.mock import patch

from fastapi.testclient import TestClient

from hive.comb.server import app

client = TestClient(app, follow_redirects=False)


def test_index_lists_workers():
    with patch("hive.comb.server._get_workers", return_value={"budget": 8501, "news": 8502}):
        resp = client.get("/")
    assert resp.status_code == 200
    assert "budget" in resp.text
    assert "news" in resp.text


def test_index_empty():
    with patch("hive.comb.server._get_workers", return_value={}):
        resp = client.get("/")
    assert resp.status_code == 200


def test_worker_redirect():
    with patch("hive.comb.server._get_workers", return_value={"budget": 8501}):
        resp = client.get("/workers/budget")
    assert resp.status_code == 302
    assert resp.headers["location"] == "http://localhost:8501"


def test_worker_redirect_not_found():
    with patch("hive.comb.server._get_workers", return_value={}):
        resp = client.get("/workers/missing")
    assert resp.status_code == 404


def test_worker_redirect_no_port():
    with patch("hive.comb.server._get_workers", return_value={"budget": None}):
        resp = client.get("/workers/budget")
    assert resp.status_code == 503
