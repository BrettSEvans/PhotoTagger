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
  photos_found: number;
  photos_ingested: number;
  duplicates_skipped: number;
  errors: number;
}

/**
 * CrawlResponse - API response from crawl endpoint
 */
export interface LegacyCrawlResponse {
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
export interface LegacyOCRProcessResponse {
  success: boolean;
  results: OCRProcessingResult;
}

export type ProcessingJobStatus = 'queued' | 'running' | 'succeeded' | 'failed';

export interface ProcessingJob<TResult = unknown> {
  id: number;
  type: string;
  status: ProcessingJobStatus;
  progress: number;
  payload: Record<string, unknown>;
  result: TResult | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobSubmissionResponse<TResult = unknown> {
  success: boolean;
  job_id: number;
  job: ProcessingJob<TResult>;
}

export interface JobStatusResponse<TResult = unknown> {
  job: ProcessingJob<TResult>;
}

export type CrawlResponse = JobSubmissionResponse<CrawlResult>;
export type OCRProcessResponse = JobSubmissionResponse<OCRProcessingResult>;

export interface FaceDetectionResult {
  photos_processed: number;
  faces_detected: number;
  photos_skipped_existing: number;
  errors: number;
}

export interface ClusterPlayersResult {
  clusters_created: number;
  faces_clustered: number;
  faces_total?: number;
  error?: string;
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
  mode?: string;
}

export interface AgentSettings {
  localAgentUrl: string;
  agentToken: string;
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

/**
 * PlayerCluster - A grouped face identity (one "player")
 */
export interface PlayerCluster {
  id: number;
  face_count: number;
  photo_count: number;
  thumbnail_face_id: number | null;
  created_at: string;
  roster_entry_id?: number | null;
}

/**
 * PlayersResponse - API response from /api/players
 */
export interface PlayersResponse {
  players: PlayerCluster[];
  total: number;
}

/**
 * PlayerPhotoItem - One photo containing a specific player
 */
export interface PlayerPhotoItem {
  id: number;
  filename: string;
  path: string;
  added_at: string;
  face_id: number;
  face_bbox: [number, number, number, number];
  face_confidence: number;
}

/**
 * PlayerPhotosResponse - API response from /api/players/:id/photos
 */
export interface PlayerPhotosResponse {
  cluster_id: number;
  photos: PlayerPhotoItem[];
  total: number;
}

/**
 * DetectionStatus - Face detection and clustering counts
 */
export interface DetectionStatus {
  face_count: number;
  cluster_count: number;
}

/**
 * RosterEntry - Single player in the roster table
 */
export interface RosterEntry {
  id: number;
  team_name: string;
  team_year: number;
  jersey_number: string;
  player_name: string;
  uniform_color?: string | null;
  thumbnail_face_id?: number | null;
}

export interface GameContextTeam {
  team_name: string;
  team_year: number;
  uniform_color: string;
}

export interface GameContextResponse {
  teams: GameContextTeam[];
}

/**
 * RosterImportResponse - Result from roster bulk import endpoints
 */
export interface RosterImportResponse {
  success: boolean;
  imported: number;
  skipped: number;
  failed: number;
  errors: string[];
}

/**
 * DeassignFacesResponse - Result from removing face assignments from clusters
 */
export interface DeassignFacesResponse {
  success: boolean;
  deassigned: number;
  affected_cluster_ids: number[];
  deleted_cluster_ids: number[];
}

export interface MetadataWriteSummary {
  requested: boolean;
  written: number;
  skipped: number;
  failed: number;
  opponent_omitted: boolean;
  errors: string[];
}

export interface AssignClusterResponse {
  success: boolean;
  metadata: MetadataWriteSummary;
}

/**
 * RosterResponse - API response from /api/roster
 */
export interface RosterResponse {
  entries: RosterEntry[];
  total: number;
}

/**
 * RosterSearchResult - Hit from /api/roster/search
 */
export interface RosterSearchResult {
  id: number;
  team_name: string;
  jersey_number: string;
  player_name: string;
  uniform_color?: string | null;
}

/**
 * ProcessingSummary - Counts from /api/processing-summary
 */
export interface ProcessingSummary {
  total_photos: number;
  tagged: number;
  needs_review: number;
}

/**
 * TaggedPhoto - Photo confirmed matched to a roster player
 */
export interface TaggedPhoto {
  id: number;
  file_path: string;
  jersey_number: string;
  player_name: string;
  team_name?: string;
  uniform_color?: string | null;
  confidence: number;
}

/**
 * ReviewPhoto - Photo with unmatched OCR jersey
 */
export interface ReviewPhoto {
  id: number;
  file_path: string;
  jersey_number: string;
  uniform_color?: string | null;
  confidence: number;
  roster_candidates?: RosterSearchResult[];
}

/**
 * PlayerCluster extended with optional player assignment
 */
export interface PlayerClusterFull extends PlayerCluster {
  player_name?: string;
  jersey_number?: string;
}
