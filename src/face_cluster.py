import logging
import numpy as np
from typing import List, Dict, Tuple
from src.db import Database

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
        all_faces = self.db.get_all_faces()

        if not all_faces:
            logger.warning("No faces in database. Run face detection first.")
            return {"clusters_created": 0, "faces_clustered": 0, "error": "No faces found"}

        logger.info(f"Clustering {len(all_faces)} faces...")

        # Clear existing clusters
        self.db.clear_clusters()

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
            # Pick the highest-confidence face as thumbnail
            thumbnail_face = max(face_list, key=lambda f: f["confidence"])

            cluster_id = self.db.add_player_cluster(
                face_count=len(face_list),
                photo_count=len(photo_ids),
                thumbnail_face_id=thumbnail_face["id"],
            )

            for face in face_list:
                self.db.assign_face_to_cluster(face["id"], cluster_id)
                total_faces += 1

        result = {
            "clusters_created": len(clusters),
            "faces_clustered": total_faces,
            "faces_total": len(all_faces),
        }
        logger.info(f"Clustering complete: {result}")
        return result
