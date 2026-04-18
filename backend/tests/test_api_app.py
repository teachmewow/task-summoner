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


class TestFailureSummary:
    def test_empty_store(self, app_and_store):
        client, _ = app_and_store
        body = client.get("/api/failures/summary").json()
        assert body["total_failed"] == 0
        assert body["quarantined"] == 0
        assert body["healthy"] == 0
        assert body["tickets"] == []

    def test_categorizes_and_aggregates(self, app_and_store):
        client, store = app_and_store
        store.save(
            TicketContext(
                ticket_key="ENG-201",
                state=TicketState.FAILED,
                error="Not reachable on board: Linear issue not found",
                cost_history=[
                    CostEntry(cost_usd=0.0, turns=0, profile="standard", state="CHECKING_DOC")
                ],
            )
        )
        store.save(
            TicketContext(
                ticket_key="ENG-202",
                state=TicketState.FAILED,
                error="Agent timed out after 200 turns",
                cost_history=[
                    CostEntry(cost_usd=3.0, turns=200, profile="heavy", state="IMPLEMENTING")
                ],
            )
        )
        store.save(TicketContext(ticket_key="ENG-203", state=TicketState.DONE))

        body = client.get("/api/failures/summary").json()
        assert body["total_failed"] == 2
        assert body["quarantined"] == 1
        assert body["healthy"] == 1

        categories = {c["category"]: c["count"] for c in body["by_category"]}
        assert categories["board_not_found"] == 1
        assert categories["timeout"] == 1

        phases = {p["phase"]: p["count"] for p in body["by_phase"]}
        assert phases["CHECKING_DOC"] == 1
        assert phases["IMPLEMENTING"] == 1

        keys = {t["ticket_key"]: t for t in body["tickets"]}
        assert keys["ENG-201"]["quarantined"] is True
        assert keys["ENG-202"]["quarantined"] is False

    def test_retry_requeues_failed_ticket(self, app_and_store):
        client, store = app_and_store
        store.save(
            TicketContext(
                ticket_key="ENG-210",
                state=TicketState.FAILED,
                error="Whatever",
                retry_count=3,
            )
        )
        response = client.post("/api/failures/ENG-210/retry")
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["new_state"] == "QUEUED"

        reloaded = store.load("ENG-210")
        assert reloaded is not None
        assert reloaded.state == TicketState.QUEUED
        assert reloaded.error is None
        assert reloaded.retry_count == 0

    def test_retry_rejects_non_failed(self, app_and_store):
        client, store = app_and_store
        store.save(TicketContext(ticket_key="ENG-211", state=TicketState.PLANNING))
        response = client.post("/api/failures/ENG-211/retry")
        assert response.status_code == 400

    def test_retry_missing_ticket_is_404(self, app_and_store):
        client, _ = app_and_store
        response = client.post("/api/failures/NOPE-999/retry")
        assert response.status_code == 404


