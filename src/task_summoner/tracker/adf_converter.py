"""Markdown → ADF converter.

Converts markdown text to typed ADF block nodes (Pydantic models).
Line-by-line parser that outputs ``AdfBlockNode`` instances via the ``Adf`` factory.
"""

from __future__ import annotations

import re

from .adf import (
    Adf,
    AdfBlockNode,
    AdfParagraph,
    AdfTableCell,
    AdfTableHeader,
    AdfTableRow,
    AdfText,
)

_INLINE_PATTERN = re.compile(r"(\*\*.*?\*\*|`[^`]+`)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+)$")
_ORDERED_RE = re.compile(r"^\s*\d+\.\s+(.+)$")
_HR_RE = re.compile(r"^(---+|\*\*\*+|___+)$")
_CODE_FENCE_RE = re.compile(r"^```(\w*)\s*$")
_TABLE_ROW_RE = re.compile(r"^\|(.+)\|$")
_TABLE_SEP_RE = re.compile(r"^\|[-:| ]+\|$")


def markdown_to_adf(text: str) -> list[AdfBlockNode]:
    """Convert markdown text to a list of ADF block nodes.

    Returns typed Pydantic models (not raw dicts) so callers can
    compose them with other nodes before wrapping in ``AdfDocument``.
    """
    lines = text.split("\n")
    nodes: list[AdfBlockNode] = []

    in_code = False
    code_lang = ""
    code_lines: list[str] = []

    list_items: list[AdfParagraph] = []
    list_type = ""  # "bullet" | "ordered"

    table_rows: list[list[str]] = []
    table_is_header_next = True

    def flush_table() -> None:
        nonlocal table_rows, table_is_header_next
        if len(table_rows) < 2:  # need at least header + 1 body row
            # Not a valid table, render as paragraphs
            for row in table_rows:
                content = parse_inline(" | ".join(row))
                if content:
                    nodes.append(AdfParagraph(content=content))
            table_rows = []
            table_is_header_next = True
            return
        header_cells = table_rows[0]
        header = AdfTableRow(
            content=[
                AdfTableHeader(content=[AdfParagraph(content=parse_inline(cell))])
                for cell in header_cells
            ]
        )
        body = []
        for row in table_rows[1:]:
            body.append(
                AdfTableRow(
                    content=[
                        AdfTableCell(content=[AdfParagraph(content=parse_inline(cell))])
                        for cell in row
                    ]
                )
            )
        nodes.append(Adf.table(header, body))
        table_rows = []
        table_is_header_next = True

    def flush_list() -> None:
        nonlocal list_items, list_type
        if not list_items:
            return
        if list_type == "bullet":
            nodes.append(Adf.bullet_list(list_items))
        else:
            nodes.append(Adf.ordered_list(list_items))
        list_items = []
        list_type = ""

    def flush_code() -> None:
        nonlocal in_code, code_lines, code_lang
        nodes.append(Adf.code_block("\n".join(code_lines), code_lang))
        code_lines = []
        code_lang = ""
        in_code = False

    for line in lines:
        stripped = line.strip()

        # Code fence toggle
        fence = _CODE_FENCE_RE.match(stripped)
        if fence:
            if in_code:
                flush_code()
            else:
                flush_list()
                in_code = True
                code_lang = fence.group(1)
                code_lines = []
            continue

        if in_code:
            code_lines.append(line)
            continue

        # Empty line — flush accumulated structures
        if not stripped:
            flush_list()
            flush_table()
            continue

        # Heading
        heading = _HEADING_RE.match(stripped)
        if heading:
            flush_list()
            level = len(heading.group(1))
            nodes.append(Adf.heading(level, *parse_inline(heading.group(2))))
            continue

        # Horizontal rule
        if _HR_RE.match(stripped):
            flush_list()
            nodes.append(Adf.rule())
            continue

        # Bullet list item
        bullet = _BULLET_RE.match(line)
        if bullet:
            if list_type and list_type != "bullet":
                flush_list()
            list_type = "bullet"
            list_items.append(AdfParagraph(content=parse_inline(bullet.group(1))))
            continue

        # Ordered list item
        ordered = _ORDERED_RE.match(line)
        if ordered:
            if list_type and list_type != "ordered":
                flush_list()
            list_type = "ordered"
            list_items.append(AdfParagraph(content=parse_inline(ordered.group(1))))
            continue

        # Table row
        table_match = _TABLE_ROW_RE.match(stripped)
        if table_match:
            flush_list()
            if _TABLE_SEP_RE.match(stripped):
                continue  # skip separator row (|---|---|)
            cells = [c.strip() for c in table_match.group(1).split("|")]
            table_rows.append(cells)
            continue

        # If we were accumulating table rows and hit a non-table line, flush
        if table_rows:
            flush_table()

        # Regular paragraph
        flush_list()
        inline = parse_inline(stripped)
        if inline:
            nodes.append(AdfParagraph(content=inline))

    # Flush remaining state
    flush_list()
    flush_table()
    if in_code:
        flush_code()

    return nodes


def parse_inline(text: str) -> list[AdfText]:
    """Parse inline markdown (bold, inline code) into typed ADF text nodes."""
    if not text:
        return []

    parts = _INLINE_PATTERN.split(text)
    nodes: list[AdfText] = []

    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            inner = part[2:-2]
            if inner:
                nodes.append(Adf.bold(inner))
        elif part.startswith("`") and part.endswith("`"):
            inner = part[1:-1]
            if inner:
                nodes.append(Adf.code(inner))
        else:
            nodes.append(Adf.text(part))

    return nodes


def extract_text_from_adf(adf: dict | str | None) -> str:
    """Extract plain text from Atlassian Document Format JSON.

    acli returns description as ADF (dict with content nodes).
    Recursively walks the tree and joins text nodes.
    """
    if adf is None:
        return ""
    if isinstance(adf, str):
        return adf

    parts: list[str] = []

    def _walk(node: dict | list) -> None:
        if isinstance(node, list):
            for item in node:
                _walk(item)
            return
        if isinstance(node, dict):
            if node.get("type") == "text":
                parts.append(node.get("text", ""))
            for child in node.get("content", []):
                _walk(child)

    _walk(adf)
    return "\n".join(parts) if parts else ""
