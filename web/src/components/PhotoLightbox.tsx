import React, { useState, useEffect, useRef } from 'react';
import photoTaggerClient from '../api/photoTaggerClient';
import type { JerseyDetection, FacesResponse, FaceInResponse } from '../types/index';
import { bboxStyle, analyzeBackgroundColor, ImgDim } from '../utils/bboxUtils';
import LoadingSpinner from './LoadingSpinner';

interface PhotoLightboxProps {
  photoId: number;
  onClose: () => void;
}

/**
 * PhotoLightbox - Full-screen photo viewer with:
 * - Face detection bboxes (linked to player clusters)
 * - Jersey number detection bboxes (linked to roster entries)
 * - Smart color selection (purple or fluorescent orange) based on background contrast
 * - Player name labels on each detection
 * - Filters to show only player faces (not background spectators)
 */

// Quality/jersey thresholds (match src/config.py)
const MIN_FACE_QUALITY_SCORE = 0.50;
const MIN_JERSEY_COLOR_CONF = 0.45;

/**
 * Determine if a face qualifies as a "player" (not background crowd).
 * A player must have: good quality score AND a detected jersey color.
 */
function isPlayerFace(face: FaceInResponse): boolean {
  const qualityScore = face.quality_score ?? 0;
  const jerseyConf = face.jersey_color_conf ?? 0;
  return qualityScore >= MIN_FACE_QUALITY_SCORE && face.jersey_color !== null && face.jersey_color !== undefined && jerseyConf >= MIN_JERSEY_COLOR_CONF;
}