class TestAgentProfiles:
    def _write_valid_config(self, client, tmp_path: Path) -> None:
        repo = tmp_path / "r"
        repo.mkdir()
        payload = {
            "board_type": "linear",
            "board_config": {
                "api_key": "k",
                "team_id": "team",
                "watch_label": "task-summoner",
            },
            "agent_type": "claude_code",
            "agent_config": {
                "auth_method": "api_key",
                "api_key": "ak",
                "plugin_mode": "installed",
            },
            "repos": {"demo": str(repo)},
            "default_repo": "demo",
            "polling_interval_sec": 10,
            "workspace_root": str(tmp_path / "ws"),
        }
        r = client.post("/api/config", json=payload)
        assert r.status_code == 200, r.text

    def test_list_requires_config(self, app_and_store):
        client, _ = app_and_store
        response = client.get("/api/agent-profiles")
        assert response.status_code == 409

    def test_list_returns_three_profiles(self, app_and_store, tmp_path: Path):
        client, _ = app_and_store
        self._write_valid_config(client, tmp_path)
        body = client.get("/api/agent-profiles").json()
        assert body["agent_provider"] == "claude_code"
        assert "sonnet" in body["available_models"]
        names = {p["name"] for p in body["profiles"]}
        assert names == {"doc_checker", "standard", "heavy"}

    def test_save_persists_and_reloads(self, app_and_store, tmp_path: Path):
        client, _ = app_and_store
        self._write_valid_config(client, tmp_path)
        payload = {
            "model": "opus",
            "max_turns": 300,
            "max_budget_usd": 60.0,
            "tools": ["Read", "Bash"],
            "enabled": True,
        }
        response = client.post("/api/agent-profiles/heavy", json=payload)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["ok"] is True
        assert body["profile"]["model"] == "opus"
        assert body["profile"]["max_turns"] == 300

        reloaded = client.get("/api/agent-profiles").json()
        heavy = next(p for p in reloaded["profiles"] if p["name"] == "heavy")
        assert heavy["model"] == "opus"
        assert heavy["max_turns"] == 300
        assert heavy["tools"] == ["Read", "Bash"]

    def test_save_unknown_profile_is_404(self, app_and_store, tmp_path: Path):
        client, _ = app_and_store
        self._write_valid_config(client, tmp_path)
        r = client.post(
            "/api/agent-profiles/nope",
            json={
                "model": "sonnet",
                "max_turns": 10,
                "max_budget_usd": 1,
                "tools": [],
            },
        )
        assert r.status_code == 404

    def test_save_rejects_unknown_model(self, app_and_store, tmp_path: Path):
        client, _ = app_and_store
        self._write_valid_config(client, tmp_path)
        r = client.post(
            "/api/agent-profiles/standard",
            json={
                "model": "gpt-4o",
                "max_turns": 10,
                "max_budget_usd": 1,
                "tools": [],
            },
        )
        assert r.status_code == 400


class TestSkills:
    def _write_config_and_plugin(self, client, tmp_path: Path) -> Path:
        plugin = tmp_path / "task-summoner-workflows"
        (plugin / "skills" / "alpha").mkdir(parents=True)
        (plugin / "skills" / "alpha" / "SKILL.md").write_text(
            '---\nname: alpha\ndescription: "Alpha skill"\nuser-invocable: true\n---\n\n# Alpha\n\nBody.\n'
        )
        (plugin / "skills" / "beta").mkdir(parents=True)
        (plugin / "skills" / "beta" / "SKILL.md").write_text(
            '---\nname: beta\ndescription: "Beta skill"\nuser-invocable: false\n---\n\n# Beta\n'
        )
        repo = tmp_path / "r"
        repo.mkdir()
        r = client.post(
            "/api/config",
            json={
                "board_type": "linear",
                "board_config": {
                    "api_key": "k",
                    "team_id": "team",
                    "watch_label": "task-summoner",
                },
                "agent_type": "claude_code",
                "agent_config": {
                    "auth_method": "api_key",
                    "api_key": "ak",
                    "plugin_mode": "local",
                    "plugin_path": str(plugin),
                },
                "repos": {"demo": str(repo)},
                "default_repo": "demo",
                "polling_interval_sec": 10,
                "workspace_root": str(tmp_path / "ws"),
            },
        )
        assert r.status_code == 200, r.text
        return plugin

    def test_list_returns_skills_with_metadata(self, app_and_store, tmp_path: Path):
        client, _ = app_and_store
        self._write_config_and_plugin(client, tmp_path)
        body = client.get("/api/skills").json()
        assert body["editable"] is True
        names = {s["name"] for s in body["skills"]}
        assert names == {"alpha", "beta"}
        alpha = next(s for s in body["skills"] if s["name"] == "alpha")
        assert alpha["description"] == "Alpha skill"
        assert alpha["user_invocable"] is True

    def test_get_returns_content(self, app_and_store, tmp_path: Path):
        client, _ = app_and_store
        self._write_config_and_plugin(client, tmp_path)
        body = client.get("/api/skills/alpha").json()
        assert body["name"] == "alpha"
        assert "# Alpha" in body["content"]

    def test_put_writes_content(self, app_and_store, tmp_path: Path):
        client, _ = app_and_store
        plugin = self._write_config_and_plugin(client, tmp_path)
        new_content = '---\nname: alpha\ndescription: "Updated alpha"\nuser-invocable: true\n---\n\n# Alpha v2\n'
        r = client.put("/api/skills/alpha", json={"content": new_content})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["skill"]["description"] == "Updated alpha"
        assert (plugin / "skills" / "alpha" / "SKILL.md").read_text() == new_content

    def test_unknown_skill_is_404(self, app_and_store, tmp_path: Path):
        client, _ = app_and_store
        self._write_config_and_plugin(client, tmp_path)
        assert client.get("/api/skills/nope").status_code == 404
        assert client.put("/api/skills/nope", json={"content": "anything"}).status_code == 404

    def test_rejects_hidden_names(self, app_and_store, tmp_path: Path):
        client, _ = app_and_store
        self._write_config_and_plugin(client, tmp_path)
        # Dot-prefixed names are rejected — prevents reaching e.g. `.git`.
        assert client.get("/api/skills/.git").status_code == 400
        assert client.put("/api/skills/.git", json={"content": "x"}).status_code == 400

    def test_installed_mode_is_read_only(self, app_and_store, tmp_path: Path):
        client, _ = app_and_store
        repo = tmp_path / "r"
        repo.mkdir()
        r = client.post(
            "/api/config",
            json={
                "board_type": "linear",
                "board_config": {
                    "api_key": "k",
                    "team_id": "team",
                    "watch_label": "task-summoner",
                },
                "agent_type": "claude_code",
                "agent_config": {
                    "auth_method": "api_key",
                    "api_key": "ak",
                    "plugin_mode": "installed",
                },
                "repos": {"demo": str(repo)},
                "default_repo": "demo",
                "polling_interval_sec": 10,
                "workspace_root": str(tmp_path / "ws"),
            },
        )
        assert r.status_code == 200, r.text
        body = client.get("/api/skills").json()
        assert body["editable"] is False
        assert body["reason"]


