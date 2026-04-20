"""Tests for the plan render API (``/api/plans/{key}``)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from task_summoner.api import app as app_module
from task_summoner.api.app import create_app


@pytest.fixture
def client_and_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Build a test app whose artifacts_dir is under tmp_path.

    We write a minimal config.yaml so the plans router can resolve
    ``config.artifacts_dir`` without going through the full setup flow.
    """
    monkeypatch.setattr(app_module, "_WEB_DIST", tmp_path / "no_web_dist")
    config_path = tmp_path / "config.yaml"
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    repo = tmp_path / "r"
    repo.mkdir()
    config_path.write_text(
        yaml.safe_dump(
            {
                "providers": {
                    "board": {"type": "linear", "linear": {"api_key": "k", "team_id": "t"}},
                    "agent": {
                        "type": "claude_code",
                        "claude_code": {"api_key": "ak", "plugin_mode": "installed"},
                    },
                },
                "repos": {"demo": str(repo)},
                "default_repo": "demo",
                "artifacts_dir": str(artifacts),
                "workspace_root": str(tmp_path / "ws"),
            }
        )
    )
    app = create_app(config_path=config_path)
    with TestClient(app) as client:
        yield client, artifacts


class TestGetPlan:
    def test_returns_exists_false_when_plan_not_written(self, client_and_config):
        client, _ = client_and_config
        r = client.get("/api/plans/ENG-1")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["exists"] is False
        assert body["issue_key"] == "ENG-1"

    def test_returns_content_when_plan_exists(self, client_and_config):
        client, artifacts = client_and_config
        ticket_dir = artifacts / "ENG-2"
        ticket_dir.mkdir()
        content = "# Plan for ENG-2\n\n## What\nAdd README.md.\n"
        (ticket_dir / "plan.md").write_text(content)

        r = client.get("/api/plans/ENG-2")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["exists"] is True
        assert body["title"] == "Plan for ENG-2"
        assert body["content"] == content
        assert body["plan_path"].endswith("ENG-2/plan.md")

    def test_falls_back_to_default_title_when_no_h1(self, client_and_config):
        client, artifacts = client_and_config
        ticket_dir = artifacts / "ENG-3"
        ticket_dir.mkdir()
        (ticket_dir / "plan.md").write_text("No heading at all.\nJust prose.")

        r = client.get("/api/plans/ENG-3")
        body = r.json()
        assert body["exists"] is True
        assert body["title"] == "Plan for ENG-3"

    def test_rejects_bogus_keys(self, client_and_config):
        client, _ = client_and_config
        # The path separator is stripped by the router; what reaches the
        # handler is ``..etc..passwd``. That still contains dots/slashes after
        # decode (and ``.`` isn't in our allowlist) so the validator rejects.
        r = client.get("/api/plans/has.dot")
        assert r.status_code == 400
