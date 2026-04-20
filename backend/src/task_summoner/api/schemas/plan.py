"""Plan render API schemas.

Mirror of ``RfcResponse`` for the planning-phase artifact (``plan.md`` in
``artifacts/<issue-key>/``). Kept as a separate schema rather than a shared
"markdown artifact" type because plan.md has no image sidecars and lives on
a completely different filesystem root — the shared surface is the
frontend component, not the wire model.
"""

from __future__ import annotations

from pydantic import BaseModel


class PlanResponse(BaseModel):
    """One plan — markdown source + metadata for the viewer."""

    ok: bool
    exists: bool
    issue_key: str
    title: str = ""
    content: str = ""
    plan_path: str = ""
    reason: str | None = None


__all__ = ["PlanResponse"]
