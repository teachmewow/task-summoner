"""Jira ticket model — normalized from acli JSON output."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class Ticket(BaseModel):
    """Normalized Jira ticket from acli output."""

    key: str = Field(..., pattern=r"^[A-Z]+-\d+$")
    summary: str
    description: str = ""
    status: str = ""
    labels: list[str] = Field(default_factory=list)
    assignee: str | None = None
    project_key: str = ""
    acceptance_criteria: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def derive_project_key(cls, values: dict) -> dict:
        if not values.get("project_key") and values.get("key"):
            key = values["key"]
            values["project_key"] = key.split("-")[0] if "-" in key else ""
        return values

    @classmethod
    def from_acli_json(cls, data: dict) -> Ticket:
        key = data.get("key", "UNKNOWN-0")
        fields = data.get("fields", data)

        raw_desc = fields.get("description")
        if isinstance(raw_desc, dict):
            description = _extract_text_from_adf(raw_desc)
        else:
            description = raw_desc or ""

        return cls(
            key=key,
            summary=fields.get("summary", ""),
            description=description,
            status=(fields.get("status", {}) or {}).get("name", ""),
            labels=[
                lbl if isinstance(lbl, str) else lbl.get("name", "")
                for lbl in (fields.get("labels") or [])
            ],
            assignee=_extract_assignee(fields),
            acceptance_criteria=_extract_acceptance_criteria(fields),
            raw=data,
        )


def _extract_text_from_adf(adf: dict | str | None) -> str:
    """Extract plain text from Atlassian Document Format JSON."""
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


def _extract_assignee(fields: dict) -> str | None:
    assignee = fields.get("assignee")
    if not assignee:
        return None
    if isinstance(assignee, str):
        return assignee
    return assignee.get("displayName") or assignee.get("emailAddress")


def _extract_acceptance_criteria(fields: dict) -> str | None:
    for field_name in ("acceptance_criteria", "customfield_10035", "customfield_10036"):
        val = fields.get(field_name)
        if val:
            return str(val)
    return None
