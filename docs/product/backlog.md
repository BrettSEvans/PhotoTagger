# Product Backlog

## Open (3)
- **[ARCHITECT]** Extend GET /health's ocr_ok self-test pattern with an analogous iptc_ok flag (exiftool -ver check at startup) so a missing exiftool install is visible immediately instead of manifesting as silently-skipped IPTC writes. (low)
- **[ARCHITECT]** If silent server-side-only IPTC write failure logging proves too invisible in practice, surface a soft warning in the assign/deassign response so the user can tell whether the embed actually happened. (low)
- **[ENGINEER]** Critic (architect p1): the GET /api/photos/<id>/metadata "people" array's per-face shape ({id, name, cluster_id, assigned}) is specified in the design spec but not co-located with the endpoint contract in 04-architecture.md §6 — cross-reference spec §2.1 directly when implementing photo_metadata.py and the two consuming components to avoid a shape mismatch. (low)

## Done (1)
- Critic (architect p1): remove the now-vestigial write_metadata param construction from web/src/api/photoTaggerClient.ts's assign call once the server-side flag is removed — dead code cleanup, not a functional break. (2026-07-31)

## Won't Fix (1)
- Critic (architect p1): guard the in-memory "backup already done" flag with the same lock used for iptc write serialization, so two near-simultaneous first-writes under Flask's threaded=True don't both trigger a redundant uploads_backup/ copy. (2026-07-31)