export const PhotoLightbox: React.FC<PhotoLightboxProps> = ({ photoId, onClose }) => {
  const [allFaces, setAllFaces] = useState<FaceInResponse[]>([]);
  const [jerseyDetections, setJerseyDetections] = useState<JerseyDetection[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [imageDim, setImageDim] = useState<ImgDim | null>(null);
  const [bboxColors, setBboxColors] = useState<Map<string, string>>(new Map());
  const imageRef = useRef<HTMLImageElement>(null);

  // Filter to only player faces (not background)
  const playerFaces = allFaces.filter(isPlayerFace);

  // Load face and jersey detection data
  useEffect(() => {
    const loadDetections = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const [faceData, jerseyData] = await Promise.all([
          photoTaggerClient.getFaces(photoId),
          photoTaggerClient.getJerseyDetections(photoId),
        ]);
        setAllFaces(faceData.faces || []);
        setJerseyDetections(jerseyData || []);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load detections');
      } finally {
        setIsLoading(false);
      }
    };
    loadDetections();
  }, [photoId]);

  // Analyze background colors for all bboxes once image is loaded
  const handleImageLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    const width = img.naturalWidth;
    const height = img.naturalHeight;
    setImageDim({ w: width, h: height });

    const colors = new Map<string, string>();

    // Analyze player face bboxes only
    playerFaces.forEach((face, idx) => {
      const analysis = analyzeBackgroundColor(img, face.bbox);
      colors.set(`face-${face.id}`, analysis.isLowContrast || analysis.isPurplish ? 'orange' : 'purple');
    });

    // Analyze jersey bboxes
    jerseyDetections.forEach((jersey, idx) => {
      if (jersey.bbox) {
        const analysis = analyzeBackgroundColor(img, jersey.bbox);
        colors.set(`jersey-${jersey.id}`, analysis.isLowContrast || analysis.isPurplish ? 'orange' : 'purple');
      }
    });

    setBboxColors(colors);
  };

  // Close on Escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  if (isLoading) {
    return (
      <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
        <LoadingSpinner message="Loading photo…" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
        <div className="bg-white rounded-lg p-6 max-w-sm">
          <h2 className="font-outfit text-xl font-bold text-foreground mb-2">Error</h2>
          <p className="font-jakarta text-muted-fg mb-4">{error}</p>
          <button
            onClick={onClose}
            className="btn-candy bg-accent text-white px-4 py-2 rounded-lg"
          >
            Close
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      {/* Close button */}
      <button
        onClick={onClose}
        className="absolute top-4 right-4 z-10 bg-white rounded-full p-2 hover:bg-gray-100 transition-colors"
        aria-label="Close lightbox"
      >
        <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      {/* Photo container with relative positioning for overlays */}
      <div className="relative max-w-4xl max-h-[90vh] bg-white rounded-lg overflow-hidden">
        <img
          ref={imageRef}
          src={`http://127.0.0.1:5001/api/image/${photoId}`}
          alt="Full size photo"
          className="w-full h-auto block"
          onLoad={handleImageLoad}
        />

        {/* SVG overlay for bounding boxes */}
        {imageDim && (
          <svg
            className="absolute inset-0 w-full h-full"
            viewBox={`0 0 ${imageDim.w} ${imageDim.h}`}
            preserveAspectRatio="xMidYMid slice"
          >
            {/* Face detection bboxes - only players (not background spectators) */}
            {playerFaces.map((face) => {
              const color = bboxColors.get(`face-${face.id}`);
              const strokeClass = color === 'orange' ? 'stroke-[#FFA500]' : 'stroke-[#9333EA]';
              return (
                <g key={`face-${face.id}`}>
                  {/* Bounding box rectangle */}
                  <rect
                    x={face.bbox[0]}
                    y={face.bbox[1]}
                    width={face.bbox[2] - face.bbox[0]}
                    height={face.bbox[3] - face.bbox[1]}
                    fill="none"
                    stroke={color === 'orange' ? '#FF6600' : '#9333EA'}
                    strokeWidth="3"
                  />

                  {/* Label background and text */}
                  <g>
                    <rect
                      x={face.bbox[0]}
                      y={Math.max(face.bbox[1] - 32, 0)}
                      width="100"
                      height="28"
                      fill={color === 'orange' ? '#FFA500' : '#9333EA'}
                      opacity="0.9"
                      rx="4"
                    />
                    <text
                      x={face.bbox[0] + 5}
                      y={Math.max(face.bbox[1] - 10, 20)}
                      fill="white"
                      fontSize="12"
                      fontFamily="Arial, sans-serif"
                      fontWeight="600"
                    >
                      Face
                    </text>
                  </g>
                </g>
              );
            })}

            {/* Jersey detection bboxes */}
            {jerseyDetections.map((jersey) => {
              if (!jersey.bbox) return null;
              const color = bboxColors.get(`jersey-${jersey.id}`);
              return (
                <g key={`jersey-${jersey.id}`}>
                  {/* Bounding box rectangle */}
                  <rect
                    x={jersey.bbox[0]}
                    y={jersey.bbox[1]}
                    width={jersey.bbox[2] - jersey.bbox[0]}
                    height={jersey.bbox[3] - jersey.bbox[1]}
                    fill="none"
                    stroke={color === 'orange' ? '#FF6600' : '#9333EA'}
                    strokeWidth="3"
                  />

                  {/* Label background and text */}
                  <g>
                    <rect
                      x={jersey.bbox[0]}
                      y={Math.max(jersey.bbox[1] - 32, 0)}
                      width="120"
                      height="28"
                      fill={color === 'orange' ? '#FFA500' : '#9333EA'}
                      opacity="0.9"
                      rx="4"
                    />
                    <text
                      x={jersey.bbox[0] + 5}
                      y={Math.max(jersey.bbox[1] - 10, 20)}
                      fill="white"
                      fontSize="12"
                      fontFamily="Arial, sans-serif"
                      fontWeight="600"
                    >
                      #{jersey.jersey_number}
                    </text>
                  </g>
                </g>
              );
            })}
          </svg>
        )}

        {/* Detection stats footer - shows only player faces (not background spectators) */}
        <div className="absolute bottom-0 left-0 right-0 bg-black/70 text-white p-3 flex justify-between items-center">
          <div className="font-jakarta text-sm">
            {playerFaces.length > 0 && <span>{playerFaces.length} player{playerFaces.length !== 1 ? 's' : ''} detected</span>}
            {playerFaces.length > 0 && jerseyDetections.length > 0 && <span>, </span>}
            {jerseyDetections.length > 0 && <span>{jerseyDetections.length} jersey{jerseyDetections.length !== 1 ? 's' : ''} detected</span>}
            {playerFaces.length === 0 && jerseyDetections.length === 0 && <span>No detections</span>}
          </div>
          <button
            onClick={onClose}
            className="text-sm font-jakarta hover:underline"
          >
            Close (Esc)
          </button>
        </div>
      </div>
    </div>
  );
};

export default PhotoLightbox;
