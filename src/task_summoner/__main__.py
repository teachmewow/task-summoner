"""Entry point: python -m task_summoner"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from task_summoner.cli import cmd_run, cmd_setup, cmd_status

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
    run_p.add_argument("--no-ui", action="store_true", help="Disable web dashboard")

    setup_p = sub.add_parser("setup", help="Interactive setup wizard")
    setup_p.add_argument("-c", "--config", default="config.yaml")

    status_p = sub.add_parser("status", help="Show tracked tickets")
    status_p.add_argument("-c", "--config", default="config.yaml")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    match args.command:
        case "run":
            asyncio.run(cmd_run(args.config, port=args.port, with_ui=not args.no_ui))
        case "setup":
            cmd_setup(args.config)
        case "status":
            cmd_status(args.config)
        case _:
            parser.print_help()
            sys.exit(1)


if __name__ == "__main__":
    main()
