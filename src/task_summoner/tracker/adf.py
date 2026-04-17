"""Atlassian Document Format (ADF) — Pydantic models and factory.

All ADF nodes are Pydantic v2 models. The ``Adf`` factory creates them
from simple inputs. ``AdfDocument.to_json()`` serializes the full envelope.
No raw dicts or isinstance checks in builders.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

# ═══════ Inline ═══════


class AdfMark(BaseModel):
    """Inline mark (bold, code, link)."""

    type: Literal["strong", "code", "link"]
    attrs: dict[str, str] | None = None


class AdfText(BaseModel):
    """Inline text node with optional marks."""

    type: Literal["text"] = "text"
    text: str
    marks: list[AdfMark] | None = None


# ═══════ Block nodes ═══════


class AdfParagraph(BaseModel):
    type: Literal["paragraph"] = "paragraph"
    content: list[AdfText] = Field(default_factory=list)


class AdfHeading(BaseModel):
    type: Literal["heading"] = "heading"
    attrs: dict[str, int]
    content: list[AdfText] = Field(default_factory=list)


class AdfListItem(BaseModel):
    type: Literal["listItem"] = "listItem"
    content: list[AdfParagraph]


class AdfBulletList(BaseModel):
    type: Literal["bulletList"] = "bulletList"
    content: list[AdfListItem]


class AdfOrderedList(BaseModel):
    type: Literal["orderedList"] = "orderedList"
    content: list[AdfListItem]


class AdfCodeBlock(BaseModel):
    type: Literal["codeBlock"] = "codeBlock"
    content: list[AdfText] = Field(default_factory=list)
    attrs: dict[str, str] | None = None


class AdfRule(BaseModel):
    type: Literal["rule"] = "rule"


class AdfTableHeader(BaseModel):
    type: Literal["tableHeader"] = "tableHeader"
    content: list[AdfParagraph]


class AdfTableCell(BaseModel):
    type: Literal["tableCell"] = "tableCell"
    content: list[AdfParagraph]


class AdfTableRow(BaseModel):
    type: Literal["tableRow"] = "tableRow"
    content: list[AdfTableHeader | AdfTableCell]


class AdfTable(BaseModel):
    type: Literal["table"] = "table"
    content: list[AdfTableRow]


AdfBlockNode = (
    AdfParagraph | AdfHeading | AdfBulletList | AdfOrderedList | AdfCodeBlock | AdfRule | AdfTable
)


# ═══════ Document ═══════


class AdfDocument(BaseModel):
    """Top-level ADF document. Serialize with ``to_json()``."""

    version: int = 1
    type: Literal["doc"] = "doc"
    content: list[AdfBlockNode] = Field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(self.model_dump(exclude_none=True))


# ═══════ Factory ═══════


class Adf:
    """Factory for building ADF nodes from simple inputs."""

    @staticmethod
    def text(value: str) -> AdfText:
        return AdfText(text=value)

    @staticmethod
    def bold(value: str) -> AdfText:
        return AdfText(text=value, marks=[AdfMark(type="strong")])

    @staticmethod
    def code(value: str) -> AdfText:
        return AdfText(text=value, marks=[AdfMark(type="code")])

    @staticmethod
    def link(text: str, href: str) -> AdfText:
        return AdfText(text=text, marks=[AdfMark(type="link", attrs={"href": href})])

    @staticmethod
    def paragraph(*parts: AdfText | str) -> AdfParagraph:
        content = [AdfText(text=p) if isinstance(p, str) else p for p in parts if p]
        return AdfParagraph(content=content)

    @staticmethod
    def heading(level: int, *parts: AdfText | str) -> AdfHeading:
        content = [AdfText(text=p) if isinstance(p, str) else p for p in parts if p]
        return AdfHeading(attrs={"level": level}, content=content)

    @staticmethod
    def bullet_list(items: list[AdfParagraph]) -> AdfBulletList:
        return AdfBulletList(content=[AdfListItem(content=[p]) for p in items])

    @staticmethod
    def ordered_list(items: list[AdfParagraph]) -> AdfOrderedList:
        return AdfOrderedList(content=[AdfListItem(content=[p]) for p in items])

    @staticmethod
    def code_block(text: str, language: str = "") -> AdfCodeBlock:
        attrs = {"language": language} if language else None
        return AdfCodeBlock(content=[AdfText(text=text)], attrs=attrs)

    @staticmethod
    def rule() -> AdfRule:
        return AdfRule()

    @staticmethod
    def table(header_row: AdfTableRow, body_rows: list[AdfTableRow]) -> AdfTable:
        """Build a table from pre-built header and body rows."""
        return AdfTable(content=[header_row, *body_rows])

    @staticmethod
    def doc(*nodes: AdfBlockNode) -> AdfDocument:
        return AdfDocument(content=list(nodes))
