"""Tests for the web setup endpoints (/setup, /api/config, /api/config/test)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from task_summoner.api.setup import create_setup_router


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    app = FastAPI()
    app.include_router(create_setup_router(tmp_path / "config.yaml"))
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _valid_payload() -> dict:
    return {
        "board_type": "linear",
        "board_config": {
            "api_key": "k",
            "team_id": "team-uuid",
            "watch_label": "task-summoner",
        },
        "agent_type": "claude_code",
        "agent_config": {
            "api_key": "ak",
            "plugin_mode": "installed",
        },
        "repos": {"demo": "/tmp/demo"},
        "default_repo": "demo",
        "polling_interval_sec": 12,
        "workspace_root": "/tmp/ws",
    }


class TestSetupPage:
    def test_returns_html(self, client: TestClient):
        response = client.get("/setup")
        assert response.status_code == 200
        assert "Task Summoner" in response.text
        assert "<form" in response.text


class TestConfigTest:
    def test_valid_config_returns_ok(self, client: TestClient):
        response = client.post("/api/config/test", json=_valid_payload())
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True

    def test_invalid_board_type_returns_not_ok(self, client: TestClient):
        payload = _valid_payload()
        payload["board_type"] = "trello"
        response = client.post("/api/config/test", json=payload)
        body = response.json()
        assert body["ok"] is False


class TestConfigSave:
    def test_writes_yaml_file(self, client: TestClient, tmp_path: Path):
        response = client.post("/api/config", json=_valid_payload())
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True

        config_path = tmp_path / "config.yaml"
        assert config_path.exists()
        written = yaml.safe_load(config_path.read_text())
        assert written["providers"]["board"]["type"] == "linear"
        assert written["providers"]["agent"]["type"] == "claude_code"
        assert written["default_repo"] == "demo"
        assert written["polling_interval_sec"] == 12

    def test_rejects_invalid_payload(self, client: TestClient):
        payload = _valid_payload()
        payload["board_type"] = "nope"
        response = client.post("/api/config", json=payload)
        assert response.status_code == 400
