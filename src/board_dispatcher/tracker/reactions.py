"""Approval checker — detects human decisions via Jira comment replies.

Uses the message tracker to find the exact agent comment by its bd tag,
then only analyzes HUMAN replies posted after it.
"""

from __future__ import annotations

import structlog

from board_dispatcher.tracker.feedback import FeedbackExtractor, ReactionDecision, ReactionResult
from board_dispatcher.tracker.jira_client import JiraClient
from board_dispatcher.tracker.message_tracker import get_replies_after

log = structlog.get_logger()

_extractor = FeedbackExtractor()


async def check_reaction(
    jira: JiraClient,
    ticket_key: str,
    comment_id: str,
    comments: list[dict] | None = None,
) -> ReactionResult:
    """Check for human approval by finding replies after the bd-tagged comment.

    Returns a ReactionResult with the decision and any feedback text
    the reviewer included after the keyword.
    """
    if not comment_id:
        return ReactionResult(decision=ReactionDecision.WAITING)

    if comments is None:
        comments = await jira.list_comments(ticket_key)
    if not comments:
        return ReactionResult(decision=ReactionDecision.WAITING)

    # Get only human replies after our tagged comment
    replies = get_replies_after(comments, comment_id)
    if not replies:
        return ReactionResult(decision=ReactionDecision.WAITING)

    # Check newest reply first
    for reply in reversed(replies):
        body = str(reply.get("body", ""))
        result = _extractor.extract(body)
        if result.decision != ReactionDecision.WAITING:
            log.info(
                "Reaction detected",
                ticket=ticket_key,
                decision=result.decision.value,
                has_feedback=result.has_feedback,
                body=body[:60],
            )
            return result

    return ReactionResult(decision=ReactionDecision.WAITING)
