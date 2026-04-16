"""Message tracker — generates unique IDs for agent comments posted to Jira.

Each comment posted by board-dispatcher includes a machine-readable tag:
  [bd:{ticket_key}:{state}:{short_id}]

This allows the approval checker to:
1. Find the exact comment it posted (not rely on position)
2. Only look at replies AFTER that specific comment
3. Avoid processing its own comments as human input
"""

from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, Field

from .adf import Adf, AdfBlockNode, AdfDocument, AdfParagraph

_BD_TAG_PATTERN = re.compile(r"\[bd:([A-Z]+-\d+):([a-z_]+):([a-z0-9]+)\]")


class MessageTag(BaseModel):
    """A unique tag embedded in board-dispatcher comments."""

    ticket_key: str
    state: str
    short_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])

    @property
    def tag(self) -> str:
        return f"[bd:{self.ticket_key}:{self.state}:{self.short_id}]"

    def embed_in(self, text: str) -> str:
        """Append the tag to a plain-text message body."""
        return f"{text}\n\n{self.tag}"

    def embed_in_adf(self, *paragraphs: AdfParagraph) -> str:
        """Build an ADF document from paragraphs + bd tag appended as last paragraph."""
        tag_para = Adf.paragraph(self.tag)
        return AdfDocument(content=[*paragraphs, tag_para]).to_json()

    def embed_nodes_in_adf(self, nodes: list[AdfBlockNode], *extra: AdfParagraph) -> str:
        """Wrap ADF block nodes + extra paragraphs + bd tag into a complete ADF document.

        Used when the comment body is rich ADF (e.g., from markdown_to_adf).
        """
        tag_para = Adf.paragraph(self.tag)
        all_nodes: list[AdfBlockNode] = [*nodes, *extra, tag_para]
        return AdfDocument(content=all_nodes).to_json()


def find_bd_comment(comments: list[dict], tag_str: str) -> int | None:
    """Find the index of a comment containing a specific bd tag."""
    for i, c in enumerate(comments):
        body = str(c.get("body", ""))
        if tag_str in body:
            return i
    return None


def is_bd_comment(comment: dict) -> bool:
    """Check if a comment was posted by board-dispatcher (contains a bd tag)."""
    body = str(comment.get("body", ""))
    return bool(_BD_TAG_PATTERN.search(body))


def find_latest_bd_tag(comments: list[dict], ticket_key: str, state: str) -> str | None:
    """Find the latest bd tag in comments matching a ticket key and state.

    Scans comments in reverse to find the most recent bd tag like
    [bd:LLMOPS-1146:implementing:abc12345]. Returns the full tag string
    or None if not found. Used for state recovery when metadata is lost.
    """
    pattern = re.compile(rf"\[bd:{re.escape(ticket_key)}:{re.escape(state)}:[a-z0-9]+\]")
    for comment in reversed(comments):
        body = str(comment.get("body", ""))
        match = pattern.search(body)
        if match:
            return match.group(0)
    return None


def get_replies_after(comments: list[dict], tag_str: str) -> list[dict]:
    """Get all human comments posted AFTER the tagged bd comment.

    Filters out other bd-tagged comments (only returns human replies).
    """
    idx = find_bd_comment(comments, tag_str)
    if idx is None:
        return []

    replies = []
    for c in comments[idx + 1:]:
        if not is_bd_comment(c):
            replies.append(c)
    return replies
