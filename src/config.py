# src/config.py
import multiprocessing
import os

# Face Detection
FACE_DETECTION_CONFIDENCE_THRESHOLD = 0.5
FACE_EMBEDDING_DIM = 384  # InsightFace default

# Parallel Processing
def get_optimal_worker_count():
    """
    Dynamically determine optimal worker count based on CPU.

    Strategy:
    - 1-4 CPUs: use 1 worker (avoid contention)
    - 5-8 CPUs: use cpu_count - 2 (leave headroom)
    - 8+ CPUs: use cpu_count - 3 (balance with system)
    """
    cpu_count = multiprocessing.cpu_count()

    if cpu_count <= 4:
        return 1
    elif cpu_count <= 8:
        return max(1, cpu_count - 2)
    else:
        return max(3, cpu_count - 3)

OPTIMAL_OCR_WORKERS = get_optimal_worker_count()
OCR_WORKER_TIMEOUT = 300  # 5 minutes per photo

# Batch Processing
BATCH_SIZE = 10
QUEUE_MAX_SIZE = 100

# Face quality filtering (applied before clustering)
# Minimum Laplacian variance of the face crop. Lower = blurrier. 0 disables.
# Note: photos are pre-downscaled (-sm), so sharpness values are lower than full-res.
MIN_FACE_SHARPNESS = 10.0
# Minimum face bbox area as a fraction of total image area.
# Photos are already -sm (576x384). Average detected face is ~16px wide (ratio ≈ 0.001).
# 0.0003 ≈ 8px-wide face in a 576px image — keeps foreground players, drops 4px noise.
MIN_FACE_SIZE_RATIO = 0.0003
# Minimum composite quality score (0-1) combining confidence, size, sharpness, and position
# Filters background crowd faces while allowing legitimate players at distance
# <0.45 = background crowd, 0.45-0.65 = players, >0.65 = high confidence players
MIN_FACE_QUALITY_SCORE = 0.50

# ── Jersey-color subject detection ─────────────────────────────────────────
# Per-game (per-folder) the two teams wear known jersey colors. A face wearing a
# team color is far more likely to be a player than a spectator. We sample the
# torso below each face, infer the two dominant team colors for the folder, then
# gate faces on (jersey color match) AND (foreground size).
#
# Minimum confidence for a sampled jersey color to count.
MIN_JERSEY_COLOR_CONF = 0.45
# "Foreground" is RELATIVE within each photo: a player in a wide shot is the same
# pixel-size as a spectator in a close shot, so absolute size alone can't separate
# them. We normalize each face against the largest team-jersey face in ITS photo.
# A team-colored face is kept if its size is at least this fraction of that max.
SUBJECT_REL_FRAC = 0.35
# Absolute size floor so a photo full of only tiny crowd faces doesn't keep noise,
# while still allowing genuine players in far/wide shots (faces ~0.0002 of frame).
SUBJECT_ABS_FLOOR = 0.00015
# A face NOT in a team color (spectator, ref, or a mis-sampled/occluded torso) must
# be a clearly large foreground subject to be kept.
NONTEAM_MIN_SIZE = 0.004
# Faces smaller than this are ignored when inferring the folder's team colors
# (tiny background torsos give unreliable color reads).
TEAM_INFER_MIN_SIZE = 0.01
# Colors that are usually shadows/shorts/skin rather than a distinguishing jersey
# color — excluded when inferring team colors.
TEAM_INFER_EXCLUDE_COLORS = {"black"}

# ── Cluster-level review filtering ─────────────────────────────────────────
# Which clusters are worth surfacing in the Review & Assign list. Two signals
# separate a real, taggable player from noise:
#   1) Recurrence — a player you'd tag appears across multiple photos. A cluster
#      seen in only one photo is almost always a one-off mis-detection ("zombie").
#   2) Prominence — a real player gets at least one close/foreground appearance,
#      so their cluster has at least one sizable face. A background person is never
#      the subject, so every face in their cluster stays tiny (e.g. cluster of all
#      0.0004–0.0012 faces). Their cluster's LARGEST face still falls below this.
# Already-assigned clusters (player_name set) are always shown regardless.
MIN_CLUSTER_PHOTOS = 2
MIN_CLUSTER_PROMINENCE = 0.002
