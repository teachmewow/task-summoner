# Plan: ENG-190 — Add "✨ Smoke verified" one-liner to task-summoner README

## Ticket
- ID: ENG-190
- Linear: https://linear.app/teachmewow/issue/ENG-190/smoke-add-smoke-verified-one-liner-to-task-summoner-readme
- Parent: none
- Branch: ENG-190-smoke-add-smoke-verified
- Repo: task-summoner

## Scope
- In-scope:
  - Append exactly one blockquote line to the top-level `README.md`, placed immediately after the `**Local-first agentic board management.**` intro paragraph and before the ASCII lifecycle flow block.
  - The inserted line: `> ✨ **Smoke**: End-to-end pipeline verified via Linear + Claude Code dispatch.`
  - Exactly one blank line above and below the blockquote.
- Out-of-scope:
  - Any other `README.md` changes (badges, prose, lifecycle block, etc.)
  - Other files — this is a pure docs touch-up
  - Changelog entries, version bumps, test additions

## Implementation steps
1. Edit `README.md`: insert the blockquote line immediately after line 7 (`**Local-first agentic board management.**...` paragraph), before the `` ``` `` fence that opens the lifecycle ASCII diagram (currently line 9).
2. Ensure exactly one blank line above the blockquote (already present as line 8) and one blank line below (insert between the blockquote and the `` ``` `` fence).
3. Commit with message `feat(ENG-190): add Smoke verified one-liner to README`.
4. Open the code PR ready-for-review on branch `ENG-190-smoke-add-smoke-verified` targeting `main`.

## Files to create
- None

## Files to modify
- `README.md` — insert one blockquote line after the intro paragraph, before the lifecycle ASCII block (net +2 lines: the blockquote and the trailing blank line)

## Testing strategy
- No automated tests needed — pure docs change.
- Manual review: open the PR on GitHub; confirm the blockquote renders with the sparkle emoji, bolded "Smoke", and the rest of the sentence on one line.
- Confirm no other lines in `README.md` were altered (`git diff main -- README.md` shows a single `+` with the blockquote and one blank line, nothing else).

## Design patterns to follow
- Mirrors the blockquote-insertion pattern used by ENG-166 and ENG-164.
- Keep the emoji first, bolded keyword second, then the sentence — consistent with those precedents.

## Notes
- The worktree is already at `/private/tmp/task-summoner-workspaces/ENG-190` on branch `ENG-190-smoke-add-smoke-verified`.
- The branch is currently at the same commit as `main` (24ade25) — no divergence; a clean single-commit diff is guaranteed.
- The smoke acceptance criterion requires no retries: the entire FSM walk (`QUEUED → PLANNING → WAITING_PLAN_REVIEW → IMPLEMENTING → WAITING_MR_REVIEW → DONE`) must complete with one `lgtm` per gate and no `MANUAL_CHECK` banners.
