"""BoardProviderFactory — instantiates the correct BoardProvider from config."""

from __future__ import annotations

from task_summoner.providers.board.jira import JiraAdapter
from task_summoner.providers.board.linear import LinearAdapter
from task_summoner.providers.board.protocol import BoardProvider
from task_summoner.providers.config import (
    BoardProviderType,
    JiraConfig,
    LinearConfig,
    ProviderConfig,
)


class BoardProviderFactory:
    """Creates a BoardProvider instance based on the provider type in config."""

    @staticmethod
    def create(config: ProviderConfig) -> BoardProvider:
        match config.board:
            case BoardProviderType.JIRA:
                if not isinstance(config.board_config, JiraConfig):
                    raise ValueError("Board provider is 'jira' but board_config is not JiraConfig")
                return JiraAdapter(config.board_config)
            case BoardProviderType.LINEAR:
                if not isinstance(config.board_config, LinearConfig):
                    raise ValueError(
                        "Board provider is 'linear' but board_config is not LinearConfig"
                    )
                return LinearAdapter(config.board_config)
            case _:
                raise ValueError(f"Unknown board provider: {config.board}")
