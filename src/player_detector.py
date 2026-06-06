import cv2
import numpy as np
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from insightface.app import FaceAnalysis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PlayerDetector:
    """Detect players vs spectators by face location and uniform analysis."""

    def __init__(self):
        """Initialize face detector."""
        logger.info("Initializing PlayerDetector with face detection")
        try:
            self.face_detector = FaceAnalysis(
                name='buffalo_l',
                providers=['CPUExecutionProvider']
            )
            self.face_detector.prepare(ctx_id=0, det_size=(640, 640))
            self.initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize face detector: {e}")
            self.initialized = False

    def detect_players(self, image_path: str) -> Optional[List[Dict]]:
        """
        Detect all people in photo and classify as player or spectator.

        Uses face detection + vertical position heuristic:
        - Players: Upper 70% of image (on field)
        - Sideline: 70-85% (on sideline)
        - Background/Spectators: Bottom 15% (in stands)

        Returns:
            List of detected people with:
            {
                'face_id': int,
                'bbox': [x0, y0, x1, y1],
                'bbox_expanded': [x0, y0, x1, y1],  # Expanded to include body
                'center_x': float,
                'center_y': float,
                'relative_y': float (0.0 to 1.0),
                'location': 'field' | 'sideline' | 'background',
                'location_confidence': float (0.0-1.0),
                'embedding': np.array (512-dimensional),
            }
        """
        if not self.initialized:
            logger.error("PlayerDetector not initialized")
            return None

        try:
            path = Path(image_path)
            if not path.exists():
                logger.error(f"Image not found: {image_path}")
                return None

            img = cv2.imread(str(image_path))
            if img is None:
                logger.error(f"Failed to read image: {image_path}")
                return None

            height, width = img.shape[:2]
            logger.debug(f"Processing image: {width}x{height}")

            # Detect faces
            faces = self.face_detector.get(img)
            if not faces:
                logger.debug("No faces detected in image")
                return []

            logger.debug(f"Detected {len(faces)} face(s)")

            players = []
            for face_idx, face in enumerate(faces):
                # Extract face bounding box
                bbox = face.bbox.astype(int).tolist()
                x0, y0, x1, y1 = bbox

                # Calculate center
                center_x = (x0 + x1) / 2
                center_y = (y0 + y1) / 2
                relative_y = center_y / height

                # Expand bbox to include body (face is ~30% of body height)
                face_height = y1 - y0
                body_height = int(face_height * 3.5)  # Face is ~30% of body
                expanded_y0 = max(0, y0 - face_height)  # Add space above
                expanded_y1 = min(height, y0 + body_height)  # Extend below
                expanded_x0 = max(0, x0 - int(face_height * 0.5))
                expanded_x1 = min(width, x1 + int(face_height * 0.5))

                bbox_expanded = [expanded_x0, expanded_y0, expanded_x1, expanded_y1]

                # Classify location based on vertical position.
                # Thresholds (0.70 / 0.85) were calibrated for field-level Ultimate
                # Frisbee tournament photos where the playing field fills the upper ~70%.
                location, location_conf = self._classify_location(relative_y, height)

                player_info = {
                    'face_id': face_idx,
                    'bbox': bbox,  # Face bounding box
                    'bbox_expanded': bbox_expanded,  # Body region for jersey extraction
                    'center_x': center_x,
                    'center_y': center_y,
                    'relative_y': relative_y,
                    'location': location,
                    'location_confidence': location_conf,
                    'embedding': face.embedding,  # Face embedding for potential matching
                }

                players.append(player_info)

                logger.debug(
                    f"Face {face_idx}: location={location} ({location_conf:.1%}), "
                    f"y_pos={relative_y:.1%}"
                )

            logger.info(f"Detected {len(players)} potential players/people")
            return players

        except Exception as e:
            logger.error(f"Error detecting players in {image_path}: {e}")
            return None

    def filter_field_players(self, people: List[Dict]) -> List[Dict]:
        """
        Filter to only on-field players.

        Removes spectators and sideline personnel.

        Args:
            people: Output from detect_players()

        Returns:
            List of people classified as 'field' players
        """
        if not people:
            return []

        field_players = [p for p in people if p['location'] == 'field']
        logger.info(
            f"Filtered {len(people)} people → {len(field_players)} field players"
        )
        return field_players

    def filter_by_location(
        self,
        people: List[Dict],
        location: str
    ) -> List[Dict]:
        """
        Filter people by location type.

        Args:
            people: Output from detect_players()
            location: 'field', 'sideline', or 'background'

        Returns:
            Filtered list
        """
        return [p for p in people if p['location'] == location]

    def _classify_location(self, relative_y: float, image_height: int) -> Tuple[str, float]:
        """
        Classify person location based on vertical position.

        Heuristic:
        - y < 0.70: On field (players)
        - 0.70 <= y < 0.85: Sideline (coaches, staff)
        - y >= 0.85: Background/Stands (spectators)

        Args:
            relative_y: Vertical position as fraction (0.0 to 1.0)
            image_height: Image height in pixels

        Returns:
            (location_name, confidence)
        """
        if relative_y < 0.70:
            location = 'field'
            # Confidence increases as we move up (more confident about field positions)
            confidence = 1.0 - (relative_y * 0.2)  # 1.0 at top, 0.86 at 0.7
        elif relative_y < 0.85:
            location = 'sideline'
            # Lower confidence for sideline (ambiguous region)
            confidence = 0.6
        else:
            location = 'background'
            # High confidence for background (stands are clearly at bottom)
            confidence = 0.95 - ((1.0 - relative_y) * 0.3)  # 0.95 at bottom

        return location, confidence

    def visualize_detections(
        self,
        image_path: str,
        people: List[Dict],
        output_path: str = None
    ) -> Optional[np.ndarray]:
        """
        Draw detected people on image for visualization.

        Args:
            image_path: Input image
            people: Output from detect_players()
            output_path: Optional path to save visualization

        Returns:
            Annotated image array
        """
        img = cv2.imread(str(image_path))
        if img is None:
            return None

        # Color by location
        location_colors = {
            'field': (0, 255, 0),  # Green for field players
            'sideline': (0, 165, 255),  # Orange for sideline
            'background': (0, 0, 255),  # Red for spectators
        }

        for person in people:
            # Draw face bbox
            x0, y0, x1, y1 = person['bbox']
            color = location_colors[person['location']]
            cv2.rectangle(img, (x0, y0), (x1, y1), color, 2)

            # Draw expanded body bbox (dashed)
            ex0, ey0, ex1, ey1 = person['bbox_expanded']
            cv2.rectangle(img, (ex0, ey0), (ex1, ey1), color, 1)

            # Label
            label = f"{person['location']} {person['location_confidence']:.0%}"
            cv2.putText(
                img,
                label,
                (x0, y0 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2
            )

        if output_path:
            cv2.imwrite(str(output_path), img)
            logger.info(f"Saved visualization to {output_path}")

        return img
