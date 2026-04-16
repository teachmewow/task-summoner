"""Web-based setup endpoints — alternative to the CLI wizard.

Minimal companion to the CLI wizard: renders a static form that POSTs to
`/api/config` with the provider choices. The server validates, calls the
provider factories to confirm the config shape, and writes `config.yaml`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from task_summoner.providers.board import BoardProviderFactory
from task_summoner.providers.config import (
    AgentProviderType,
    BoardProviderType,
    ClaudeCodeConfig,
    CodexConfig,
    JiraConfig,
    LinearConfig,
    ProviderConfig,
)
from task_summoner.setup_wizard import _render_config_yaml

_SETUP_PATH = Path(__file__).resolve().parent / "setup.html"


class ConfigPayload(BaseModel):
    """Incoming config from the web setup form."""

    board_type: str
    board_config: dict[str, Any]
    agent_type: str
    agent_config: dict[str, Any]
    repos: dict[str, str] = {}
    default_repo: str = ""
    polling_interval_sec: int = 10
    workspace_root: str = "/tmp/task-summoner-workspaces"


def create_setup_router(config_path: Path) -> APIRouter:
    """Return a FastAPI router serving the setup page + save/test endpoints."""
    router = APIRouter()

    @router.get("/setup", response_class=HTMLResponse)
    async def setup_page() -> str:
        if _SETUP_PATH.exists():
            return _SETUP_PATH.read_text()
        return _DEFAULT_SETUP_HTML

    @router.post("/api/config/test")
    async def test_config(payload: ConfigPayload) -> dict[str, Any]:
        try:
            _build_provider_config(payload)
            return {"ok": True, "message": "Config shape is valid."}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    @router.post("/api/config")
    async def save_config(payload: ConfigPayload) -> dict[str, Any]:
        try:
            provider_config = _build_provider_config(payload)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        yaml_text = _render_config_yaml(
            board_type=provider_config.board,
            board_config=provider_config.board_config,
            agent_type=provider_config.agent,
            agent_config=provider_config.agent_config,
            repos=payload.repos,
            default_repo=payload.default_repo,
            polling_interval_sec=payload.polling_interval_sec,
            workspace_root=payload.workspace_root,
        )
        config_path.write_text(yaml_text)
        return {"ok": True, "path": str(config_path.resolve())}

    return router


def _build_provider_config(payload: ConfigPayload) -> ProviderConfig:
    board_type = BoardProviderType(payload.board_type)
    agent_type = AgentProviderType(payload.agent_type)

    if board_type == BoardProviderType.JIRA:
        board_config: JiraConfig | LinearConfig = JiraConfig(**payload.board_config)
    else:
        board_config = LinearConfig(**payload.board_config)

    if agent_type == AgentProviderType.CLAUDE_CODE:
        agent_config: ClaudeCodeConfig | CodexConfig = ClaudeCodeConfig(
            **payload.agent_config
        )
    else:
        agent_config = CodexConfig(**payload.agent_config)

    provider_config = ProviderConfig(
        board=board_type,
        board_config=board_config,
        agent=agent_type,
        agent_config=agent_config,
    )
    BoardProviderFactory.create(provider_config)  # shape validation
    return provider_config


_DEFAULT_SETUP_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Task Summoner — Setup</title>
<style>
body { font-family: system-ui, sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem; }
fieldset { border: 1px solid #ddd; padding: 1rem; margin: 1rem 0; border-radius: 6px; }
label { display: block; margin: 0.5rem 0 0.25rem; font-weight: 600; }
input, select { width: 100%; padding: 0.5rem; font-size: 1rem; border: 1px solid #ccc; border-radius: 4px; }
button { padding: 0.5rem 1rem; font-size: 1rem; cursor: pointer; }
.primary { background: #2563eb; color: white; border: none; border-radius: 4px; }
.secondary { background: #e5e7eb; border: none; border-radius: 4px; margin-right: 0.5rem; }
.msg { margin-top: 1rem; padding: 0.75rem; border-radius: 4px; }
.msg.ok { background: #dcfce7; color: #166534; }
.msg.err { background: #fee2e2; color: #991b1b; }
.hidden { display: none; }
</style>
</head>
<body>
<h1>Task Summoner — Setup</h1>
<p>Configure your board + agent provider. The form writes to <code>config.yaml</code>.</p>

<form id="setup-form">
  <fieldset>
    <legend>Board</legend>
    <label>Board type</label>
    <select name="board_type" id="board-type">
      <option value="linear">Linear</option>
      <option value="jira">Jira</option>
    </select>

    <div id="linear-fields">
      <label>API key</label>
      <input name="linear_api_key" value="${LINEAR_API_KEY}">
      <label>Team ID</label>
      <input name="linear_team_id">
      <label>Watch label</label>
      <input name="linear_watch_label" value="task-summoner">
    </div>

    <div id="jira-fields" class="hidden">
      <label>Email</label>
      <input name="jira_email" value="${ATLASSIAN_EMAIL}">
      <label>Token</label>
      <input name="jira_token" value="${ATLASSIAN_TOKEN}">
      <label>Watch label</label>
      <input name="jira_watch_label" value="task-summoner">
    </div>
  </fieldset>

  <fieldset>
    <legend>Agent</legend>
    <label>Agent type</label>
    <select name="agent_type" id="agent-type">
      <option value="claude_code">Claude Code</option>
      <option value="codex">Codex</option>
    </select>

    <div id="claude-fields">
      <label>Anthropic API key</label>
      <input name="claude_api_key" value="${ANTHROPIC_API_KEY}">
      <label>Plugin mode</label>
      <select name="claude_plugin_mode">
        <option value="installed">installed</option>
        <option value="local">local</option>
      </select>
    </div>

    <div id="codex-fields" class="hidden">
      <label>OpenAI API key</label>
      <input name="codex_api_key" value="${OPENAI_API_KEY}">
    </div>
  </fieldset>

  <fieldset>
    <legend>Workspace</legend>
    <label>Polling interval (seconds)</label>
    <input type="number" name="polling_interval_sec" value="10">
    <label>Workspace root</label>
    <input name="workspace_root" value="/tmp/task-summoner-workspaces">
  </fieldset>

  <button type="button" class="secondary" onclick="testConfig()">Test</button>
  <button type="submit" class="primary">Save config.yaml</button>
</form>

<div id="message"></div>

<script>
const $ = (id) => document.getElementById(id);
function toggle() {
  $('linear-fields').classList.toggle('hidden', $('board-type').value !== 'linear');
  $('jira-fields').classList.toggle('hidden', $('board-type').value !== 'jira');
  $('claude-fields').classList.toggle('hidden', $('agent-type').value !== 'claude_code');
  $('codex-fields').classList.toggle('hidden', $('agent-type').value !== 'codex');
}
$('board-type').addEventListener('change', toggle);
$('agent-type').addEventListener('change', toggle);
toggle();

function buildPayload() {
  const form = $('setup-form');
  const fd = new FormData(form);
  const boardType = fd.get('board_type');
  const agentType = fd.get('agent_type');
  const boardConfig = boardType === 'jira'
    ? { email: fd.get('jira_email'), token: fd.get('jira_token'), watch_label: fd.get('jira_watch_label') }
    : { api_key: fd.get('linear_api_key'), team_id: fd.get('linear_team_id'), watch_label: fd.get('linear_watch_label') };
  const agentConfig = agentType === 'codex'
    ? { api_key: fd.get('codex_api_key') }
    : { api_key: fd.get('claude_api_key'), plugin_mode: fd.get('claude_plugin_mode') };
  return {
    board_type: boardType,
    board_config: boardConfig,
    agent_type: agentType,
    agent_config: agentConfig,
    repos: {},
    default_repo: "",
    polling_interval_sec: parseInt(fd.get('polling_interval_sec') || '10'),
    workspace_root: fd.get('workspace_root') || '/tmp/task-summoner-workspaces',
  };
}

function showMessage(ok, text) {
  const el = $('message');
  el.className = `msg ${ok ? 'ok' : 'err'}`;
  el.textContent = text;
}

async function testConfig() {
  const res = await fetch('/api/config/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(buildPayload()),
  });
  const data = await res.json();
  showMessage(data.ok, data.message || 'Tested');
}

$('setup-form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const res = await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(buildPayload()),
  });
  if (!res.ok) {
    const err = await res.json();
    showMessage(false, `Error: ${err.detail || res.statusText}`);
    return;
  }
  const data = await res.json();
  showMessage(true, `Config written to ${data.path}. Run "task-summoner run" to start.`);
});
</script>
</body>
</html>
"""