class TestWorkflow:
    def test_nodes_cover_every_state(self, app_and_store):
        client, _ = app_and_store
        body = client.get("/api/workflow").json()
        ids = {n["id"] for n in body["nodes"]}
        assert {"QUEUED", "DONE", "FAILED", "PLANNING", "IMPLEMENTING"} <= ids
        # Node kinds are derived from the frozensets in state_machine.
        kinds = {n["id"]: n["kind"] for n in body["nodes"]}
        assert kinds["QUEUED"] == "start"
        assert kinds["DONE"] == "terminal"
        assert kinds["FAILED"] == "terminal"
        assert kinds["PLANNING"] == "agent"
        assert kinds["WAITING_PLAN_REVIEW"] == "approval"

    def test_every_edge_has_a_known_source_and_target(self, app_and_store):
        client, _ = app_and_store
        body = client.get("/api/workflow").json()
        node_ids = {n["id"] for n in body["nodes"]}
        for edge in body["edges"]:
            assert edge["source"] in node_ids
            assert edge["target"] in node_ids
            assert edge["trigger"]

    def test_live_counts_reflect_store(self, app_and_store):
        client, store = app_and_store
        store.save(TicketContext(ticket_key="ENG-1", state=TicketState.PLANNING))
        store.save(TicketContext(ticket_key="ENG-2", state=TicketState.PLANNING))
        store.save(TicketContext(ticket_key="ENG-3", state=TicketState.DONE))
        body = client.get("/api/workflow/live").json()
        assert body["total_tickets"] == 3
        counts = {c["state"]: c["count"] for c in body["counts"]}
        assert counts["PLANNING"] == 2
        assert counts["DONE"] == 1


