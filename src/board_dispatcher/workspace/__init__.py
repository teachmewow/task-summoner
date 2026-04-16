"""Git workspace management — worktree lifecycle per ticket."""

from .manager import GitWorkspaceManager, derive_branch_name

__all__ = ["GitWorkspaceManager", "derive_branch_name"]
