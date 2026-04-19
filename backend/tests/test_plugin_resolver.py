"""Tests for PluginResolver — registration vs enablement semantics (ENG-120)."""

from __future__ import annotations

import json
from pathlib import Path

from task_summoner.providers.agent.claude_code.plugin_resolver import (
    PluginMode,
    PluginResolver,
)


def _write_manifest(
    root: Path,
    *,
    marketplace_name: str = "task-summoner-plugin",
    plugin_names: list[str] | None = None,
) -> None:
    manifest_dir = root / ".claude-plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    plugins = [{"name": name} for name in (plugin_names or ["task-summoner-workflows"])]
    (manifest_dir / "marketplace.json").write_text(
        json.dumps({"name": marketplace_name, "plugins": plugins}),
        encoding="utf-8",
    )


class TestPluginResolverResolve:
    def test_installed_mode_resolves_to_empty(self):
        resolver = PluginResolver(mode=PluginMode.INSTALLED, plugin_path="")
        assert resolver.resolve() == []

    def test_local_mode_resolves_to_single_entry(self, tmp_path):
        resolver = PluginResolver(mode=PluginMode.LOCAL, plugin_path=str(tmp_path))
        assert resolver.resolve() == [{"type": "local", "path": str(tmp_path.resolve())}]


class TestPluginResolverEnabledKeys:
    def test_installed_mode_returns_no_keys(self, tmp_path):
        _write_manifest(tmp_path)
        resolver = PluginResolver(mode=PluginMode.INSTALLED, plugin_path=str(tmp_path))
        assert resolver.enabled_plugin_keys() == []

    def test_local_mode_derives_key_from_manifest(self, tmp_path):
        _write_manifest(tmp_path)
        resolver = PluginResolver(mode=PluginMode.LOCAL, plugin_path=str(tmp_path))
        assert resolver.enabled_plugin_keys() == ["task-summoner-workflows@task-summoner-plugin"]

    def test_local_mode_supports_multiple_plugins(self, tmp_path):
        _write_manifest(
            tmp_path,
            marketplace_name="my-market",
            plugin_names=["alpha", "beta", "gamma"],
        )
        resolver = PluginResolver(mode=PluginMode.LOCAL, plugin_path=str(tmp_path))
        assert resolver.enabled_plugin_keys() == [
            "alpha@my-market",
            "beta@my-market",
            "gamma@my-market",
        ]

    def test_local_mode_missing_manifest_returns_empty(self, tmp_path):
        resolver = PluginResolver(mode=PluginMode.LOCAL, plugin_path=str(tmp_path))
        assert resolver.enabled_plugin_keys() == []

    def test_local_mode_malformed_manifest_returns_empty(self, tmp_path):
        manifest_dir = tmp_path / ".claude-plugin"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        (manifest_dir / "marketplace.json").write_text("{not json", encoding="utf-8")
        resolver = PluginResolver(mode=PluginMode.LOCAL, plugin_path=str(tmp_path))
        assert resolver.enabled_plugin_keys() == []

    def test_local_mode_manifest_without_name_returns_empty(self, tmp_path):
        manifest_dir = tmp_path / ".claude-plugin"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        (manifest_dir / "marketplace.json").write_text(
            json.dumps({"plugins": [{"name": "p"}]}),
            encoding="utf-8",
        )
        resolver = PluginResolver(mode=PluginMode.LOCAL, plugin_path=str(tmp_path))
        assert resolver.enabled_plugin_keys() == []

    def test_local_mode_skips_plugin_entries_without_name(self, tmp_path):
        manifest_dir = tmp_path / ".claude-plugin"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        (manifest_dir / "marketplace.json").write_text(
            json.dumps(
                {
                    "name": "mkt",
                    "plugins": [
                        {"name": "good"},
                        {"description": "no-name"},
                        "not-a-dict",
                    ],
                }
            ),
            encoding="utf-8",
        )
        resolver = PluginResolver(mode=PluginMode.LOCAL, plugin_path=str(tmp_path))
        assert resolver.enabled_plugin_keys() == ["good@mkt"]


class TestPluginResolverValidation:
    def test_local_mode_without_path_errors(self):
        resolver = PluginResolver(mode=PluginMode.LOCAL, plugin_path="")
        errors = resolver.validate()
        assert errors and "plugin_path" in errors[0]

    def test_local_mode_with_missing_path_errors(self, tmp_path):
        resolver = PluginResolver(mode=PluginMode.LOCAL, plugin_path=str(tmp_path / "nope"))
        errors = resolver.validate()
        assert errors and "does not exist" in errors[0]

    def test_local_mode_with_valid_path_ok(self, tmp_path):
        resolver = PluginResolver(mode=PluginMode.LOCAL, plugin_path=str(tmp_path))
        assert resolver.validate() == []

    def test_installed_mode_never_errors(self):
        resolver = PluginResolver(mode=PluginMode.INSTALLED, plugin_path="")
        assert resolver.validate() == []
