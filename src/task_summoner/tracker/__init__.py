"""Jira adapter internals — ADF models, message tagging, feedback parsing.

These modules are used by `providers.board.jira.JiraAdapter` to convert between
Markdown and Atlassian Document Format. Core layers do not import from this
package directly — they go through `BoardProvider`.
"""

from .adf import Adf, AdfBlockNode, AdfDocument, AdfParagraph, AdfText
from .adf_converter import markdown_to_adf
from .feedback import FeedbackExtractor, ReactionDecision, ReactionResult
from .message_tracker import (
    MessageTag,
    find_latest_ts_tag,
    find_ts_comment,
    get_replies_after,
    is_ts_comment,
)

__all__ = [
    "Adf",
    "AdfBlockNode",
    "AdfDocument",
    "AdfParagraph",
    "AdfText",
    "FeedbackExtractor",
    "MessageTag",
    "ReactionDecision",
    "ReactionResult",
    "find_latest_ts_tag",
    "find_ts_comment",
    "get_replies_after",
    "is_ts_comment",
    "markdown_to_adf",
]
