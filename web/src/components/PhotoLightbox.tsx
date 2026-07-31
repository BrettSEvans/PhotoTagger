import React, { useState, useEffect, useRef, useCallback } from 'react';
import photoTaggerClient from '../api/photoTaggerClient';
import type { JerseyDetection, FaceInResponse, PhotoMetadata } from '../types/index';
import { bboxStyle, analyzeBackgroundColor, ImgDim } from '../utils/bboxUtils';
import { placeLabels } from '../utils/labelPlacement';
import { MetadataPanel } from './MetadataPanel';
import LoadingSpinner from './LoadingSpinner';

interface PhotoLightboxProps {
  photoId: number;
  onClose: () => void;
}

/**
 * PhotoLightbox — full-screen photo viewer (feature #1) with:
 * - a right-side metadata panel (file, image, library, jersey/OCR, game, people)
 * - adaptive player-name labels / numbered pins / leader lines (feature #3)
 * - independent Names/Boxes visibility toggles (feature #4)
 * - jersey number detection overlay (unchanged from prior behavior)
 */

// Quality/jersey thresholds (match src/config.py — see photo_metadata.py's
// server-side isPlayerFace, which this mirrors so the panel's people count
// always matches what's actually drawn on the photo).
const MIN_FACE_QUALITY_SCORE = 0.50;
const MIN_JERSEY_COLOR_CONF = 0.45;

function isPlayerFace(face: FaceInResponse): boolean {
  const qualityScore = face.quality_score ?? 0;
  const jerseyConf = face.jersey_color_conf ?? 0;
  return qualityScore >= MIN_FACE_QUALITY_SCORE && face.jersey_color !== null && face.jersey_color !== undefined && jerseyConf >= MIN_JERSEY_COLOR_CONF;
}

