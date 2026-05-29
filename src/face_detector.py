import logging
import numpy as np
from typing import List, Dict, Tuple
from pathlib import Path
import insightface
from insightface.app import FaceAnalysis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FaceDetector:
    """Detect faces and extract embeddings using InsightFace."""

    def __init__(self, model_name: str = "buffalo_l", allowed_modules=None):
        """
        Initialize face detector.

        Args:
            model_name: InsightFace model (buffalo_l is most accurate)
            allowed_modules: Which modules to load (default: detection + recognition)
        """
        logger.info(f"Initializing FaceDetector with model: {model_name}")

        if allowed_modules is None:
            allowed_modules = ['detection', 'recognition']

        self.app = FaceAnalysis(
            name=model_name,
            providers=['CPUExecutionProvider'],  # Use CPU for compatibility
            allowed_modules=allowed_modules
        )
        self.app.prepare(ctx_id=0, det_size=(640, 640))
        self.model = self.app

    def detect_faces(self, image_path: str) -> List[Dict]:
        """
        Detect all faces in an image and extract embeddings.

        Args:
            image_path: Path to image file

        Returns:
            List of dicts: {
                'embedding': np.array (384-dim),
                'bbox': [x0, y0, x1, y1],
                'confidence': float (0-1),
                'age': int,
                'gender': str
            }
        """
        try:
            from PIL import Image

            path = Path(image_path)
            if not path.exists():
                logger.error(f"Image not found: {image_path}")
                return []

            # Load image
            img = Image.open(image_path).convert('RGB')
            img_array = np.array(img)

            # Detect faces
            logger.debug(f"Detecting faces in: {image_path}")
            faces = self.app.get(img_array)

            if not faces:
                logger.debug(f"No faces detected in {image_path}")
                return []

            results = []
            for face in faces:
                # Extract bounding box and confidence
                bbox = face.bbox.astype(int).tolist()  # [x0, y0, x1, y1]
                embedding = face.embedding  # 384-dim vector
                confidence = face.det_score  # Detection confidence

                result = {
                    'embedding': embedding,
                    'bbox': bbox,
                    'confidence': float(confidence),
                    'age': int(face.age) if hasattr(face, 'age') and face.age is not None else None,
                    'gender': face.gender if hasattr(face, 'gender') else None,
                }
                results.append(result)

            logger.info(f"Detected {len(faces)} face(s) in {path.name}")
            return results

        except Exception as e:
            logger.error(f"Error detecting faces in {image_path}: {e}")
            return []

    @staticmethod
    def embedding_distance(emb1: np.ndarray, emb2: np.ndarray) -> float:
        """
        Compute L2 distance between two embeddings.

        Lower distance = more similar faces
        Typical threshold: 0.4-0.5 for same person
        """
        return float(np.linalg.norm(emb1 - emb2))

    def cluster_faces_by_similarity(self, faces: List[Dict], threshold: float = 0.5) -> List[List[int]]:
        """
        Cluster faces by similarity (simple single-linkage clustering).

        Args:
            faces: List of face dicts with 'embedding'
            threshold: Distance threshold for clustering

        Returns:
            List of clusters (each cluster is list of face indices)
        """
        if not faces:
            return []

        clusters = []
        used = set()

        for i, face_i in enumerate(faces):
            if i in used:
                continue

            cluster = [i]
            used.add(i)

            for j, face_j in enumerate(faces):
                if j in used:
                    continue

                dist = self.embedding_distance(face_i['embedding'], face_j['embedding'])
                if dist < threshold:
                    cluster.append(j)
                    used.add(j)

            clusters.append(cluster)

        return clusters
