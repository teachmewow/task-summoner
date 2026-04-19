"""RFC render API schemas (ENG-98)."""

from __future__ import annotations

from pydantic import BaseModel


class RfcResponse(BaseModel):
    """One RFC — markdown source + metadata for the viewer.

    The frontend renders markdown client-side (see ``marked`` in package.json),
    so we return the raw text rather than pre-rendered HTML. That keeps the
    backend dependency surface small and lets the UI style headings with
    tailwind classes consistently with the rest of the app.
    """

    ok: bool
    exists: bool
    issue_key: str
    title: str = ""
    content: str = ""
    readme_path: str = ""
    # Image filenames under the RFC dir. The UI builds URLs with
    # ``/api/rfcs/{issue_key}/image/{name}``.
    images: list[str] = []
    reason: str | None = None


__all__ = ["RfcResponse"]