export const PhotoLightbox: React.FC<PhotoLightboxProps> = ({ photoId, onClose }) => {
  const [allFaces, setAllFaces] = useState<FaceInResponse[]>([]);
  const [jerseyDetections, setJerseyDetections] = useState<JerseyDetection[]>([]);
  const [metadata, setMetadata] = useState<PhotoMetadata | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isMetadataLoading, setIsMetadataLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [imageDim, setImageDim] = useState<ImgDim | null>(null);
  const [bboxColors, setBboxColors] = useState<Map<string, string>>(new Map());
  const [showNames, setShowNames] = useState(true);
  const [showBoxes, setShowBoxes] = useState(true);
  const [hoveredPersonId, setHoveredPersonId] = useState<number | null>(null);
  const imageRef = useRef<HTMLImageElement>(null);

  const playerFaces = allFaces.filter(isPlayerFace);

  const loadMetadata = useCallback(async () => {
    setIsMetadataLoading(true);
    try {
      setMetadata(await photoTaggerClient.getPhotoMetadata(photoId));
    } catch {
      setMetadata(null);
    } finally {
      setIsMetadataLoading(false);
    }
  }, [photoId]);

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
    loadMetadata();
  }, [photoId, loadMetadata]);

  const handleImageLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    const width = img.naturalWidth;
    const height = img.naturalHeight;
    setImageDim({ w: width, h: height });

    const colors = new Map<string, string>();
    playerFaces.forEach((face) => {
      const analysis = analyzeBackgroundColor(img, face.bbox);
      colors.set(`face-${face.id}`, analysis.isLowContrast || analysis.isPurplish ? 'orange' : 'purple');
    });
    jerseyDetections.forEach((jersey) => {
      if (jersey.bbox) {
        const analysis = analyzeBackgroundColor(img, jersey.bbox);
        colors.set(`jersey-${jersey.id}`, analysis.isLowContrast || analysis.isPurplish ? 'orange' : 'purple');
      }
    });
    setBboxColors(colors);
  };

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  // Names map for the placement solver: face_id -> player name, sourced from
  // the metadata panel's People list (server-filtered the same way as
  // playerFaces above, so the two always agree on which faces are "players").
  const names: Record<number, string> = {};
  for (const person of metadata?.people ?? []) {
    if (person.assigned && person.name) names[person.id] = person.name;
  }

  const placement = imageDim
    ? placeLabels(
        playerFaces.map((f) => ({ id: f.id, x: f.bbox[0], y: f.bbox[1], width: f.bbox[2] - f.bbox[0], height: f.bbox[3] - f.bbox[1] })),
        names,
        imageDim.w,
        imageDim.h,
      )
    : { labels: [], pins: [], lines: [] };

  const handleAssigned = () => {
    loadMetadata();
  };

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
          <button onClick={onClose} className="btn-candy bg-accent text-white px-4 py-2 rounded-lg">
            Close
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <button
        onClick={onClose}
        className="absolute top-4 right-4 z-10 bg-white rounded-full p-2 hover:bg-gray-100 transition-colors"
        aria-label="Close lightbox"
      >
        <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      <div className="w-full max-w-6xl max-h-[90vh] bg-white rounded-lg overflow-hidden flex flex-col md:flex-row">
        <div className="relative flex-1 bg-black flex items-center min-w-0">
          <img
            ref={imageRef}
            src={`http://127.0.0.1:5001/api/image/${photoId}`}
            alt="Full size photo"
            className="w-full h-auto block"
            onLoad={handleImageLoad}
          />

          {imageDim && (
            <svg
              className="absolute inset-0 w-full h-full"
              viewBox={`0 0 ${imageDim.w} ${imageDim.h}`}
              preserveAspectRatio="xMidYMid slice"
            >
              {showBoxes && (
                <g>
                  {playerFaces.map((face) => {
                    const color = bboxColors.get(`face-${face.id}`);
                    return (
                      <rect
                        key={`face-box-${face.id}`}
                        x={face.bbox[0]}
                        y={face.bbox[1]}
                        width={face.bbox[2] - face.bbox[0]}
                        height={face.bbox[3] - face.bbox[1]}
                        fill="none"
                        stroke={color === 'orange' ? '#FF6600' : '#9333EA'}
                        strokeWidth="3"
                        opacity={hoveredPersonId !== null && hoveredPersonId !== face.id ? 0.35 : 1}
                      />
                    );
                  })}
                  {jerseyDetections.map((jersey) => {
                    if (!jersey.bbox) return null;
                    const color = bboxColors.get(`jersey-${jersey.id}`);
                    return (
                      <g key={`jersey-${jersey.id}`}>
                        <rect
                          x={jersey.bbox[0]}
                          y={jersey.bbox[1]}
                          width={jersey.bbox[2] - jersey.bbox[0]}
                          height={jersey.bbox[3] - jersey.bbox[1]}
                          fill="none"
                          stroke={color === 'orange' ? '#FF6600' : '#9333EA'}
                          strokeWidth="3"
                        />
                        <rect
                          x={jersey.bbox[0]}
                          y={Math.max(jersey.bbox[1] - 32, 0)}
                          width="60"
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
                    );
                  })}
                </g>
              )}

              {showNames && (
                <g>
                  <g stroke="#9333EA" strokeWidth="1.1" opacity="0.8">
                    {placement.lines.map((line, idx) => {
                      const pin = placement.pins.find((p) => p.id === line.fromId);
                      if (!pin) return null;
                      return <line key={idx} x1={pin.x} y1={pin.y} x2={line.toX} y2={line.toY} />;
                    })}
                  </g>
                  <g fontFamily="Inter, Arial, sans-serif" fontSize="9" fontWeight="700">
                    {placement.labels.map((label) => (
                      <g key={`label-${label.id}`} opacity={hoveredPersonId !== null && hoveredPersonId !== label.id ? 0.4 : 1}>
                        <rect x={label.x} y={label.y} width={label.width} height={label.height} rx="2" fill="#9333EA" />
                        <text x={label.x + 3} y={label.y + label.height - 3} fill="white">
                          {label.name}
                        </text>
                      </g>
                    ))}
                    {placement.pins.map((pin) => (
                      <g key={`pin-${pin.id}`} opacity={hoveredPersonId !== null && hoveredPersonId !== pin.id ? 0.4 : 1}>
                        <circle cx={pin.x} cy={pin.y} r="8" fill="#9333EA" />
                        <text x={pin.x} y={pin.y + 3} fill="white" textAnchor="middle">
                          {pin.number}
                        </text>
                      </g>
                    ))}
                  </g>
                </g>
              )}
            </svg>
          )}
        </div>

        <MetadataPanel
          metadata={metadata}
          isLoading={isMetadataLoading}
          showNames={showNames}
          showBoxes={showBoxes}
          onToggleNames={() => setShowNames((v) => !v)}
          onToggleBoxes={() => setShowBoxes((v) => !v)}
          onAssigned={handleAssigned}
          hoveredPersonId={hoveredPersonId}
          onHoverPerson={setHoveredPersonId}
        />
      </div>
    </div>
  );
};

export default PhotoLightbox;
