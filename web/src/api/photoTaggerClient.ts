/**
 * PhotoTagger API Client
 * Type-safe Axios client for frontend-backend communication
 */

import axios, { AxiosInstance, AxiosError } from 'axios';
import {
  HealthCheckResponse,
  InfoResponse,
  CrawlResponse,
  OCRProcessResponse,
  SearchResponse,
  FacesResponse,
  PhotosResponse,
  PlayersResponse,
  PlayerPhotosResponse,
  DetectionStatus,
  APIError,
  SearchOptions,
  RosterResponse,
  RosterImportResponse,
  RosterSearchResult,
  ProcessingSummary,
  TaggedPhoto,
  ReviewPhoto,
} from '../types/index';

/**
 * PhotoTaggerClient - Encapsulates all API communication
 * Provides type-safe methods for interacting with PhotoTagger backend
 */
class PhotoTaggerClient {
  private client: AxiosInstance;
  private baseURL: string;

  /**
   * Constructor
   * @param baseURL Base URL of the PhotoTagger API (default: http://127.0.0.1:5001)
   */
  constructor(baseURL: string = 'http://127.0.0.1:5001') {
    this.baseURL = baseURL;
    this.client = axios.create({
      baseURL: this.baseURL,
      timeout: 30000, // 30 second timeout
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Add response interceptor for error handling
    this.client.interceptors.response.use(
      response => response,
      error => this.handleError(error)
    );
  }

  /**
   * Handle API errors with proper typing
   */
  private handleError(error: AxiosError<APIError>): Promise<never> {
    if (error.response?.data?.error) {
      const message = error.response.data.error;
      console.error(`API Error: ${message}`);
      return Promise.reject(new Error(message));
    }

    if (error.message) {
      console.error(`Request Error: ${error.message}`);
      return Promise.reject(error);
    }

    return Promise.reject(new Error('Unknown API error'));
  }

  /**
   * Health check - Verify API is running
   * GET /health
   *
   * @returns Health check response
   */
  async healthCheck(): Promise<HealthCheckResponse> {
    const response = await this.client.get<HealthCheckResponse>('/health');
    return response.data;
  }

  /**
   * Get database info - Statistics and configuration
   * GET /api/info
   *
   * @returns Database information
   */
  async getInfo(): Promise<InfoResponse> {
    const response = await this.client.get<InfoResponse>('/api/info');
    return response.data;
  }

  /**
   * Open native OS directory picker dialog
   * POST /api/pick-directory
   *
   * @returns Selected directory path, or null if cancelled
   */
  async pickDirectory(): Promise<string | null> {
    const response = await this.client.post<{ path: string | null; cancelled: boolean }>(
      '/api/pick-directory'
    );
    return response.data.path;
  }

  /**
   * Crawl photos - Ingest photos from local directory
   * POST /api/crawl
   *
   * @param photoDir Path to directory containing photos
   * @returns Crawl results with counts
   */
  async crawlPhotos(photoDir: string): Promise<CrawlResponse> {
    const response = await this.client.post<CrawlResponse>('/api/crawl', {
      photo_dir: photoDir,
    });
    return response.data;
  }

  /**
   * Process OCR - Extract jersey numbers from photos
   * POST /api/process-ocr
   *
   * @param photoIds Optional specific photo IDs to process
   * @returns OCR processing results with counts
   */
  async processOCR(photoIds?: number[]): Promise<OCRProcessResponse> {
    const body = photoIds ? { photo_ids: photoIds } : {};
    const response = await this.client.post<OCRProcessResponse>('/api/process-ocr', body);
    return response.data;
  }

  /**
   * Search photos - Find photos by jersey number with optional filters
   * GET /api/search
   *
   * @param jersey Jersey number to search for (required)
   * @param options Optional search parameters
   * @returns Search results with matching photos
   */
  async search(jersey: string, options?: SearchOptions): Promise<SearchResponse> {
    const params: Record<string, any> = { jersey };

    if (options?.minConfidence !== undefined) {
      params.min_confidence = options.minConfidence;
    }

    if (options?.team !== undefined) {
      params.team = options.team;
    }

    if (options?.year !== undefined) {
      params.year = options.year;
    }

    const response = await this.client.get<SearchResponse>('/api/search', { params });
    return response.data;
  }

  /**
   * Get faces for photo - Retrieve all detected faces and embeddings
   * GET /api/faces/<id>
   *
   * @param photoId Photo ID to get faces for
   * @returns Face detection results
   */
  async getFaces(photoId: number): Promise<FacesResponse> {
    const response = await this.client.get<FacesResponse>(`/api/faces/${photoId}`);
    return response.data;
  }

  /**
   * Get all photos - Retrieve paginated list of all photos in database
   * GET /api/photos
   *
   * @param page Page number (default: 1)
   * @param perPage Number of photos per page (default: 20)
   * @returns Paginated photos with metadata
   */
  async getPhotos(page = 1, perPage = 20): Promise<PhotosResponse> {
    const response = await this.client.get<PhotosResponse>('/api/photos', {
      params: { page, per_page: perPage }
    })
    return response.data
  }

  /**
   * Get detection status - face and cluster counts
   * GET /api/detection-status
   */
  async getDetectionStatus(): Promise<DetectionStatus> {
    const response = await this.client.get<DetectionStatus>('/api/detection-status');
    return response.data;
  }

  /**
   * Run face detection on all photos
   * POST /api/detect-faces
   *
   * @param photoIds Optional list of specific photo IDs to process
   */
  async detectFaces(photoIds?: number[]): Promise<{ success: boolean; photos_processed: number; faces_detected: number; errors: number }> {
    const body = photoIds ? { photo_ids: photoIds } : {};
    const response = await this.client.post('/api/detect-faces', body, { timeout: 600000 }); // 10 min
    return response.data;
  }

  /**
   * Cluster detected faces into player identities
   * POST /api/cluster-players
   *
   * @param threshold Cosine similarity threshold (default 0.40)
   */
  async clusterPlayers(threshold = 0.40): Promise<{ success: boolean; clusters_created: number; faces_clustered: number }> {
    const response = await this.client.post('/api/cluster-players', { threshold });
    return response.data;
  }

  /**
   * Get all player clusters
   * GET /api/players
   */
  async getPlayers(): Promise<PlayersResponse> {
    const response = await this.client.get<PlayersResponse>('/api/players');
    return response.data;
  }

  /**
   * Get all photos for a specific player cluster
   * GET /api/players/:id/photos
   */
  async getPlayerPhotos(clusterId: number): Promise<PlayerPhotosResponse> {
    const response = await this.client.get<PlayerPhotosResponse>(`/api/players/${clusterId}/photos`);
    return response.data;
  }

  /**
   * Get the URL for a cropped face thumbnail
   */
  getFaceCropUrl(faceId: number): string {
    return `${this.baseURL}/api/face-crop/${faceId}`;
  }

  /**
   * Get the URL for a full photo
   */
  getPhotoUrl(photoId: number): string {
    return `${this.baseURL}/api/image/${photoId}`;
  }

  // ── Roster ────────────────────────────────────────────────────────────────

  async getRoster(): Promise<RosterResponse> {
    const response = await this.client.get<RosterResponse>('/api/roster');
    return response.data;
  }

  async addRosterEntry(jerseyNumber: string, playerName: string, teamName = 'Manual Entry', teamYear = 2026): Promise<void> {
    await this.client.post('/api/roster', {
      jersey_number: jerseyNumber,
      player_name: playerName,
      team_name: teamName,
      team_year: teamYear,
    });
  }

  async deleteRosterEntry(entryId: number): Promise<void> {
    await this.client.delete(`/api/roster/${entryId}`);
  }

  async importRosterFile(file: File, teamName: string, teamYear: number, duplicatePolicy: 'replace' | 'skip'): Promise<RosterImportResponse> {
    const form = new FormData();
    form.append('file', file);
    form.append('team_name', teamName);
    form.append('team_year', String(teamYear));
    form.append('duplicate_policy', duplicatePolicy);

    const response = await this.client.post<RosterImportResponse>('/api/roster/import', form, { timeout: 120000 });
    return response.data;
  }

  async importRosterUrl(url: string, teamName: string, teamYear: number, duplicatePolicy: 'replace' | 'skip'): Promise<RosterImportResponse> {
    const response = await this.client.post<RosterImportResponse>('/api/roster/import-url', {
      url,
      team_name: teamName,
      team_year: teamYear,
      duplicate_policy: duplicatePolicy,
    }, { timeout: 120000 });
    return response.data;
  }

  async searchRoster(query: string): Promise<RosterSearchResult[]> {
    const response = await this.client.get<{ results: RosterSearchResult[] }>(
      '/api/roster/search', { params: { q: query } }
    );
    return response.data.results;
  }

  // ── Processing summary ────────────────────────────────────────────────────

  async getProcessingSummary(): Promise<ProcessingSummary> {
    const response = await this.client.get<ProcessingSummary>('/api/processing-summary');
    return response.data;
  }

  async getConfirmedPhotos(limit = 60, offset = 0): Promise<TaggedPhoto[]> {
    const response = await this.client.get<{ photos: TaggedPhoto[] }>(
      '/api/confirmed-photos', { params: { limit, offset } }
    );
    return response.data.photos;
  }

  async getReviewPhotos(limit = 60, offset = 0): Promise<ReviewPhoto[]> {
    const response = await this.client.get<{ photos: ReviewPhoto[] }>(
      '/api/review-photos', { params: { limit, offset } }
    );
    return response.data.photos;
  }

  async assignCluster(clusterId: number, playerName: string, jerseyNumber: string): Promise<void> {
    await this.client.post(`/api/players/${clusterId}/assign`, { player_name: playerName, jersey_number: jerseyNumber });
  }

  async deassignFaces(faceIds: number[]): Promise<void> {
    await this.client.post('/api/faces/deassign', { face_ids: faceIds });
  }

  /**
   * Update base URL
   * Useful for switching between environments
   *
   * @param baseURL New base URL for API
   */
  setBaseURL(baseURL: string): void {
    this.baseURL = baseURL;
    this.client.defaults.baseURL = baseURL;
  }

  /**
   * Get current base URL
   */
  getBaseURL(): string {
    return this.baseURL;
  }
}

/**
 * Singleton instance of PhotoTaggerClient
 * Default configuration: http://localhost:5000
 */
const photoTaggerClient = new PhotoTaggerClient();

export { PhotoTaggerClient, photoTaggerClient as default };
export type { SearchOptions };
