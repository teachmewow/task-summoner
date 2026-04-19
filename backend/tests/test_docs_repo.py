"""Tests for ``docs_repo`` helpers (ENG-96 + ENG-98).

We exercise:
- frontmatter parsing edge cases
- ``list_decisions`` sort order + tag extraction
- ``read_rfc`` with and without a README
- ``rfc_image_path`` traversal guard

``list_decisions`` calls ``git log`` under the hood — tests initialise a real
git repo in ``tmp_path`` so the commit-time branch is exercised end-to-end.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from task_summoner.docs_repo import (
    DocsRepoError,
    list_decisions,
    parse_markdown,
    read_rfc,
    rfc_image_path,
)


@pytest.fixture(autouse=True)
def isolated_user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("TASK_SUMMONER_DOCS_REPO", raising=False)


def _make_docs_repo(root: Path) -> Path:
    repo = root / "docs-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / ".task-summoner").mkdir()
    (repo / ".task-summoner" / "config.yml").write_text("version: 1\n")
    (repo / "decisions").mkdir()
    (repo / "rfcs").mkdir()
    return repo


def _commit(repo: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", message],
        cwd=repo,
        check=True,
    )


def _configure_docs_repo(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TASK_SUMMONER_DOCS_REPO", str(repo))


class TestParseMarkdown:
    def test_extracts_title_and_first_paragraph(self):
        text = "# Hello\n\nThis is the first paragraph.\n\nSecond."
        parsed = parse_markdown(text)
        assert parsed.title == "Hello"
        assert parsed.summary == "This is the first paragraph."

    def test_frontmatter_summary_wins_over_body(self):
        text = "---\nsummary: From meta\n---\n# Ignored\n\nBody first para."
        parsed = parse_markdown(text)
        assert parsed.summary == "From meta"

    def test_tags_list_and_csv(self):
        a = parse_markdown("---\ntags: [alpha, beta]\n---\n# Title")
        b = parse_markdown("---\ntags: alpha, beta\n---\n# Title")
        assert a.tags == ["alpha", "beta"]
        assert b.tags == ["alpha", "beta"]

    def test_missing_frontmatter(self):
        parsed = parse_markdown("# Only heading\n")
        assert parsed.frontmatter == {}
        assert parsed.title == "Only heading"

    def test_malformed_frontmatter_returns_empty(self):
        # Invalid YAML with unmatched bracket — must not raise.
        parsed = parse_markdown("---\ntags: [oops\n---\n# Title\n")
        assert parsed.frontmatter == {}
        assert parsed.title == "Title"

    def test_fallback_title_used_when_no_h1(self):
        parsed = parse_markdown("Just plain text\n", fallback_title="stem")
        assert parsed.title == "stem"


class TestListDecisions:
    async def test_returns_entries_sorted_by_commit_time(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        repo = _make_docs_repo(tmp_path)
        _configure_docs_repo(repo, monkeypatch)

        (repo / "decisions" / "old.md").write_text("# Old\n\nOld decision.\n")
        _commit(repo, "old")
        # ensure distinct commit timestamps
        await asyncio.sleep(1.1)
        (repo / "decisions" / "new.md").write_text(
            "---\nsummary: Latest\ntags: [arch, mvp]\n---\n# New\n\nBody.\n"
        )
        _commit(repo, "new")

        entries = await list_decisions()
        assert [e.filename for e in entries] == ["new.md", "old.md"]
        assert entries[0].summary == "Latest"
        assert entries[0].tags == ["arch", "mvp"]
        assert entries[0].committed_at is not None

    async def test_empty_decisions_dir_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        repo = _make_docs_repo(tmp_path)
        _configure_docs_repo(repo, monkeypatch)
        entries = await list_decisions()
        assert entries == []

    async def test_limit_applied(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        repo = _make_docs_repo(tmp_path)
        _configure_docs_repo(repo, monkeypatch)
        for i in range(3):
            (repo / "decisions" / f"d{i}.md").write_text(f"# D{i}\n\nBody.\n")
            _commit(repo, f"d{i}")

        entries = await list_decisions(limit=2)
        assert len(entries) == 2

    async def test_untracked_file_included_at_bottom(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        repo = _make_docs_repo(tmp_path)
        _configure_docs_repo(repo, monkeypatch)

        (repo / "decisions" / "tracked.md").write_text("# Tracked\n")
        _commit(repo, "tracked")
        (repo / "decisions" / "draft.md").write_text("# Draft\n")
        # NOT committed.

        entries = await list_decisions()
        # tracked first (has commit), draft second (no commit)
        assert entries[0].filename == "tracked.md"
        assert entries[1].filename == "draft.md"
        assert entries[0].committed_at is not None
        assert entries[1].committed_at is None


class TestReadRfc:
    def test_returns_none_when_no_readme(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        repo = _make_docs_repo(tmp_path)
        _configure_docs_repo(repo, monkeypatch)
        assert read_rfc("ENG-99") is None

    def test_reads_readme_and_lists_images(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        repo = _make_docs_repo(tmp_path)
        _configure_docs_repo(repo, monkeypatch)
        rfc_dir = repo / "rfcs" / "ENG-98"
        rfc_dir.mkdir(parents=True)
        (rfc_dir / "README.md").write_text("# Render RFC\n\nBody.\n")
        (rfc_dir / "impact.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (rfc_dir / "not-an-image.txt").write_text("x")

        bundle = read_rfc("ENG-98")
        assert bundle is not None
        assert bundle.title == "Render RFC"
        assert bundle.images == ["impact.png"]
        assert bundle.content.startswith("# Render RFC")


class TestRfcImagePath:
    def test_valid_image(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        repo = _make_docs_repo(tmp_path)
        _configure_docs_repo(repo, monkeypatch)
        rfc_dir = repo / "rfcs" / "ENG-98"
        rfc_dir.mkdir(parents=True)
        img = rfc_dir / "impact.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")

        resolved = rfc_image_path("ENG-98", "impact.png")
        assert resolved == img

    def test_rejects_traversal(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        repo = _make_docs_repo(tmp_path)
        _configure_docs_repo(repo, monkeypatch)
        (repo / "rfcs" / "ENG-98").mkdir(parents=True)
        with pytest.raises(DocsRepoError):
            rfc_image_path("ENG-98", "../../etc/passwd")
        with pytest.raises(DocsRepoError):
            rfc_image_path("ENG-98", "nested/path.png")
        with pytest.raises(DocsRepoError):
            rfc_image_path("ENG-98", ".hidden.png")

    def test_missing_image(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        repo = _make_docs_repo(tmp_path)
        _configure_docs_repo(repo, monkeypatch)
        (repo / "rfcs" / "ENG-98").mkdir(parents=True)
        with pytest.raises(DocsRepoError):
            rfc_image_path("ENG-98", "gone.png")


class TestUnconfigured:
    def test_read_rfc_raises_when_docs_repo_unset(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("TASK_SUMMONER_DOCS_REPO", raising=False)
        with pytest.raises(DocsRepoError):
            read_rfc("ENG-99")

    async def test_list_decisions_raises_when_docs_repo_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("TASK_SUMMONER_DOCS_REPO", raising=False)
        with pytest.raises(DocsRepoError):
            await list_decisions()
