import logging
import numpy as np
from typing import List, Dict, Tuple
from src.db import Database
from src.config import MIN_FACE_SHARPNESS, MIN_FACE_SIZE_RATIO

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

        # Filter out blurry and small (background) faces
        quality_faces = [
            f for f in all_faces
            if (f.get("sharpness") or 0) >= MIN_FACE_SHARPNESS
            and (f.get("face_size_ratio") or 0) >= MIN_FACE_SIZE_RATIO
        ]
        logger.info(f"Quality filter: {len(all_faces)} → {len(quality_faces)} faces "
                    f"(removed {len(all_faces) - len(quality_faces)} blurry/small faces)")
        all_faces = quality_faces

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
