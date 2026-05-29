# Changelog

## 2026-05-29

- Hid ambiguous duplicate confirmed cards in the Upload UI when the same photo and jersey are returned with multiple player names.
  - Commit: c2dd21b
- Added active game context and team uniform colors so duplicate jersey numbers across teams are not auto-confirmed without a matching uniform color.
  - Commit: eb7a12e
- Made Flask backend debug mode opt-in so `python -m src.api` starts cleanly on port `5001` in restricted local environments.
  - Commit: 46f3c9e
- Started the local-hardening refactor with a stable baseline tag, resumable local processing jobs, job-returning processing endpoints, and stricter API validation for numeric inputs and crawl paths.
  - Commits: 808927c, 81a5024, f41172b, ce78cea, ea5f2be, 5fcd314, b231117, 408d305
- Linked cleanup assignments to stable roster entry IDs so roster faces populate from identified photos even when uniform colors or jersey numbers change across photo sets.
  - Commit: 416dc85
- Added confirmation prompts before Search and Cleanup removals, and delete empty cleanup clusters after their last face is removed.
  - Commit: 7cb3d46
- Updated the Search tab to hide face boxes and confidence percentages, and added controls to remove face-tagged photos from the current player.
  - Commit: fcf5871
- Added backend roster importing for CSV, TXT, Markdown, XLSX, PDF, and roster URLs; updated the Roster tab import UI and added player face thumbnails to roster rows.
  - Commit: 3bd3bd4
