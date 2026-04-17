"""Tests for the FastAPI app — lifespan state, routers, config endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from task_summoner.api.app import create_app
from task_summoner.core import StateStore
from task_summoner.models import TicketContext, TicketState


@pytest.fixture
def app_and_store(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    app = create_app(config_path=config_path)
    store = StateStore(str(tmp_path / "artifacts"))

    with TestClient(app) as client:
        app.state.store = store
        yield client, store


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


class TestRootAndStatic:
    def test_dashboard_returns_html(self, app_and_store):
        client, _ = app_and_store
        response = client.get("/")
        assert response.status_code == 200
        assert "<html" in response.text.lower() or "<!doctype" in response.text.lower()


class TestSetupPage:
    def test_setup_returns_html(self, app_and_store):
        client, _ = app_and_store
        response = client.get("/setup")
        assert response.status_code == 200
        assert "Task Summoner" in response.text


class TestConfigStatus:
    def test_unconfigured_state_reported(self, app_and_store):
        client, _ = app_and_store
        response = client.get("/api/config/status")
        assert response.status_code == 200
        body = response.json()
        assert body["configured"] is False
        assert isinstance(body["errors"], list)


class TestConfigTest:
    def test_valid_config_returns_ok(self, app_and_store):
        client, _ = app_and_store
        response = client.post("/api/config/test", json=_valid_payload())
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_invalid_board_type_returns_not_ok(self, app_and_store):
        client, _ = app_and_store
        payload = _valid_payload()
        payload["board_type"] = "trello"
        response = client.post("/api/config/test", json=payload)
        assert response.json()["ok"] is False


class TestConfigSave:
    def test_writes_yaml_file(self, app_and_store, tmp_path: Path):
        client, _ = app_and_store
        response = client.post("/api/config", json=_valid_payload())
        assert response.status_code == 200
        assert response.json()["ok"] is True

        written = yaml.safe_load((tmp_path / "config.yaml").read_text())
        assert written["providers"]["board"]["type"] == "linear"
        assert written["providers"]["agent"]["type"] == "claude_code"
        assert written["default_repo"] == "demo"
        assert written["polling_interval_sec"] == 12

    def test_rejects_invalid_payload(self, app_and_store):
        client, _ = app_and_store
        payload = _valid_payload()
        payload["board_type"] = "nope"
        response = client.post("/api/config", json=payload)
        assert response.status_code == 400


class TestTickets:
    def test_list_empty(self, app_and_store):
        client, _ = app_and_store
        response = client.get("/api/tickets")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_returns_saved(self, app_and_store):
        client, store = app_and_store
        store.save(TicketContext(ticket_key="ENG-1", state=TicketState.QUEUED))
        response = client.get("/api/tickets")
        assert response.status_code == 200
        keys = [t["ticket_key"] for t in response.json()]
        assert "ENG-1" in keys

    def test_get_single_ticket(self, app_and_store):
        client, store = app_and_store
        store.save(TicketContext(ticket_key="ENG-2", state=TicketState.PLANNING))
        response = client.get("/api/tickets/ENG-2")
        assert response.status_code == 200
        assert response.json()["ticket_key"] == "ENG-2"

    def test_missing_ticket_returns_404(self, app_and_store):
        client, _ = app_and_store
        response = client.get("/api/tickets/DOES-NOT-EXIST")
        assert response.status_code == 404


class TestEventHistory:
    def test_empty_history(self, app_and_store):
        client, _ = app_and_store
        response = client.get("/api/events/history")
        assert response.status_code == 200
        assert response.json() == []
