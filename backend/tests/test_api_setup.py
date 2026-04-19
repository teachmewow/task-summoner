"""Tests for the combined setup endpoints (/api/setup/state + /api/setup/save).

Covers:

* ``GET /api/setup/state`` — empty config → empty shape; existing config →
  populated + secrets masked.
* ``POST /api/setup/save`` — routes board/agent/repos/general to config.yaml,
  docs_repo to the user config, preserves unchanged secrets, and validates
  docs_repo before persisting.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from task_summoner.api import app as app_module
from task_summoner.api.app import create_app
from task_summoner.api.schemas.setup import MASKED_SECRET_SENTINEL
from task_summoner.user_config import user_config_path


@pytest.fixture
def isolated_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Run the FastAPI app against a temp config.yaml + isolated XDG dir."""
    monkeypatch.setattr(app_module, "_WEB_DIST", tmp_path / "no_web_dist")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("TASK_SUMMONER_DOCS_REPO", raising=False)
    config_path = tmp_path / "config.yaml"
    app = create_app(config_path=config_path)
    with TestClient(app) as client:
        yield client, config_path, tmp_path


def _make_docs_repo(root: Path) -> Path:
    repo = root / "docs-repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    marker_dir = repo / ".task-summoner"
    marker_dir.mkdir()
    (marker_dir / "config.yml").write_text("version: 1\n")
    return repo


def _save_payload(tmp_path: Path, **overrides) -> dict:
    repo_dir = tmp_path / "demo-repo"
    repo_dir.mkdir(exist_ok=True)
    base = {
        "board": {
            "provider": "linear",
            "api_key": "lin_api_xxx",
            "team_id": "team-uuid",
            "watch_label": "task-summoner",
        },
        "agent": {
            "provider": "claude_code",
            "auth_method": "api_key",
            "api_key": "ak-123",
            "plugin_mode": "installed",
            "plugin_path": "",
        },
        "repos": [{"name": "demo", "path": str(repo_dir)}],
        "general": {
            "default_repo": "demo",
            "polling_interval_sec": 12,
            "workspace_root": str(tmp_path / "ws"),
            "docs_repo": "",
        },
    }
    for section, patch in overrides.items():
        base[section] = {**base[section], **patch} if isinstance(base[section], dict) else patch
    return base


class TestSetupStateEndpoint:
    def test_empty_config_returns_blank_shape(self, isolated_setup):
        client, _, _ = isolated_setup
        body = client.get("/api/setup/state").json()

        assert body["board"]["provider"] == ""
        assert body["board"]["api_key_masked"] is False
        assert body["board"]["api_key"] is None
        assert body["agent"]["provider"] == ""
        assert body["repos"] == []
        assert body["general"]["docs_repo"] == ""

    def test_populated_config_masks_secrets(self, isolated_setup):
        client, _, tmp_path = isolated_setup
        # Save once, then refetch — mask should replace the plaintext key.
        payload = _save_payload(tmp_path)
        assert client.post("/api/setup/save", json=payload).status_code == 200

        body = client.get("/api/setup/state").json()

        assert body["board"]["provider"] == "linear"
        assert body["board"]["api_key_masked"] is True
        assert body["board"]["api_key"] == MASKED_SECRET_SENTINEL
        assert body["board"]["team_id"] == "team-uuid"
        assert body["agent"]["provider"] == "claude_code"
        assert body["agent"]["auth_method"] == "api_key"
        assert body["agent"]["api_key_masked"] is True
        assert body["agent"]["api_key"] == MASKED_SECRET_SENTINEL
        assert [r["name"] for r in body["repos"]] == ["demo"]
        assert body["general"]["default_repo"] == "demo"
        assert body["general"]["polling_interval_sec"] == 12

        # And crucially: the literal plaintext key never appears in the body.
        raw = json.dumps(body)
        assert "lin_api_xxx" not in raw
        assert "ak-123" not in raw

    def test_docs_repo_from_user_config_included(self, isolated_setup, tmp_path: Path):
        client, _, _ = isolated_setup
        repo = _make_docs_repo(tmp_path)

        client.post(
            "/api/setup/save",
            json=_save_payload(tmp_path, general={"docs_repo": str(repo)}),
        )

        body = client.get("/api/setup/state").json()
        assert body["general"]["docs_repo"] == str(repo)


