"""Entry point: python -m task_summoner"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from task_summoner.cli import cmd_clean, cmd_run, cmd_setup, cmd_status
from task_summoner.cli_config import (
    cmd_config_get,
    cmd_config_list,
    cmd_config_set,
    cmd_config_unset,
)
from task_summoner.user_config import USER_CONFIG_KEYS

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(0),
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="task-summoner",
        description="Local-first agentic board management — provider-agnostic SDLC orchestrator",
    )
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Start the orchestrator + dashboard")
    run_p.add_argument("-c", "--config", default="config.yaml")
    run_p.add_argument("--port", type=int, default=8420, help="Dashboard port")
    run_p.add_argument("--dev", action="store_true", help="Also spawn vite dev server on :5173")

    setup_p = sub.add_parser("setup", help="Interactive setup wizard")
    setup_p.add_argument("-c", "--config", default="config.yaml")

    status_p = sub.add_parser("status", help="Show tracked tickets")
    status_p.add_argument("-c", "--config", default="config.yaml")

    clean_p = sub.add_parser(
        "clean",
        help="Remove local state for tickets that no longer exist on the board",
    )
    clean_p.add_argument("-c", "--config", default="config.yaml")
    clean_p.add_argument("--dry-run", action="store_true", help="Show what would be removed")
    clean_p.add_argument("-y", "--force", action="store_true", help="Skip confirmation prompt")

    config_p = sub.add_parser(
        "config",
        help="Get / set user-level config (docs_repo, …)",
    )
    config_sub = config_p.add_subparsers(dest="config_command")

    keys_help = ", ".join(USER_CONFIG_KEYS)

    get_p = config_sub.add_parser(
        "get",
        help=f"Print a config value + source. Keys: {keys_help}",
    )
    get_p.add_argument("key", help=f"Config key. One of: {keys_help}")

    set_p = config_sub.add_parser(
        "set",
        help="Persist a config value to the user config file (with validation)",
    )
    set_p.add_argument("key", help=f"Config key. One of: {keys_help}")
    set_p.add_argument("value", help="Value to persist. For docs_repo: absolute git repo path.")

    unset_p = config_sub.add_parser(
        "unset",
        help="Remove a key from the user config file",
    )
    unset_p.add_argument("key", help=f"Config key. One of: {keys_help}")

    config_sub.add_parser(
        "list",
        help="List all config keys with value + source",
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    match args.command:
        case "run":
            asyncio.run(cmd_run(args.config, port=args.port, dev=args.dev))
        case "setup":
            cmd_setup(args.config)
        case "status":
            cmd_status(args.config)
        case "clean":
            cmd_clean(args.config, dry_run=args.dry_run, force=args.force)
        case "config":
            sys.exit(_dispatch_config(args, parser))
        case _:
            parser.print_help()
            sys.exit(1)


def _dispatch_config(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Dispatch `task-summoner config <subcommand>`. Returns the exit code."""
    match args.config_command:
        case "get":
            return cmd_config_get(args.key)
        case "set":
            return cmd_config_set(args.key, args.value)
        case "unset":
            return cmd_config_unset(args.key)
        case "list":
            return cmd_config_list()
        case _:
            parser.parse_args(["config", "--help"])
            return 1


if __name__ == "__main__":
    main()
