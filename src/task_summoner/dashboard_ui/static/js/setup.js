/* Setup form — gathers provider config + POSTs to /api/config. */

const $ = (id) => document.getElementById(id);

function toggleVisibility() {
  $('linear-fields').classList.toggle('hidden', $('board-type').value !== 'linear');
  $('jira-fields').classList.toggle('hidden', $('board-type').value !== 'jira');
  $('claude-fields').classList.toggle('hidden', $('agent-type').value !== 'claude_code');
  $('codex-fields').classList.toggle('hidden', $('agent-type').value !== 'codex');
}

function buildPayload() {
  const form = $('setup-form');
  const fd = new FormData(form);
  const boardType = fd.get('board_type');
  const agentType = fd.get('agent_type');

  const boardConfig = boardType === 'jira'
    ? {
        email: fd.get('jira_email'),
        token: fd.get('jira_token'),
        watch_label: fd.get('jira_watch_label'),
      }
    : {
        api_key: fd.get('linear_api_key'),
        team_id: fd.get('linear_team_id'),
        watch_label: fd.get('linear_watch_label'),
      };

  const agentConfig = agentType === 'codex'
    ? { api_key: fd.get('codex_api_key') }
    : {
        api_key: fd.get('claude_api_key'),
        plugin_mode: fd.get('claude_plugin_mode'),
      };

  return {
    board_type: boardType,
    board_config: boardConfig,
    agent_type: agentType,
    agent_config: agentConfig,
    repos: {},
    default_repo: '',
    polling_interval_sec: parseInt(fd.get('polling_interval_sec') || '10', 10),
    workspace_root: fd.get('workspace_root') || '/tmp/task-summoner-workspaces',
  };
}

function showMessage(ok, text) {
  const el = $('message');
  el.className = `msg ${ok ? 'ok' : 'err'}`;
  el.textContent = text;
}

async function testConfig() {
  try {
    const res = await fetch('/api/config/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildPayload()),
    });
    const data = await res.json();
    showMessage(data.ok, data.message || 'Tested');
  } catch (err) {
    showMessage(false, `Request failed: ${err.message}`);
  }
}

async function saveConfig(ev) {
  ev.preventDefault();
  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildPayload()),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showMessage(false, `Error: ${err.detail || res.statusText}`);
      return;
    }
    const data = await res.json();
    showMessage(
      true,
      `Config written to ${data.path}. Run "task-summoner run" to start.`,
    );
  } catch (err) {
    showMessage(false, `Request failed: ${err.message}`);
  }
}

$('board-type').addEventListener('change', toggleVisibility);
$('agent-type').addEventListener('change', toggleVisibility);
$('test-btn').addEventListener('click', testConfig);
$('setup-form').addEventListener('submit', saveConfig);
toggleVisibility();
