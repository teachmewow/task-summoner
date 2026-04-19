"""ClaudeCodeAdapter — implements AgentProvider via the Claude Agent SDK.

Translates between the provider-agnostic AgentProvider contract and the
Claude-specific SDK: maps AgentProfile to ClaudeAgentOptions, emits
generic AgentEvent instances (never raw SDK types) through event_callback.

MCP wiring is mode-aware:

- **LOCAL mode** = strict isolation. The adapter builds an explicit
  ``mcp_servers`` map and the spawned subprocess cannot pick up the user's
  global ``claude mcp add`` servers (which may be authenticated against a
  different workspace). The Linear MCP server is scoped with the API key
  carried in ``.env`` as ``LINEAR_API_KEY``, and the system prompt
  reiterates the configured ``team_id`` so the agent never touches tickets
  from other workspaces even if the key happens to have multi-workspace
  visibility.
- **INSTALLED mode** = trust the user's local Claude Code setup. The
  adapter returns ``None`` for ``mcp_servers`` so the SDK falls back to
  whatever ``setting_sources=["user"]`` loaded. INSTALLED trusts your
  local setup; cross-workspace pollution is your responsibility.

Cancellation contract: `_consume_stream` wraps the SDK async-iterator in a
`try/finally` so that on orchestrator shutdown (`asyncio.CancelledError`)
the underlying `query(...)` generator is closed and any subprocess the SDK
spawned receives termination. CancelledError is always re-raised.

Plugin enablement (ENG-120): LOCAL mode pairs ``plugins=[{type: "local",
path: ...}]`` with a synthesized ``settings`` JSON carrying
``enabledPlugins: {<plugin>@<marketplace>: true}``. Without the
enablement map the CLI lists the plugin directory but does not surface
its skills, so the subprocess sees only global defaults. The map is
derived from the plugin's own ``marketplace.json`` — see
``PluginResolver.enabled_plugin_keys``.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

from task_summoner.providers.agent.claude_code.plugin_resolver import (
    PluginMode,
    PluginResolver,
)
from task_summoner.providers.agent.protocol import (
    AgentEvent,
    AgentEventType,
    AgentProfile,
    AgentResult,
)
from task_summoner.providers.config import ClaudeCodeConfig

log = structlog.get_logger()

# Environment variables forwarded from the task-summoner process into the
# Claude Code subprocess. Do not inherit the full parent env — only the keys
# we explicitly own. `LINEAR_API_KEY` is required for MCP isolation: the
# spawned agent uses it (via the scoped Linear MCP below) instead of
# whatever OAuth token the user's global Claude Code session carries.
_FORWARDED_ENV_KEYS = [
    "ANTHROPIC_API_KEY",
    "ATLASSIAN_EMAIL",
    "ATLASSIAN_TOKEN",
    "SLACK_BOT_TOKEN",
    "SLACK_USER_ID",
    "LINEAR_API_KEY",
    "LINEAR_WORKSPACE_ID",
    # Forward the docs-repo override when the user sets it explicitly. The
    # `create-design-doc` skill resolves docs_repo through `task-summoner
    # config get docs_repo`, which already honours this env var — forwarding
    # it keeps the subprocess aligned with the orchestrator's view when the
    # user opted out of the user-config file.
    "TASK_SUMMONER_DOCS_REPO",
]


class ClaudeCodeAdapter:
    """AgentProvider implementation backed by the Claude Agent SDK."""

    def __init__(
        self,
        config: ClaudeCodeConfig,
        *,
        board_team_id: str | None = None,
    ) -> None:
        """Create the adapter.

        Args:
            config: Claude Code-specific settings (auth, plugin mode).
            board_team_id: Optional Linear team_id threaded through from the
                active BoardConfig. When set, the system prompt tells the
                agent to scope every Linear MCP call by this team_id so it
                cannot accidentally surface tickets from other workspaces.
        """
        self._config = config
        self._board_team_id = board_team_id

    def supports_streaming(self) -> bool:
        return True

    def supports_tool_use(self) -> bool:
        return True

    async def run(
        self,
        prompt: str,
        profile: AgentProfile,
        working_dir: Path,
        event_callback: Callable[[AgentEvent], None] | None = None,
    ) -> AgentResult:
        options = self._build_options(profile, working_dir)

        log.info(
            "Agent starting",
            agent=profile.name,
            model=profile.model,
            max_turns=profile.max_turns,
            budget=profile.max_cost_usd,
            cwd=str(working_dir),
        )

        output_parts: list[str] = []
        cost = 0.0
        turns = 0
        error: str | None = None

        try:
            output_parts, cost, turns, error = await self._consume_stream(
                prompt=prompt,
                options=options,
                profile=profile,
                event_callback=event_callback,
            )
        except asyncio.CancelledError:
            # Propagate cancellation so the orchestrator's shutdown path can
            # observe it. The `_consume_stream` finally block has already
            # closed the SDK generator and any subprocess it spawned.
            log.info("Agent cancelled", agent=profile.name)
            raise
        except Exception as e:
            log.error("Agent SDK error", agent=profile.name, error=str(e))
            error = str(e)
            self._emit(
                event_callback,
                AgentEvent(
                    type=AgentEventType.ERROR,
                    content=error,
                    metadata={"agent": profile.name},
                ),
            )

        success = error is None
        self._emit(
            event_callback,
            AgentEvent(
                type=AgentEventType.COMPLETED,
                content="",
                metadata={
                    "agent": profile.name,
                    "success": success,
                    "cost_usd": cost,
                    "turns": turns,
                },
            ),
        )

        log.info(
            "Agent finished",
            agent=profile.name,
            turns=turns,
            cost=f"${cost:.4f}",
            success=success,
        )

        return AgentResult(
            success=success,
            output="\n".join(output_parts),
            cost_usd=cost,
            turns_used=turns,
            error=error,
        )

    async def _consume_stream(
        self,
        *,
        prompt: str,
        options: ClaudeAgentOptions,
        profile: AgentProfile,
        event_callback: Callable[[AgentEvent], None] | None,
    ) -> tuple[list[str], float, int, str | None]:
        """Consume the streaming response from the Claude SDK.

        When LangSmith tracing is enabled at startup,
        `langsmith.integrations.claude_agent_sdk.configure_claude_agent_sdk()`
        auto-instruments this loop: each tool use, message, and result becomes
        a span. No manual decorators needed here.

        Cancellation: on `asyncio.CancelledError` the `finally` closes the
        underlying async generator — `claude_agent_sdk.query(...)` is
        documented to terminate the spawned subprocess when its generator is
        closed. CancelledError propagates to the caller unchanged.
        """
        output_parts: list[str] = []
        cost = 0.0
        turns = 0
        error: str | None = None
        # Maps tool_use_id -> tool name so tool results can be joined with the
        # originating call in the stream (the UI needs this for the collapsible
        # tool-call boxes).
        tool_name_by_id: dict[str, str] = {}

        stream = query(prompt=prompt, options=options)
        try:
            async for message in stream:
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            output_parts.append(block.text)
                            self._emit(
                                event_callback,
                                AgentEvent(
                                    type=AgentEventType.MESSAGE,
                                    content=block.text,
                                    metadata={"agent": profile.name},
                                ),
                            )
                        elif isinstance(block, ToolUseBlock):
                            tool_name_by_id[block.id] = block.name
                            self._emit(
                                event_callback,
                                AgentEvent(
                                    type=AgentEventType.TOOL_USE,
                                    content=block.name,
                                    metadata={
                                        "agent": profile.name,
                                        "tool_use_id": block.id,
                                        "tool_input": _safe_tool_input(block.input),
                                    },
                                ),
                            )
                elif isinstance(message, UserMessage):
                    blocks = message.content if isinstance(message.content, list) else []
                    for block in blocks:
                        if isinstance(block, ToolResultBlock):
                            tool_name = tool_name_by_id.get(block.tool_use_id, "")
                            self._emit(
                                event_callback,
                                AgentEvent(
                                    type=AgentEventType.TOOL_RESULT,
                                    content=tool_name,
                                    metadata={
                                        "agent": profile.name,
                                        "tool_use_id": block.tool_use_id,
                                        "tool_name": tool_name,
                                        "tool_result": _safe_tool_result(block.content),
                                        "is_error": bool(block.is_error),
                                    },
                                ),
                            )
                elif isinstance(message, ResultMessage):
                    cost = getattr(message, "total_cost_usd", 0.0) or 0.0
                    turns = getattr(message, "num_turns", 0) or 0
                    if getattr(message, "is_error", False):
                        error = getattr(message, "result", None) or "Agent error"
        finally:
            # Close the async generator so the SDK tears down its subprocess.
            # Some claude-agent-sdk versions return a plain async iterator
            # without `aclose`; guard accordingly.
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except Exception as close_err:
                    log.warning(
                        "Failed to close agent stream cleanly",
                        agent=profile.name,
                        error=str(close_err),
                    )

        return output_parts, cost, turns, error

    def _build_options(self, profile: AgentProfile, working_dir: Path) -> ClaudeAgentOptions:
        resolver = self._make_resolver()
        return ClaudeAgentOptions(
            cwd=str(working_dir),
            model=profile.model,
            max_turns=profile.max_turns,
            max_budget_usd=profile.max_cost_usd,
            allowed_tools=profile.tools,
            permission_mode="bypassPermissions",
            setting_sources=self._resolve_setting_sources(),
            plugins=resolver.resolve(),
            settings=self._build_settings(resolver),
            env=self._build_env(),
            mcp_servers=self._build_mcp_servers(),
            system_prompt=self._build_system_prompt(),
        )

    def _make_resolver(self) -> PluginResolver:
        try:
            mode = PluginMode(self._config.plugin_mode)
        except ValueError as e:
            raise ValueError(f"Unknown plugin_mode: {self._config.plugin_mode}") from e

        resolver = PluginResolver(mode=mode, plugin_path=self._config.plugin_path or "")
        errors = resolver.validate()
        if errors:
            raise ValueError("; ".join(errors))
        return resolver

    def _resolve_plugins(self, profile: AgentProfile) -> list[dict[str, str]]:
        """Back-compat helper retained for tests that exercise resolver output.

        The production path runs through ``_build_options`` which shares a
        single resolver with ``_build_settings`` — do not use this method to
        build options.
        """
        return self._make_resolver().resolve()

    def _build_settings(self, resolver: PluginResolver) -> str | None:
        """Emit a JSON settings blob enabling the LOCAL-mode plugin (ENG-120).

        In LOCAL mode ``setting_sources`` is ``[]`` so the CLI never reads
        ``~/.claude/settings.json`` (that's how ENG-114 blocked global MCP
        leakage). A side effect is that ``enabledPlugins`` from user settings
        is also gone, which leaves ``--plugin-dir`` loading the marketplace
        but never turning on any of its plugins — all ``task-summoner-
        workflows:*`` skills vanish from the subprocess.

        The CLI's ``--settings`` flag accepts an inline JSON blob that the SDK
        threads through verbatim. We use it to ship the minimum
        ``{"enabledPlugins": {<plugin>@<marketplace>: true, ...}}`` map, which
        registers the plugins as enabled without re-opening the user scope to
        any other setting (including MCP servers). Marketplace + plugin names
        come from the plugin's own ``marketplace.json`` so we stay honest if
        either is renamed.

        Returns ``None`` for INSTALLED mode or when the marketplace manifest
        can't be parsed — in both cases there is nothing for us to inject and
        the SDK falls back to its default behaviour.
        """
        if resolver.mode != PluginMode.LOCAL:
            return None
        keys = resolver.enabled_plugin_keys()
        if not keys:
            return None
        settings = {"enabledPlugins": {key: True for key in keys}}
        return json.dumps(settings)

    def _resolve_setting_sources(self) -> list[str]:
        """Pick `setting_sources` from the user's plugin_mode config.

        LOCAL mode injects the plugin explicitly via `plugin_path` and the
        adapter injects `mcp_servers` explicitly too. The user-scope Claude
        Code settings must NOT be inherited, or globally-registered MCPs
        (e.g. a different workspace's Linear) leak in and pollute dispatch
        data. Return an empty list — no inheritance.

        INSTALLED mode relies on the user's global Claude Code settings to
        provide the plugin enablement, so `setting_sources=["user"]` is
        required. Downstream MCP isolation is the user's responsibility in
        that case (don't register conflicting MCPs globally).
        """
        try:
            mode = PluginMode(self._config.plugin_mode)
        except ValueError as e:
            raise ValueError(f"Unknown plugin_mode: {self._config.plugin_mode}") from e

        if mode == PluginMode.LOCAL:
            return []
        return ["user"]

    def _build_env(self) -> dict[str, str]:
        """Forward credentials to the spawned agent subprocess.

        For `auth_method=personal_session`, we deliberately do NOT forward
        ANTHROPIC_API_KEY so the agent inherits the user's logged-in Claude
        Code session (stored in ~/.claude/) instead of a bespoke key.
        """
        keys = list(_FORWARDED_ENV_KEYS)
        if self._config.auth_method == "personal_session":
            keys = [k for k in keys if k != "ANTHROPIC_API_KEY"]
        env = {k: os.environ[k] for k in keys if os.environ.get(k)}
        if self._config.auth_method == "api_key" and self._config.api_key:
            env["ANTHROPIC_API_KEY"] = self._config.api_key
        return env

    def _build_mcp_servers(self) -> dict[str, Any] | None:
        """Build the ``mcp_servers`` value for ``ClaudeAgentOptions``.

        Behaviour is mode-aware:

        - **LOCAL** returns an explicit dict. This replaces — not extends —
          whatever the user's global Claude Code config might have
          registered (another workspace's Linear, random hosted MCPs, etc.).
          When ``LINEAR_API_KEY`` is set in our ``.env`` we add a Linear
          MCP entry; otherwise we emit an empty dict (still non-``None``,
          so global MCP inheritance stays blocked).

          The Linear entry uses the ``@tacticlaunch/mcp-linear`` npm
          package over stdio. It is the only widely-distributed package
          that authenticates with a raw Personal Access Token — Linear's
          hosted HTTP MCP at ``mcp.linear.app`` requires OAuth, which has
          no way to complete a browser flow from a headless subprocess
          (smoke tests showed ``No such tool available:
          mcp__linear-server__get_issue`` because the SDK silently marked
          the server as unavailable after auth failed). The package's own
          env var is ``LINEAR_API_TOKEN``; we read our canonical
          ``LINEAR_API_KEY`` and forward it under that name inside the MCP
          entry.

          Shape returned to claude-agent-sdk::

              {
                  "linear-server": {
                      "type": "stdio",
                      "command": "npx",
                      "args": ["-y", "@tacticlaunch/mcp-linear@latest"],
                      "env": {"LINEAR_API_TOKEN": "<key>"},
                  },
              }

        - **INSTALLED** returns ``None``. With
          ``setting_sources=["user"]`` the SDK loads the user's global
          Claude Code settings and picks up whatever MCPs they already
          registered (``claude mcp add``). Overriding ``mcp_servers`` here
          would silently strip that — INSTALLED mode is explicitly opt-in
          to "trust my local setup", so we stay out of the way.
        """
        mode = PluginMode(self._config.plugin_mode)
        if mode == PluginMode.INSTALLED:
            return None

        servers: dict[str, Any] = {}
        linear_key = os.environ.get("LINEAR_API_KEY")
        if linear_key:
            servers["linear-server"] = {
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@tacticlaunch/mcp-linear@latest"],
                "env": {"LINEAR_API_TOKEN": linear_key},
            }

        return servers

    def _build_system_prompt(self) -> str | None:
        """Compose the isolation-reinforcing system prompt (LOCAL mode only).

        In LOCAL mode the adapter owns the Linear MCP wiring, so it is also
        the right place to tell the agent which team_id to scope every call
        by. This is belt-and-suspenders on top of the explicit
        ``mcp_servers`` config: even if the configured key had visibility
        into multiple workspaces, the prompt tells the agent to always scope
        Linear MCP calls to the configured team_id.

        In INSTALLED mode the user owns MCP configuration (including any
        team scoping they baked into their own setup), so we do not inject
        a team-scoping prompt line — doing so could contradict their
        intent.

        Returns ``None`` when there is nothing to add so the SDK falls back
        to its default system prompt.
        """
        mode = PluginMode(self._config.plugin_mode)
        if mode != PluginMode.LOCAL:
            return None
        if not self._board_team_id:
            return None

        team_id = self._board_team_id
        return (
            "Task Summoner operational constraints:\n"
            f"- ALWAYS pass team_id={team_id} when calling Linear MCP tools "
            "(linear-server__list_issues, linear-server__list_projects, "
            "linear-server__list_teams, etc.).\n"
            "- Never act on tickets from other Linear workspaces; ignore any "
            "ticket whose team_id does not match the configured team_id.\n"
            "- The Linear MCP is explicitly configured by the orchestrator; "
            "do not attempt to reconfigure it."
        )

    def _emit(
        self,
        callback: Callable[[AgentEvent], None] | None,
        event: AgentEvent,
    ) -> None:
        if callback:
            callback(event)


_TOOL_INPUT_MAX_CHARS = 20_000
_TOOL_RESULT_MAX_CHARS = 20_000


def _safe_tool_input(inp: Any) -> dict[str, Any]:
    """Normalize a tool-use input dict for the event stream.

    The UI inspects tool input inside a collapsible box so the cap is generous,
    not the 200-char preview we used when the callback only drove log lines.
    We still cap to bound memory for pathological calls (e.g. massive Edits).
    """
    if isinstance(inp, dict):
        out: dict[str, Any] = {}
        for k, v in inp.items():
            if isinstance(v, str):
                out[k] = v if len(v) <= _TOOL_INPUT_MAX_CHARS else v[:_TOOL_INPUT_MAX_CHARS] + "..."
            else:
                out[k] = v
        return out
    raw = str(inp)
    if len(raw) > _TOOL_INPUT_MAX_CHARS:
        raw = raw[:_TOOL_INPUT_MAX_CHARS] + "..."
    return {"raw": raw}


def _safe_tool_result(content: Any) -> str:
    """Coerce a ToolResultBlock payload into a string for the stream.

    The SDK emits either a plain string or a list of ``{type, text}`` chunks
    (the content-block shape used by Anthropic's API). Collapse to a single
    string so the UI can render it verbatim inside a ``<pre>``. Long outputs
    are truncated to keep the JSONL file bounded.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return (
            content
            if len(content) <= _TOOL_RESULT_MAX_CHARS
            else content[:_TOOL_RESULT_MAX_CHARS] + "..."
        )
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                    continue
            parts.append(str(item))
        joined = "\n".join(parts)
        return (
            joined
            if len(joined) <= _TOOL_RESULT_MAX_CHARS
            else joined[:_TOOL_RESULT_MAX_CHARS] + "..."
        )
    raw = str(content)
    return raw if len(raw) <= _TOOL_RESULT_MAX_CHARS else raw[:_TOOL_RESULT_MAX_CHARS] + "..."
