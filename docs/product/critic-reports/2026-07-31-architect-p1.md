TECHNICAL CRITIC REPORT — Architect — PhotoTagger

Artifact: docs/product/04-architecture.md
Reviewed against: docs/superpowers/specs/2026-07-30-photo-metadata-design.md,
  src/repositories/_base.py, src/repositories/batch.py, src/blueprints/review.py,
  src/schema.py, docs/ARCHITECTURE.md §7
Pass: 1 (single pass — engineer auto-applies; no second pass)
Status: ISSUES FOUND

Issues found:
- [Correctness & soundness] Concurrent-write race on a single photo file — significant — APPLY
- [Risk, scalability & operability] Synchronous 47MB backup blocks the first assign/unassign request — significant — APPLY
- [Oversights] In-memory backup-done flag isn't thread-safe under threaded=True — minor — DEFER
- [Seam & interface integrity] Frontend still sends write_metadata param the server will ignore — minor — DEFER
- [Seam & interface integrity] "people" section per-face JSON shape not fully specified in §6 — minor — DEFER

Action:
  Engineer auto-applies both APPLY findings without HITL review.
  DEFER findings go to backlog.md.
  HITL reviews the final result at QA.

---

## 1. Correctness & soundness — Concurrent-write race on a single photo file (significant, APPLY)

§4 Scenario B/C explicitly moves the `iptc_writer.write_iptc()` call **outside**
`self._lock` — correctly, to avoid the dashboard-polling-stall class of bug this
codebase already suffered once. But the architecture doesn't address what
protects the **file itself** once the DB lock is released.

Concretely: if a user assigns a face in photo #774 to Player A, then within the
same photo quickly unassigns a different face (Player B) — two plausible rapid
UI actions — both requests resolve their DB state under the lock, release it,
and then race to call `write_iptc()` against the *same JPEG file* concurrently.
Two exiftool subprocesses doing read-modify-write against the same file's
`PersonInImage` bag, each starting from a will-be-stale read, is a classic
lost-update race: one of the two name changes can silently disappear, or (worse,
if temp filenames aren't guaranteed unique per-call) two subprocesses could
collide on the same temp file path mid-write.

This isn't hypothetical for this specific feature — multi-face photos are the
documented common case (the design spec's own example photo has 10 tagged
faces), so two assign/unassign actions landing on the same file is a realistic
sequence, not an edge case.

**Fix:** add a lightweight **per-file-path lock** in `iptc_writer.py` (a
`defaultdict(threading.Lock)` keyed by resolved file path, or — simplest and
sufficient at this scale — a single process-wide `threading.Lock` serializing
all `write_iptc()` calls, since embed writes are already expected to be
infrequent, human-paced actions, not a hot path). This lock is independent of
`self._lock` (the DB lock) and must never be acquired while holding it, to avoid
introducing exactly the coupling §4's concurrency note is trying to prevent.
Also ensure the temp file name includes a random/unique suffix (not just the
target filename + `.tmp`) so even a near-simultaneous pair can't collide on the
same temp path.

## 2. Risk, scalability & operability — Synchronous backup blocks the first write (significant, APPLY)

§4 Scenario D and the Deltas table correctly make the one-time `uploads_backup/`
copy a hard precondition of the first embedded write. But the architecture
doesn't specify *where in the request lifecycle* that copy runs. As written, the
natural implementation is: user assigns their first face ever → assign endpoint
calls `write_iptc()` → `write_iptc()` (or a caller-side check) discovers no
backup exists → synchronously copies all 435 files (~47 MB) *inside that HTTP
request* before proceeding to the actual embed.

That's a multi-second (disk-speed-dependent) block on a single user-facing
request that has no relationship to "copy the whole photo library" — the user
just wanted to tag one face. This is exactly the kind of latency spike
`docs/ARCHITECTURE.md` §7 already documents Flask's `threaded=True` as
defending against for *other* endpoints (dashboard polling during upload); a
synchronous backup would reintroduce a similar-shaped stall for whichever
request happens to be first.

**Fix:** run the one-time backup through the existing async job pattern
(`app_job_runner.submit(...)`, already used for crawl/upload/OCR in
`src/blueprints/photos.py`) rather than inline in the assign/deassign request
path. Two viable placements, either is acceptable — engineer's choice: (a)
trigger it once at `local-agent` startup (before any assign is possible) so it's
always done by the time a user can act, or (b) trigger it as a fire-and-forget
job the *first* time an assign/deassign is attempted, and have that first
`write_iptc()` call wait on the job's completion rather than doing the copy
inline itself. Either way, the copy must not run as blocking work inside a
request handler.

## 3. Oversights — In-memory backup flag isn't thread-safe (minor, DEFER)

§4 Scenario D's "in-memory flag short-circuits repeat checks" is a plain
`bool`, checked-then-set with no lock, under a `threaded=True` Flask server. Two
near-simultaneous first-writes on different threads could both observe
"not yet backed up" and both kick off a redundant copy. The on-disk
`uploads_backup/` existence check is the real source of truth and prevents any
data problem, so this is not a correctness risk — just a wasted redundant I/O
pass in an already-rare (once-ever) scenario. Low enough impact for a
single-user local tool to defer; worth a one-line guard (check-then-set under
the same lock recommended in finding 1) if the engineer is already touching
that code path.

## 4. Seam & interface integrity — Frontend still sends write_metadata (minor, DEFER)

§7's ADR removes the server-side `write_metadata` request parameter from
`POST /api/players/<cluster_id>/assign`, but the architecture doesn't call out
that `web/src/api/photoTaggerClient.ts` (not reviewed in detail here) may still
construct that field on the client side from the pre-existing UI flow. Since the
server will simply ignore an unknown field, this isn't a breaking bug — but it's
dead code the engineer should clean up in the same pass rather than leaving a
misleading vestigial parameter in the client.

## 5. Seam & interface integrity — "people" section shape underspecified in §6 (minor, DEFER)

§6's Interfaces & contracts section references spec §3's table for
`GET /api/photos/<id>/metadata`'s response shape but doesn't restate the
per-face entry shape for the `people` array inline in the architecture doc
itself (spec has it: `{id, name, cluster_id, assigned}` per spec §2.1, listed
under Data Model & State's source module description, not co-located with the
endpoint contract in §6). Both `MetadataPanel.tsx` and `PhotoLightbox.tsx`
consume this shape, so a mismatch between what `photo_metadata.py` emits and
what the two components expect is a plausible integration bug if the engineer
works from §6 alone without cross-referencing the spec. Low risk since the spec
does have the shape, just not co-located — worth tightening if the doc is
revised for any other reason, not worth a standalone revision pass.
