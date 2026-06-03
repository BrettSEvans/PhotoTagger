import logging
import numpy as np
from typing import List, Dict, Tuple
from src.db import Database
from src.config import (
    MIN_FACE_SHARPNESS, MIN_FACE_SIZE_RATIO, MIN_FACE_QUALITY_SCORE,
    MIN_JERSEY_COLOR_CONF, SUBJECT_REL_FRAC, SUBJECT_ABS_FLOOR, NONTEAM_MIN_SIZE,
    TEAM_INFER_MIN_SIZE, TEAM_INFER_EXCLUDE_COLORS,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors. Returns -1 to 1."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class FaceClusterer:
    """
    Cluster detected faces into player identities using cosine similarity.

    Algorithm: greedy nearest-centroid clustering
    - For each face, find the existing cluster whose centroid is most similar
    - If similarity > threshold, assign to that cluster and update centroid
    - Otherwise, create a new cluster

    After clustering, auto-match clusters to roster players based on jersey numbers and colors.
    """

    def __init__(self, db: Database, similarity_threshold: float = 0.40):
        """
        Args:
            db: Database instance
            similarity_threshold: Minimum cosine similarity to join an existing cluster (0-1)
                                  Higher = stricter identity matching
        """
        self.db = db
        self.threshold = similarity_threshold

    def _resolve_team_colors(self, faces: List[Dict]) -> set:
        """
        Determine the two team jersey colors for this game.

        Manual game context wins if set; otherwise infer the two dominant jersey
        colors from the faces themselves, weighting each color vote by face size and
        color confidence (big, confident torsos are reliable; tiny ones are noise).
        """
        # Manual override from game context
        try:
            context = self.db.context.get_game_context()
            override = {
                str(t["uniform_color"]).strip().lower()
                for t in context
                if t.get("uniform_color")
            }
            if override:
                logger.info(f"Using team colors from game context: {sorted(override)}")
                return override
        except Exception as e:
            logger.debug(f"No game context available: {e}")

        # Auto-infer from sampled jersey colors
        votes: Dict[str, float] = {}
        for f in faces:
            color = f.get("jersey_color")
            conf = f.get("jersey_color_conf") or 0
            size = f.get("face_size_ratio") or 0
            if not color or conf < MIN_JERSEY_COLOR_CONF:
                continue
            if size < TEAM_INFER_MIN_SIZE:
                continue
            if color in TEAM_INFER_EXCLUDE_COLORS:
                continue
            votes[color] = votes.get(color, 0.0) + size * conf

        ranked = sorted(votes.items(), key=lambda kv: kv[1], reverse=True)
        logger.info(f"Inferred jersey color votes (size×conf weighted): {ranked}")
        return {color for color, _ in ranked[:2]}

    def _photo_team_max(self, faces: List[Dict], team_colors: set) -> Dict[int, float]:
        """
        Largest team-jersey face size per photo — the "foreground player" reference.

        Players are the largest team-colored faces in a shot; everyone else is judged
        relative to them. Falls back to the largest face of any color when a photo has
        no confident team-colored face.
        """
        team_max: Dict[int, float] = {}
        any_max: Dict[int, float] = {}
        for f in faces:
            pid = f.get("photo_id")
            size = f.get("face_size_ratio") or 0
            sharp = f.get("sharpness")
            if sharp is not None and sharp < MIN_FACE_SHARPNESS:
                continue
            any_max[pid] = max(any_max.get(pid, 0.0), size)
            color = f.get("jersey_color")
            conf = f.get("jersey_color_conf") or 0
            if color in team_colors and conf >= MIN_JERSEY_COLOR_CONF:
                team_max[pid] = max(team_max.get(pid, 0.0), size)
        # Fill photos with no team-colored face using their largest face
        for pid, m in any_max.items():
            team_max.setdefault(pid, m)
        return team_max

    def _is_subject(self, face: Dict, team_colors: set, photo_ref_size: float) -> bool:
        """
        Decide whether a face is a player (subject) vs background spectator.

        "Foreground" is relative: a team-colored face is kept when it's a large-enough
        fraction of the biggest team-jersey face in its own photo (plus a small
        absolute floor). A non-team color (spectator/ref) must be a clearly large
        foreground subject. A hard blur floor drops motion-blur smears.
        """
        size = face.get("face_size_ratio") or 0
        sharpness = face.get("sharpness")
        if sharpness is not None and sharpness < MIN_FACE_SHARPNESS:
            return False

        color = face.get("jersey_color")
        color_conf = face.get("jersey_color_conf") or 0
        in_team = bool(team_colors) and color in team_colors and color_conf >= MIN_JERSEY_COLOR_CONF

        if not team_colors:
            # No jersey-color signal at all (legacy/colorless data) — fall back to
            # pure geometry. Prefer the composite quality score; otherwise require
            # BOTH sharpness and size thresholds, treating missing values as failures.
            qs = face.get("quality_score")
            if qs is not None:
                return qs >= MIN_FACE_QUALITY_SCORE
            sharp_ok = (face.get("sharpness") or 0) >= MIN_FACE_SHARPNESS
            size_ok = (face.get("face_size_ratio") or 0) >= MIN_FACE_SIZE_RATIO
            return sharp_ok and size_ok

        if in_team:
            threshold = max(SUBJECT_ABS_FLOOR, SUBJECT_REL_FRAC * (photo_ref_size or 0))
            return size >= threshold
        # Non-team color: only keep if it's a large foreground face
        return size >= NONTEAM_MIN_SIZE

    def run(self) -> Dict:
        """
        Cluster all faces in the database into player groups.

        Returns:
            Dict with clustering statistics
        """
        logger.info("Loading all faces from database...")
        all_faces = self.db.faces.get_all_faces()

        if not all_faces:
            logger.warning("No faces in database. Run face detection first.")
            return {"clusters_created": 0, "faces_clustered": 0, "error": "No faces found"}

        logger.info(f"Clustering {len(all_faces)} faces...")

        # ── Subject detection: keep players, drop background spectators ──────────
        # For this folder, the two teams wear known jersey colors. A face wearing a
        # team color is very likely a player; we trust it at a lower size bar. A face
        # in a non-team color (spectator) must be a clearly large foreground subject.
        team_colors = self._resolve_team_colors(all_faces)
        logger.info(f"Team colors for this game: {sorted(team_colors) or '(none — geometry only)'}")

        team_max = self._photo_team_max(all_faces, team_colors)
        subject_faces = [
            f for f in all_faces
            if self._is_subject(f, team_colors, team_max.get(f.get("photo_id"), 0.0))
        ]

        logger.info(f"Subject filter: {len(all_faces)} → {len(subject_faces)} faces "
                    f"(dropped {len(all_faces) - len(subject_faces)} background/spectator faces)")
        all_faces = subject_faces

        if not all_faces:
            logger.warning("No faces passed quality filter.")
            return {"clusters_created": 0, "faces_clustered": 0, "error": "No faces passed quality filter"}

        # Clear existing clusters
        self.db.clusters.clear_clusters()

        # Greedy nearest-centroid clustering
        # clusters: List of (centroid np.ndarray, List[face_dict], set of photo_ids)
        clusters: List[Tuple[np.ndarray, List[Dict], set]] = []

        for face in all_faces:
            emb = np.array(face["embedding"], dtype=np.float32)

            best_idx = -1
            best_sim = self.threshold  # Only join if above threshold

            for i, (centroid, _, _) in enumerate(clusters):
                sim = cosine_similarity(emb, centroid)
                if sim > best_sim:
                    best_sim = sim
                    best_idx = i

            if best_idx >= 0:
                # Join existing cluster, update centroid (running average)
                centroid, face_list, photo_ids = clusters[best_idx]
                face_list.append(face)
                photo_ids.add(face["photo_id"])
                n = len(face_list)
                new_centroid = (centroid * (n - 1) + emb) / n
                clusters[best_idx] = (new_centroid, face_list, photo_ids)
            else:
                # New cluster
                clusters.append((emb, [face], {face["photo_id"]}))

        # Persist clusters to database
        total_faces = 0
        for centroid, face_list, photo_ids in clusters:
            # Pick the sharpest face as thumbnail (best identity representation)
            thumbnail_face = max(face_list, key=lambda f: f.get("sharpness") or 0)

            cluster_id = self.db.clusters.add_player_cluster(
                face_count=len(face_list),
                photo_count=len(photo_ids),
                thumbnail_face_id=thumbnail_face["id"],
            )

            for face in face_list:
                self.db.clusters.assign_face_to_cluster(face["id"], cluster_id)
                total_faces += 1

        # Auto-match clusters to roster players
        auto_matched = self._auto_match_clusters()

        result = {
            "clusters_created": len(clusters),
            "faces_clustered": total_faces,
            "faces_total": len(all_faces),
            "auto_matched": auto_matched,
        }
        logger.info(f"Clustering complete: {result}")
        return result

    def _auto_match_clusters(self) -> int:
        """
        Auto-match clusters to roster players based on jersey numbers and colors.

        For each cluster, analyzes detected jersey numbers and matches to roster entries.
        If a match is found with high confidence, auto-assigns the cluster to the player.

        Returns: Number of clusters auto-matched
        """
        matched_count = 0
        try:
            clusters = self.db.clusters.get_all_player_clusters()

            for cluster in clusters:
                if cluster.get("player_name"):
                    # Already assigned, skip
                    continue

                cluster_id = cluster["id"]

                # Get all photos in this cluster
                photos = self.db.clusters.get_photos_by_cluster(cluster_id, min_face_confidence=0.0)
                if not photos:
                    continue

                # Fetch the latest OCR row for every photo in the cluster in one query
                # (avoids an N+1 lookup per photo).
                ocr_by_photo = self.db.photos.get_latest_ocr_by_photo_ids([p["id"] for p in photos])

                # Collect jersey numbers and colors from OCR results
                jersey_candidates = {}  # jersey -> count
                color_samples = []

                for photo in photos:
                    ocr = ocr_by_photo.get(photo["id"])
                    if not ocr or not ocr.get("jersey_number"):
                        continue

                    jersey = str(ocr["jersey_number"]).strip()
                    if jersey:
                        jersey_candidates[jersey] = jersey_candidates.get(jersey, 0) + 1

                    if ocr.get("uniform_color"):
                        color_samples.append(ocr["uniform_color"])

                if not jersey_candidates:
                    continue

                # Find most common jersey number
                most_common_jersey = max(jersey_candidates, key=jersey_candidates.get)
                common_count = jersey_candidates[most_common_jersey]
                photo_count = len(photos)
                confidence = common_count / photo_count if photo_count > 0 else 0

                # Only auto-match if jersey appears in 80%+ of photos in cluster
                if confidence < 0.80:
                    logger.debug(f"Cluster {cluster_id}: jersey #{most_common_jersey} confidence only {confidence:.1%}")
                    continue

                # Get the most common color (for matching)
                most_common_color = max(color_samples, key=color_samples.count) if color_samples else None

                # Resolve roster candidates
                candidates = self.db.roster.resolve_roster_candidates(most_common_jersey, most_common_color)

                if not candidates:
                    logger.debug(f"Cluster {cluster_id}: no roster match for jersey #{most_common_jersey}")
                    continue

                if len(candidates) > 1:
                    # Multiple candidates - use color matching to narrow down
                    if most_common_color:
                        candidates = [c for c in candidates if c.get("match_score", 0) > 0]

                    if not candidates or len(candidates) > 1:
                        logger.debug(f"Cluster {cluster_id}: ambiguous match for jersey #{most_common_jersey} ({len(candidates)} candidates)")
                        continue

                # Auto-assign the cluster to the matched player
                candidate = candidates[0]
                try:
                    self.db.clusters.assign_cluster_to_player(
                        cluster_id,
                        candidate["player_name"],
                        candidate["jersey_number"],
                        candidate["id"]  # roster_entry_id
                    )
                    logger.info(f"Auto-matched cluster {cluster_id} to {candidate['player_name']} (#{candidate['jersey_number']}) with {confidence:.1%} jersey confidence")
                    matched_count += 1
                except Exception as e:
                    logger.warning(f"Failed to auto-assign cluster {cluster_id}: {e}")

            return matched_count
        except Exception as e:
            logger.error(f"Auto-matching error: {e}")
            return 0