class TestSetupSaveEndpoint:
    def test_writes_yaml_and_flips_configured(self, isolated_setup, tmp_path: Path):
        client, config_path, _ = isolated_setup
        before = client.get("/api/config/status").json()
        assert before["configured"] is False

        response = client.post("/api/setup/save", json=_save_payload(tmp_path))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["ok"] is True
        assert body["config_path"] == str(config_path.resolve())

        persisted = yaml.safe_load(config_path.read_text())
        assert persisted["providers"]["board"]["type"] == "linear"
        assert persisted["providers"]["board"]["linear"]["api_key"] == "lin_api_xxx"
        assert persisted["providers"]["agent"]["type"] == "claude_code"
        assert persisted["polling_interval_sec"] == 12
        assert persisted["default_repo"] == "demo"

        status = client.get("/api/config/status").json()
        assert status["configured"] is True

    def test_mask_sentinel_preserves_existing_secret(self, isolated_setup, tmp_path: Path):
        client, config_path, _ = isolated_setup
        client.post("/api/setup/save", json=_save_payload(tmp_path))

        # Frontend echoes the mask back on resave — on-disk key must stay.
        resave = _save_payload(
            tmp_path,
            board={"api_key": MASKED_SECRET_SENTINEL, "team_id": "team-new"},
            agent={"api_key": MASKED_SECRET_SENTINEL},
        )
        response = client.post("/api/setup/save", json=resave)
        assert response.status_code == 200, response.text

        persisted = yaml.safe_load(config_path.read_text())
        assert persisted["providers"]["board"]["linear"]["api_key"] == "lin_api_xxx"
        assert persisted["providers"]["board"]["linear"]["team_id"] == "team-new"
        assert persisted["providers"]["agent"]["claude_code"]["api_key"] == "ak-123"

    def test_empty_api_key_preserves_existing(self, isolated_setup, tmp_path: Path):
        client, config_path, _ = isolated_setup
        client.post("/api/setup/save", json=_save_payload(tmp_path))

        # Empty string from the form → still preserve, not blank-out.
        resave = _save_payload(
            tmp_path,
            board={"api_key": "", "team_id": "team-uuid"},
            agent={"api_key": ""},
        )
        client.post("/api/setup/save", json=resave)

        persisted = yaml.safe_load(config_path.read_text())
        assert persisted["providers"]["board"]["linear"]["api_key"] == "lin_api_xxx"
        assert persisted["providers"]["agent"]["claude_code"]["api_key"] == "ak-123"

    def test_new_api_key_overwrites(self, isolated_setup, tmp_path: Path):
        client, config_path, _ = isolated_setup
        client.post("/api/setup/save", json=_save_payload(tmp_path))

        resave = _save_payload(tmp_path, board={"api_key": "lin_api_new"})
        client.post("/api/setup/save", json=resave)

        persisted = yaml.safe_load(config_path.read_text())
        assert persisted["providers"]["board"]["linear"]["api_key"] == "lin_api_new"

    def test_valid_docs_repo_lands_in_user_config(self, isolated_setup, tmp_path: Path):
        client, _, _ = isolated_setup
        repo = _make_docs_repo(tmp_path)

        response = client.post(
            "/api/setup/save",
            json=_save_payload(tmp_path, general={"docs_repo": str(repo)}),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["docs_repo_saved"] is True
        assert body["errors"] == []

        persisted_user = json.loads(user_config_path().read_text())
        assert persisted_user["docs_repo"] == str(repo)

    def test_invalid_docs_repo_returns_inline_error(self, isolated_setup, tmp_path: Path):
        client, _, _ = isolated_setup
        bogus = tmp_path / "not-a-repo"
        bogus.mkdir()

        response = client.post(
            "/api/setup/save",
            json=_save_payload(tmp_path, general={"docs_repo": str(bogus)}),
        )
        # Config still saves; docs_repo surfaces as a field-level error.
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is False
        assert any("docs_repo" in err for err in body["errors"])
        assert body["docs_repo_saved"] is False

    def test_empty_docs_repo_clears_user_config(self, isolated_setup, tmp_path: Path):
        client, _, _ = isolated_setup
        repo = _make_docs_repo(tmp_path)
        client.post(
            "/api/setup/save",
            json=_save_payload(tmp_path, general={"docs_repo": str(repo)}),
        )
        assert "docs_repo" in json.loads(user_config_path().read_text())

        client.post(
            "/api/setup/save",
            json=_save_payload(tmp_path, general={"docs_repo": ""}),
        )
        assert json.loads(user_config_path().read_text()) == {}
