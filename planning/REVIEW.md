# Review Findings

## Findings

1. High - `PLAN.md` now documents an SSE contract that conflicts with the backend it says is already implemented and should be reused.
   Files: `planning/PLAN.md:7`, `planning/PLAN.md:197`, `planning/PLAN.md:199`, `planning/PLAN.md:203`, `planning/PLAN.md:207`
   Files: `backend/app/market/stream.py:30`, `backend/app/market/stream.py:33`, `backend/app/market/stream.py:62`, `backend/app/market/stream.py:83`, `backend/app/market/models.py:16`, `backend/app/market/models.py:32`, `backend/app/market/models.py:45`
   The new spec says the backend is already implemented and should be reused, but the SSE section now describes a different wire format: per-ticker `event: price` messages, ISO 8601 timestamps, `direction="unchanged"`, and `: heartbeat` comments. The actual implementation streams a single `data:` payload containing a map of all tickers, uses Unix timestamps, emits `direction="flat"`, and only sends the initial `retry:` directive. That mismatch will send downstream implementation toward either rewriting completed code unnecessarily or building clients against the wrong contract.

2. High - The updated setup docs require `.env.example`, but that file does not exist in the repository.
   Files: `README.md:74`, `planning/PLAN.md:123`, `planning/PLAN.md:141`
   Both the README quick start and the plan now treat `.env.example` as a committed bootstrap file. It is not present in the repo, so the first documented setup step fails immediately. This is a direct onboarding blocker for both users and agents.

3. Medium - The README now presents missing assets and directories as if they already exist.
   Files: `README.md:30`, `README.md:119`, `README.md:122`, `README.md:123`, `README.md:124`
   The new README references `planning/screenshots/workstation.png` and lists `frontend/`, `test/`, `scripts/`, and `db/` in the project layout, but none of those paths exist in the current tree. Because this README was rewritten as top-level project documentation rather than a future-state plan, these broken references make the repository look more complete than it is and create dead links/placeholders for readers.

4. Medium - The README quick start is now OS-specific and fails in the Windows environment this repo explicitly targets elsewhere.
   Files: `README.md:74`, `README.md:81`, `planning/PLAN.md:115`
   The setup snippet uses `cp` and `open`, which are not valid commands in standard PowerShell. That is a regression from a documentation standpoint because the plan explicitly calls out Windows support via PowerShell scripts, but the primary quick start no longer works there.

## Notes

- Scope reviewed: tracked changes against `HEAD` in `.gitignore`, `README.md`, and `planning/PLAN.md`.
- `.gitignore` change looks fine; no finding there.
- Untracked files, including `.claude/agents/`, were not reviewed as part of the requested diff scope.
- No tests were run; this review is based on diff inspection and repository state checks.
