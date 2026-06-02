import logging
import cv2
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

            img_h, img_w = img_array.shape[:2]
            img_area = img_w * img_h

            results = []
            for face in faces:
                # Extract bounding box and confidence
                bbox = face.bbox.astype(int).tolist()  # [x0, y0, x1, y1]
                embedding = face.embedding  # 384-dim vector
                confidence = face.det_score  # Detection confidence

                # Sharpness: Laplacian variance on the face crop (higher = sharper)
                x0, y0, x1, y1 = bbox
                x0c, y0c = max(0, x0), max(0, y0)
                x1c, y1c = min(img_w, x1), min(img_h, y1)
                sharpness = 0.0
                if x1c > x0c and y1c > y0c:
                    crop = img_array[y0c:y1c, x0c:x1c]
                    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
                    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

                # Face size ratio: fraction of image area covered by bbox
                face_area = max(0, x1 - x0) * max(0, y1 - y0)
                face_size_ratio = face_area / img_area if img_area > 0 else 0.0

                result = {
                    'embedding': embedding,
                    'bbox': bbox,
                    'confidence': float(confidence),
                    'sharpness': sharpness,
                    'face_size_ratio': face_size_ratio,
                    'age': int(face.age) if hasattr(face, 'age') and face.age is not None else None,
                    'gender': face.gender if hasattr(face, 'gender') else None,
                }

                # Compute quality score (filters background faces)
                result['quality_score'] = self.compute_face_quality_score(result, img_w, img_h)

                results.append(result)

            logger.info(f"Detected {len(faces)} face(s) in {path.name}")
            return results

        except Exception as e:
            logger.error(f"Error detecting faces in {image_path}: {e}")
            return []

    @staticmethod
    def compute_face_quality_score(face: Dict, img_width: int, img_height: int) -> float:
        """
        Compute a quality score (0-1) for a detected face to filter background/low-quality faces.

        Higher score = better quality / more likely to be main subject.
        Factors considered:
        - Detection confidence (higher is better)
        - Face size relative to image (larger is better, but huge is weird)
        - Sharpness (higher variance = sharper)
        - Position (centered faces score higher)

        Args:
            face: Face dict with 'confidence', 'sharpness', 'face_size_ratio', 'bbox'
            img_width: Image width in pixels
            img_height: Image height in pixels

        Returns:
            Quality score 0-1 (0.5+ is good quality)
        """
        confidence = face.get('confidence', 0.0)
        sharpness = face.get('sharpness', 0.0)
        size_ratio = face.get('face_size_ratio', 0.0)
        bbox = face.get('bbox', [0, 0, 0, 0])

        # Normalize confidence (already 0-1, just use it)
        conf_score = confidence

        # Size score: balance between background filtering and legitimate small subjects
        # Players can be small in wide shots (~2-5%) or large in closeups (>15%)
        # Tiny faces (<1%) are likely background crowd, not players
        if size_ratio < 0.01:
            size_score = 0.2  # Tiny crowd faces (needs high confidence to pass)
        elif size_ratio < 0.02:
            size_score = 0.4  # Very small - could be player or crowd
        elif size_ratio < 0.05:
            size_score = 0.7  # Small player at distance
        elif size_ratio <= 0.35:
            size_score = 1.0  # Optimal range for main subjects
        elif size_ratio <= 0.50:
            size_score = 0.85  # Getting large but still good
        else:
            size_score = 0.5  # Too large, probably cropped

        # Sharpness score: normalize to 0-1
        # Typical values: blurry ~5-50, medium ~100-500, sharp >1000
        if sharpness < 10:
            sharp_score = 0.1  # Very blurry
        elif sharpness < 50:
            sharp_score = 0.4  # Blurry (background)
        elif sharpness < 200:
            sharp_score = 0.7  # Decent
        else:
            sharp_score = 1.0  # Sharp

        # Position score: players can be off-center during action plays
        x0, y0, x1, y1 = bbox
        face_center_x = (x0 + x1) / 2.0 / img_width
        face_center_y = (y0 + y1) / 2.0 / img_height

        # Distance from center (0 = center, 0.5 = edge)
        dist_from_center = abs(face_center_x - 0.5) + abs(face_center_y - 0.5)

        if dist_from_center < 0.20:
            pos_score = 1.0  # Well centered
        elif dist_from_center < 0.35:
            pos_score = 0.9  # Off-center (action play)
        elif dist_from_center < 0.45:
            pos_score = 0.7  # Near edge
        else:
            pos_score = 0.4  # Corner (still might be player in wide shot)

        # Weighted average: size and sharpness are critical for filtering background
        # Confidence alone is not enough (background faces can be sharp and confident)
        quality_score = (
            conf_score * 0.25 +
            size_score * 0.45 +
            sharp_score * 0.20 +
            pos_score * 0.10
        )

        return min(1.0, max(0.0, quality_score))

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