class TestHealth:
    def _write_config(self, client, tmp_path: Path) -> Path:
        repo = tmp_path / "r"
        repo.mkdir()
        r = client.post(
            "/api/config",
            json={
                "board_type": "linear",
                "board_config": {
                    "api_key": "k",
                    "team_id": "team-uuid",
                    "watch_label": "task-summoner",
                },
                "agent_type": "claude_code",
                "agent_config": {
                    "auth_method": "api_key",
                    "api_key": "ak",
                    "plugin_mode": "installed",
                },
                "repos": {"demo": str(repo)},
                "default_repo": "demo",
                "polling_interval_sec": 10,
                "workspace_root": str(tmp_path / "ws"),
            },
        )
        assert r.status_code == 200, r.text
        return repo

    def test_health_requires_config(self, app_and_store):
        client, _ = app_and_store
        assert client.get("/api/health").status_code == 409

    def test_health_reports_all_sections(self, app_and_store, tmp_path: Path):
        client, _ = app_and_store
        self._write_config(client, tmp_path)
        # After the config save, reload_orchestrator swaps in the orchestrator's
        # own store; write through that one so the health endpoint sees the rows.
        active = client.app.state.store  # type: ignore[attr-defined]
        active.save(TicketContext(ticket_key="ENG-1", state=TicketState.PLANNING))
        active.save(TicketContext(ticket_key="ENG-2", state=TicketState.DONE))
        active.save(TicketContext(ticket_key="ENG-3", state=TicketState.FAILED))

        body = client.get("/api/health").json()
        assert body["board"]["provider"] == "linear"
        assert body["board"]["watch_label"] == "task-summoner"
        assert body["agent"]["provider"] == "claude_code"
        assert body["agent"]["plugin_mode"] == "installed"
        assert body["local"]["total_tickets"] == 3
        assert body["local"]["terminal_tickets"] == 2
        assert body["local"]["active_tickets"] == 1
        assert "workspace_bytes" in body["local"]

    def test_clean_removes_unknown_tickets(
        self, app_and_store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from task_summoner.api.routers import health as health_router_module
        from task_summoner.providers.board import BoardNotFoundError

        client, _ = app_and_store
        self._write_config(client, tmp_path)
        store = client.app.state.store  # type: ignore[attr-defined]
        store.save(TicketContext(ticket_key="GONE-1", state=TicketState.FAILED))
        store.save(TicketContext(ticket_key="LIVE-1", state=TicketState.PLANNING))

        class StubBoard:
            async def fetch_ticket(self, key: str):
                if key == "GONE-1":
                    raise BoardNotFoundError(key)
                return None

        monkeypatch.setattr(
            health_router_module.BoardProviderFactory,
            "create",
            lambda _cfg: StubBoard(),
        )

        body = client.post("/api/health/clean").json()
        assert body["ok"] is True
        assert "GONE-1" in body["removed"]
        assert "LIVE-1" not in body["removed"]
        assert store.load("GONE-1") is None
        assert store.load("LIVE-1") is not None


class TestLinearTeamsLookup:
    def test_empty_key_is_rejected(self, app_and_store):
        client, _ = app_and_store
        body = client.post("/api/setup/linear-teams", json={"api_key": "  "}).json()
        assert body["ok"] is False
        assert "required" in body["message"].lower()
        assert body["teams"] == []

    def test_success_returns_teams(self, app_and_store, monkeypatch: pytest.MonkeyPatch):
        from task_summoner.api.routers import setup as setup_module

        async def fake_query(self, query):  # noqa: ARG001
            return {
                "teams": {
                    "nodes": [
                        {"id": "uuid-1", "name": "teachmewow", "key": "ENG"},
                        {"id": "uuid-2", "name": "platform", "key": "PLAT"},
                    ]
                }
            }

        monkeypatch.setattr(setup_module.LinearClient, "query", fake_query)
        client, _ = app_and_store
        body = client.post("/api/setup/linear-teams", json={"api_key": "lin_api_xxx"}).json()
        assert body["ok"] is True
        assert [t["id"] for t in body["teams"]] == ["uuid-1", "uuid-2"]
        assert body["teams"][0]["name"] == "teachmewow"
        assert body["teams"][0]["key"] == "ENG"

    def test_api_error_surfaces_inline(self, app_and_store, monkeypatch: pytest.MonkeyPatch):
        from task_summoner.api.routers import setup as setup_module
        from task_summoner.providers.board.linear.client import LinearAPIError

        async def boom(self, query):  # noqa: ARG001
            raise LinearAPIError("Linear API HTTP 401: unauthorized")

        monkeypatch.setattr(setup_module.LinearClient, "query", boom)
        client, _ = app_and_store
        body = client.post("/api/setup/linear-teams", json={"api_key": "bad"}).json()
        assert body["ok"] is False
        assert "401" in body["message"]
        assert body["teams"] == []


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
