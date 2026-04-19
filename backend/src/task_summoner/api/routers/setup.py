"""Setup form endpoints — combined state prefill, save, and Linear lookups.

The setup page calls ``GET /api/setup/state`` on mount to fetch the combined
prefill payload (``config.yaml`` + user config), then ``POST /api/setup/save``
to persist edits. API secrets are returned as a mask (``api_key_masked=true``)
rather than plaintext; when the client echoes the mask sentinel back in a save
request the backend preserves the currently persisted value.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml
from fastapi import APIRouter, Depends, Request

from task_summoner import user_config
from task_summoner.api.deps import get_config_path
from task_summoner.api.schemas import (
    MASKED_SECRET_SENTINEL,
    LinearTeamsRequest,
    LinearTeamsResponse,
    LinearTeamSummary,
    SetupAgentSection,
    SetupBoardSection,
    SetupGeneralSection,
    SetupRepoEntry,
    SetupSavePayload,
    SetupSaveResponse,
    SetupStateResponse,
)
from task_summoner.providers.board.linear.client import LinearAPIError, LinearClient
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
from task_summoner.user_config import UserConfigError
from task_summoner.utils import atomic_write

log = structlog.get_logger()

router = APIRouter(prefix="/api/setup", tags=["setup"])

_TEAMS_QUERY = "{ teams { nodes { id name key } } }"


@router.post("/linear-teams", response_model=LinearTeamsResponse)
async def linear_teams(payload: LinearTeamsRequest) -> LinearTeamsResponse:
    """Return the teams visible to the given Linear API key.

    Status 200 on both success and failure so the frontend can keep a single
    happy-path handler — the ``ok`` field discriminates. Mirrors
    ``/api/config/test``.
    """
    api_key = payload.api_key.strip()
    if not api_key:
        return LinearTeamsResponse(ok=False, message="API key is required.")

    try:
        data = await LinearClient(api_key).query(_TEAMS_QUERY)
    except LinearAPIError as e:
        log.warning("Linear teams lookup failed", error=str(e))
        return LinearTeamsResponse(ok=False, message=str(e))
    except Exception as e:
        log.exception("Linear teams lookup crashed")
        return LinearTeamsResponse(ok=False, message=f"Request failed: {e}")

    nodes = (data.get("teams") or {}).get("nodes") or []
    teams = [
        LinearTeamSummary(id=n["id"], name=n.get("name", ""), key=n.get("key", ""))
        for n in nodes
        if n.get("id")
    ]
    return LinearTeamsResponse(ok=True, teams=teams)


@router.get("/state", response_model=SetupStateResponse)
async def setup_state(
    config_path: Path = Depends(get_config_path),
) -> SetupStateResponse:
    """Return the combined prefill payload for the setup form.

    Merges the project-level ``config.yaml`` (providers, repos, general) with
    the user-level ``docs_repo`` from ``~/.config/task-summoner/config.json``.
    Secrets are masked — callers never see plaintext API keys.
    """
    raw = _load_yaml_if_exists(config_path)

    return SetupStateResponse(
        board=_read_board_section(raw),
        agent=_read_agent_section(raw),
        repos=_read_repos(raw),
        general=_read_general_section(raw),
    )


@router.post("/save", response_model=SetupSaveResponse)
async def setup_save(
    payload: SetupSavePayload,
    request: Request,
    config_path: Path = Depends(get_config_path),
) -> SetupSaveResponse:
    """Persist each section to its right store, then reload the orchestrator.

    ``board``, ``agent``, ``repos``, and ``general`` (minus ``docs_repo``) land
    in ``config.yaml`` via the shared renderer. ``general.docs_repo`` is
    routed to the user config so skills keep using the same value the CLI
    manages. Secrets that arrive as the mask sentinel are preserved, not
    overwritten.
    """
    errors: list[str] = []
    existing_raw = _load_yaml_if_exists(config_path)

    try:
        provider_config = _build_provider_config(payload, existing_raw)
    except Exception as e:
        return SetupSaveResponse(ok=False, errors=[f"providers: {e}"])

    repos_map = {r.name: r.path for r in payload.repos if r.name and r.path}
    general = payload.general

    yaml_text = _render_config_yaml(
        board_type=provider_config.board,
        board_config=provider_config.board_config,
        agent_type=provider_config.agent,
        agent_config=provider_config.agent_config,
        repos=repos_map,
        default_repo=general.default_repo,
        polling_interval_sec=general.polling_interval_sec,
        workspace_root=general.workspace_root or "/tmp/task-summoner-workspaces",
    )
    atomic_write(config_path, yaml_text)

    docs_repo_saved = False
    docs_repo_value = (general.docs_repo or "").strip()
    if docs_repo_value:
        try:
            user_config.set_value("docs_repo", docs_repo_value)
            docs_repo_saved = True
        except UserConfigError as e:
            errors.append(f"docs_repo: {e}")
    else:
        user_config.unset_value("docs_repo")

    from task_summoner.api.app import reload_orchestrator

    await reload_orchestrator(request.app)

    return SetupSaveResponse(
        ok=not errors,
        config_path=str(config_path.resolve()),
        docs_repo_saved=docs_repo_saved,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Internals — reading existing config
# ---------------------------------------------------------------------------


def _load_yaml_if_exists(path: Path) -> dict[str, Any]:
    """Load ``config.yaml`` as a dict; empty dict when missing or unreadable.

    Unlike ``TaskSummonerConfig.load`` this does NOT substitute env vars — the
    setup form wants to show the literal ``${FOO}`` placeholder back to the
    user rather than resolve it.
    """
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as e:
        log.warning("Failed to load config.yaml for setup state", error=str(e))
        return {}
    return raw if isinstance(raw, dict) else {}


def _read_board_section(raw: dict[str, Any]) -> SetupBoardSection:
    providers = raw.get("providers") or {}
    board_raw = providers.get("board") or {}
    board_type = board_raw.get("type") or ""

    if board_type == "linear":
        linear = board_raw.get("linear") or {}
        has_key = bool((linear.get("api_key") or "").strip())
        return SetupBoardSection(
            provider="linear",
            api_key_masked=has_key,
            api_key=MASKED_SECRET_SENTINEL if has_key else None,
            team_id=linear.get("team_id", "") or "",
            watch_label=linear.get("watch_label", "") or "",
        )
    if board_type == "jira":
        jira = board_raw.get("jira") or {}
        has_token = bool((jira.get("token") or "").strip())
        return SetupBoardSection(
            provider="jira",
            api_key_masked=has_token,
            api_key=MASKED_SECRET_SENTINEL if has_token else None,
            email=jira.get("email", "") or "",
            watch_label=jira.get("watch_label", "") or "",
        )
    return SetupBoardSection()


def _read_agent_section(raw: dict[str, Any]) -> SetupAgentSection:
    providers = raw.get("providers") or {}
    agent_raw = providers.get("agent") or {}
    agent_type = agent_raw.get("type") or ""

    if agent_type == "claude_code":
        cc = agent_raw.get("claude_code") or {}
        has_key = bool((cc.get("api_key") or "").strip())
        return SetupAgentSection(
            provider="claude_code",
            auth_method=cc.get("auth_method") or "personal_session",
            api_key_masked=has_key,
            api_key=MASKED_SECRET_SENTINEL if has_key else None,
            plugin_mode=cc.get("plugin_mode") or "installed",
            plugin_path=cc.get("plugin_path", "") or "",
        )
    if agent_type == "codex":
        codex = agent_raw.get("codex") or {}
        has_key = bool((codex.get("api_key") or "").strip())
        return SetupAgentSection(
            provider="codex",
            auth_method="api_key",
            api_key_masked=has_key,
            api_key=MASKED_SECRET_SENTINEL if has_key else None,
        )
    return SetupAgentSection()


def _read_repos(raw: dict[str, Any]) -> list[SetupRepoEntry]:
    repos = raw.get("repos") or {}
    if not isinstance(repos, dict):
        return []
    return [
        SetupRepoEntry(name=str(name), path=str(path))
        for name, path in repos.items()
        if name and path
    ]


def _read_general_section(raw: dict[str, Any]) -> SetupGeneralSection:
    return SetupGeneralSection(
        default_repo=str(raw.get("default_repo", "") or ""),
        polling_interval_sec=int(raw.get("polling_interval_sec", 10) or 10),
        workspace_root=str(raw.get("workspace_root", "") or ""),
        docs_repo=user_config.get_docs_repo() or "",
    )


# ---------------------------------------------------------------------------
# Internals — building the write model with secret preservation
# ---------------------------------------------------------------------------


def _build_provider_config(
    payload: SetupSavePayload, existing_raw: dict[str, Any]
) -> ProviderConfig:
    board_raw = payload.board or {}
    agent_raw = payload.agent or {}

    board_type = BoardProviderType(board_raw.get("provider") or "linear")
    agent_type = AgentProviderType(agent_raw.get("provider") or "claude_code")

    board_config = _build_board_config(board_type, board_raw, existing_raw)
    agent_config = _build_agent_config(agent_type, agent_raw, existing_raw)

    return ProviderConfig(
        board=board_type,
        board_config=board_config,
        agent=agent_type,
        agent_config=agent_config,
    )


def _build_board_config(
    board_type: BoardProviderType,
    payload: dict[str, Any],
    existing_raw: dict[str, Any],
) -> JiraConfig | LinearConfig:
    existing = ((existing_raw.get("providers") or {}).get("board") or {}).get(
        board_type.value
    ) or {}

    if board_type == BoardProviderType.LINEAR:
        api_key = _resolve_secret(payload.get("api_key"), existing.get("api_key"))
        return LinearConfig(
            api_key=api_key,
            team_id=payload.get("team_id", "") or "",
            watch_label=payload.get("watch_label", "") or "task-summoner",
        )
    token = _resolve_secret(payload.get("api_key"), existing.get("token"))
    return JiraConfig(
        email=payload.get("email", "") or "",
        token=token,
        watch_label=payload.get("watch_label", "") or "task-summoner",
    )


def _build_agent_config(
    agent_type: AgentProviderType,
    payload: dict[str, Any],
    existing_raw: dict[str, Any],
) -> ClaudeCodeConfig | CodexConfig:
    existing = ((existing_raw.get("providers") or {}).get("agent") or {}).get(
        agent_type.value
    ) or {}

    if agent_type == AgentProviderType.CLAUDE_CODE:
        auth_method = payload.get("auth_method") or "personal_session"
        api_key = _resolve_secret(payload.get("api_key"), existing.get("api_key"))
        return ClaudeCodeConfig(
            auth_method=auth_method,
            api_key=api_key if auth_method == "api_key" else None,
            plugin_mode=payload.get("plugin_mode") or "installed",
            plugin_path=payload.get("plugin_path") or None,
        )
    api_key = _resolve_secret(payload.get("api_key"), existing.get("api_key"))
    return CodexConfig(api_key=api_key or "")


def _resolve_secret(incoming: Any, existing: Any) -> str:
    """Return the right secret to persist.

    Rules:
      * Mask sentinel (``"********"``) → keep the existing on-disk value.
      * ``None`` / empty string → keep existing (treat missing as unchanged).
      * Anything else → use the incoming value.
    """
    if incoming is None:
        return str(existing or "")
    if isinstance(incoming, str):
        if incoming == MASKED_SECRET_SENTINEL:
            return str(existing or "")
        if incoming == "":
            return str(existing or "")
        return incoming
    return str(existing or "")
