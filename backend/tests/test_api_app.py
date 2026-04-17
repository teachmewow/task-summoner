"""Tests for the FastAPI app — lifespan state, routers, config endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from task_summoner.api import app as app_module
from task_summoner.api.app import create_app
from task_summoner.core import StateStore
from task_summoner.models import CostEntry, TicketContext, TicketState


@pytest.fixture
def app_and_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(app_module, "_WEB_DIST", tmp_path / "no_web_dist")
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


class TestSpaFallback:
    def test_root_returns_503_when_bundle_missing(self, app_and_store):
        client, _ = app_and_store
        response = client.get("/")
        assert response.status_code == 503
        assert "pnpm build" in response.json()["detail"]

    def test_api_404_still_json(self, app_and_store):
        client, _ = app_and_store
        response = client.get("/api/does-not-exist")
        assert response.status_code == 404


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


class TestCostSummary:
    def test_empty_store_returns_zeros(self, app_and_store):
        client, _ = app_and_store
        response = client.get("/api/cost/summary")
        assert response.status_code == 200
        body = response.json()
        assert body["total_cost_usd"] == 0.0
        assert body["ticket_count"] == 0
        assert body["run_count"] == 0
        assert body["by_profile"] == []
        assert body["by_ticket"] == []
        assert body["budget"]["monthly_budget_usd"] is None

    def test_aggregates_across_tickets(self, app_and_store):
        client, store = app_and_store
        store.save(
            TicketContext(
                ticket_key="ENG-1",
                state=TicketState.DONE,
                total_cost_usd=3.0,
                cost_history=[
                    CostEntry(cost_usd=1.0, turns=12, profile="standard", state="PLANNING"),
                    CostEntry(cost_usd=2.0, turns=55, profile="heavy", state="IMPLEMENTING"),
                ],
            )
        )
        store.save(
            TicketContext(
                ticket_key="ENG-2",
                state=TicketState.PLANNING,
                total_cost_usd=0.5,
                cost_history=[
                    CostEntry(cost_usd=0.5, turns=3, profile="doc_checker", state="CHECKING_DOC"),
                ],
            )
        )
        body = client.get("/api/cost/summary").json()

        assert body["total_cost_usd"] == 3.5
        assert body["ticket_count"] == 2
        assert body["run_count"] == 3
        profiles = {p["profile"]: p for p in body["by_profile"]}
        assert profiles["heavy"]["cost_usd"] == 2.0
        assert profiles["standard"]["turns"] == 12
        assert profiles["doc_checker"]["runs"] == 1
        tickets = [t["ticket_key"] for t in body["by_ticket"]]
        assert tickets[0] == "ENG-1"
        buckets = {b["bucket"]: b["count"] for b in body["turns_histogram"]}
        assert buckets["0-9"] >= 1
        assert buckets["50-199"] >= 1


class TestReloadOnSave:
    """POST /api/config should trigger reload_orchestrator and flip configured → True."""

    def test_reload_flips_configured_flag(self, app_and_store, tmp_path: Path):
        client, _ = app_and_store

        initial = client.get("/api/config/status").json()
        assert initial["configured"] is False

        repo_dir = tmp_path / "demo_repo"
        repo_dir.mkdir()
        payload = _valid_payload()
        payload["repos"] = {"demo": str(repo_dir)}
        payload["agent_config"] = {
            "auth_method": "api_key",
            "api_key": "ak",
            "plugin_mode": "installed",
        }

        response = client.post("/api/config", json=payload)
        assert response.status_code == 200, response.text

        final = client.get("/api/config/status").json()
        assert final["configured"] is True
        assert final["errors"] == []
