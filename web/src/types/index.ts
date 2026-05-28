/**
 * PhotoTagger TypeScript Type Definitions
 * Complete type safety for frontend-backend communication
 */

/**
 * Photo - Photo data from database
 */
export interface Photo {
  id: number;
  file_path: string;
  file_hash: string;
  file_size: number;
  created_at: string;
  ingested_at: string;
}

/**
 * OCRResult - Jersey number extraction result
 */
export interface OCRResult {
  id: number;
  photo_id: number;
  jersey_number: string | null;
  confidence: number;
  raw_text: string;
  processed_at: string;
}

/**
 * BoundingBox - Coordinates for a rectangular region
 * Format: [x0, y0, x1, y1]
 */
export type BoundingBox = [number, number, number, number];

/**
 * DetectedFace - Face detection result from photo
 * Includes 512-dimensional embedding from InsightFace
 */
export interface DetectedFace {
  id: number;
  photo_id: number;
  bbox: BoundingBox;
  confidence: number;
  embedding: number[]; // 512-dimensional vector
  detected_at?: string;
}

/**
 * IdentifiedPlayer - Identified player from multi-factor matching
 * Combines jersey OCR, color detection, location classification, and roster lookup
 */
export interface IdentifiedPlayer {
  jersey_number: string | null;
  jersey_confidence: number;
  color: string;
  color_confidence: number;
  location: 'field' | 'sideline' | 'background';
  location_confidence: number;
  combined_confidence: number;
  player_name?: string;
  team_name?: string;
  team_year?: number;
}

/**
 * SearchResult - Single photo result from search
 */
export interface SearchResult {
  id: number;
  file_path: string;
  jersey_number: string | null;
  confidence: number;
  raw_text: string;
  player_name?: string;
}

/**
 * SearchResponse - API response from search endpoint
 */
export interface SearchResponse {
  jersey: string;
  count: number;
  min_confidence: number;
  results: SearchResult[];
}

/**
 * CrawlResult - Result of crawling a single photo directory
 */
export interface CrawlResult {
  added: number;
  skipped: number;
  failed: number;
}

/**
 * CrawlResponse - API response from crawl endpoint
 */
export interface CrawlResponse {
  success: boolean;
  results: CrawlResult;
}

/**
 * OCRProcessingResult - Result of OCR processing
 */
export interface OCRProcessingResult {
  processed: number;
  skipped: number;
}

/**
 * OCRProcessResponse - API response from process-ocr endpoint
 */
export interface OCRProcessResponse {
  success: boolean;
  results: OCRProcessingResult;
}

/**
 * Face data in response - Lightweight version without full embedding
 */
export interface FaceInResponse {
  id: number;
  bbox: BoundingBox;
  confidence: number;
  embedding_dim: number;
}

/**
 * FacesResponse - API response from faces endpoint
 */
export interface FacesResponse {
  photo_id: number;
  face_count: number;
  faces: FaceInResponse[];
}

/**
 * DatabaseInfo - Database statistics
 */
export interface DatabaseInfo {
  total_photos: number;
  db_path: string;
}

/**
 * InfoResponse - API response from info endpoint
 */
export interface InfoResponse extends DatabaseInfo {
  // Extends DatabaseInfo for type compatibility
}

/**
 * HealthCheckResponse - API response from health endpoint
 */
export interface HealthCheckResponse {
  status: 'ok' | 'error';
}

/**
 * APIError - Standard error response from API
 */
export interface APIError {
  error: string;
}

/**
 * SearchOptions - Optional parameters for search
 */
export interface SearchOptions {
  minConfidence?: number;
  team?: string;
  year?: number;
}

/**
 * PhotoItem - Photo data returned from /api/photos endpoint
 */
export interface PhotoItem {
  id: number;
  filename: string;
  path: string;
  added_at: string;
}

/**
 * PhotosResponse - API response from photos endpoint (paginated)
 */
export interface PhotosResponse {
  photos: PhotoItem[];
  total: number;
  page: number;
  per_page: number;
}
