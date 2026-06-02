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
# Filters background faces: <0.5 = background, 0.5-0.7 = acceptable, >0.7 = good
MIN_FACE_QUALITY_SCORE = 0.45
