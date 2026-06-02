/**
 * PhotoTagger API Client
 * Type-safe Axios client for frontend-backend communication
 */

import axios, { AxiosInstance, AxiosError } from 'axios';
import {
  HealthCheckResponse,
  AgentSettings,
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
  RosterEntry,
  RosterResponse,
  RosterImportResponse,
  DeassignFacesResponse,
  AssignClusterResponse,
  MatchSimilarResponse,
  RosterSearchResult,
  ProcessingSummary,
  TaggedPhoto,
  ReviewPhoto,
  ProcessingJob,
  JobStatusResponse,
  JobSubmissionResponse,
  FaceDetectionResult,
  ClusterPlayersResult,
  GameContextResponse,
  GameContextTeam,
  PhotoBatch,
  BatchesResponse,
} from '../types/index';

const LOCAL_AGENT_URL_KEY = 'phototagger.localAgentUrl';
const AGENT_TOKEN_KEY = 'phototagger.agentToken';

function storedValue(key: string): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(key);
}

// Use relative URLs by default, which works on both local and Railway.app deployments.
// localStorage override lets users manually set a different API URL if needed.
const API_BASE_URL = storedValue(LOCAL_AGENT_URL_KEY) || import.meta.env.VITE_LOCAL_AGENT_URL || import.meta.env.VITE_API_BASE_URL || '';

/**
 * PhotoTaggerClient - Encapsulates all API communication
 * Provides type-safe methods for interacting with PhotoTagger backend
 */
class PhotoTaggerClient {
  private client: AxiosInstance;
  private baseURL: string;
  private agentToken: string;

  /**
   * Constructor
   * @param baseURL Base URL of the PhotoTagger API (default: http://127.0.0.1:5001)
   */
  constructor(baseURL: string = API_BASE_URL) {
    this.baseURL = baseURL;
    this.agentToken = storedValue(AGENT_TOKEN_KEY) || import.meta.env.VITE_AGENT_TOKEN || '';
    this.client = axios.create({
      baseURL: this.baseURL,
      timeout: 300000, // 5 minute timeout for long-running operations
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Add response interceptor for error handling
    this.client.interceptors.response.use(
      response => response,
      error => this.handleError(error)
    );
    this.client.interceptors.request.use(config => {
      if (this.agentToken) {
        config.headers.set('X-PhotoTagger-Agent-Token', this.agentToken);
      }
      return config;
    });
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
   * Upload photos - Upload photo files via browser file picker or drag & drop
   * POST /api/upload-photos (multipart/form-data)
   *
   * @param formData FormData containing files
   * @returns Upload results with job ID for polling
   */
  async uploadPhotos(formData: FormData): Promise<CrawlResponse> {
    const response = await this.client.post<CrawlResponse>('/api/upload-photos', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
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

  async getJob<TResult = unknown>(jobId: number): Promise<ProcessingJob<TResult>> {
    const response = await this.client.get<JobStatusResponse<TResult>>(`/api/jobs/${jobId}`);
    return response.data.job;
  }

  async pollJob<TResult = unknown>(
    jobId: number,
    options: {
      intervalMs?: number;
      timeoutMs?: number;
      onUpdate?: (job: ProcessingJob<TResult>) => void;
    } = {}
  ): Promise<ProcessingJob<TResult>> {
    // Use adaptive polling: start fast, then back off for long-running jobs
    const initialIntervalMs = options.intervalMs ?? 500;
    const maxIntervalMs = 5000;
    const timeoutMs = options.timeoutMs ?? 1800000; // 30 minutes for large batches
    const startedAt = Date.now();
    let currentIntervalMs = initialIntervalMs;

    while (Date.now() - startedAt <= timeoutMs) {
      try {
        const job = await this.getJob<TResult>(jobId);
        options.onUpdate?.(job);

        if (job.status === 'succeeded') {
          return job;
        }

        if (job.status === 'failed') {
          throw new Error(job.error || 'Processing job failed');
        }

        // Increase polling interval over time to reduce server load
        currentIntervalMs = Math.min(currentIntervalMs * 1.2, maxIntervalMs);
      } catch (error) {
        // If we get a timeout error on a poll request, retry with longer interval
        if (error instanceof Error && error.message.includes('timeout')) {
          console.warn('Poll request timed out, increasing interval');
          currentIntervalMs = Math.min(currentIntervalMs * 2, maxIntervalMs);
        } else {
          throw error;
        }
      }

      await new Promise(resolve => window.setTimeout(resolve, currentIntervalMs));
    }

    throw new Error(`Processing job timed out after ${Math.round(timeoutMs / 1000)} seconds`);
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
  async detectFaces(photoIds?: number[]): Promise<JobSubmissionResponse<FaceDetectionResult>> {
    const body = photoIds ? { photo_ids: photoIds } : {};
    const response = await this.client.post<JobSubmissionResponse<FaceDetectionResult>>('/api/detect-faces', body);
    return response.data;
  }

  /**
   * Cluster detected faces into player identities
   * POST /api/cluster-players
   *
   * @param threshold Cosine similarity threshold (default 0.40)
   */
  async clusterPlayers(threshold = 0.40): Promise<JobSubmissionResponse<ClusterPlayersResult>> {
    const response = await this.client.post<JobSubmissionResponse<ClusterPlayersResult>>('/api/cluster-players', { threshold });
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
  async getPlayerPhotos(clusterId: number, options: { minFaceConfidence?: number } = {}): Promise<PlayerPhotosResponse> {
    const params: Record<string, number> = {};
    if (options.minFaceConfidence !== undefined) {
      params.min_face_confidence = options.minFaceConfidence;
    }

    const response = await this.client.get<PlayerPhotosResponse>(`/api/players/${clusterId}/photos`, { params });
    return response.data;
  }

  /**
   * Get the URL for a cropped face thumbnail
   */
  getFaceCropUrl(faceId: number): string {
    return this.withAgentToken(`${this.baseURL}/api/face-crop/${faceId}`);
  }

  /**
   * Get the URL for a full photo
   */
  getPhotoUrl(photoId: number): string {
    return this.withAgentToken(`${this.baseURL}/api/image/${photoId}`);
  }

  // ── Roster ────────────────────────────────────────────────────────────────

  async getRoster(): Promise<RosterResponse> {
    const response = await this.client.get<RosterResponse>('/api/roster');
    return response.data;
  }

  async getGameContext(): Promise<GameContextResponse> {
    const response = await this.client.get<GameContextResponse>('/api/game-context');
    return response.data;
  }

  async setGameContext(teams: GameContextTeam[]): Promise<GameContextResponse> {
    const response = await this.client.put<GameContextResponse>('/api/game-context', { teams });
    return response.data;
  }

  async addRosterEntry(
    jerseyNumber: string,
    playerName: string,
    teamName = 'Manual Entry',
    teamYear = 2026,
    uniformColor?: string,
  ): Promise<void> {
    await this.client.post('/api/roster', {
      jersey_number: jerseyNumber,
      player_name: playerName,
      team_name: teamName,
      team_year: teamYear,
      uniform_color: uniformColor,
    });
  }

  async deleteRosterEntry(entryId: number): Promise<void> {
    await this.client.delete(`/api/roster/${entryId}`);
  }

  async updateRosterEntry(
    entryId: number,
    data: Partial<Omit<RosterEntry, 'id' | 'thumbnail_face_id'>>,
  ): Promise<RosterEntry> {
    const response = await this.client.put<RosterEntry>(`/api/roster/${entryId}`, data);
    return response.data;
  }

  async importRosterFile(
    file: File,
    teamName: string,
    teamYear: number,
    duplicatePolicy: 'replace' | 'skip',
    uniformColor?: string,
  ): Promise<RosterImportResponse> {
    const form = new FormData();
    form.append('file', file);
    form.append('team_name', teamName);
    form.append('team_year', String(teamYear));
    form.append('duplicate_policy', duplicatePolicy);
    if (uniformColor) form.append('uniform_color', uniformColor);

    const response = await this.client.post<RosterImportResponse>('/api/roster/import', form, { timeout: 120000 });
    return response.data;
  }

  async importRosterUrl(
    url: string,
    teamName: string,
    teamYear: number,
    duplicatePolicy: 'replace' | 'skip',
    uniformColor?: string,
  ): Promise<RosterImportResponse> {
    const response = await this.client.post<RosterImportResponse>('/api/roster/import-url', {
      url,
      team_name: teamName,
      team_year: teamYear,
      duplicate_policy: duplicatePolicy,
      uniform_color: uniformColor,
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

  async assignCluster(
    clusterId: number,
    playerName: string,
    jerseyNumber: string,
    rosterEntryId?: number,
    options: { writeMetadata?: boolean; faceIds?: number[] } = {},
  ): Promise<AssignClusterResponse> {
    const response = await this.client.post<AssignClusterResponse>(`/api/players/${clusterId}/assign`, {
      player_name: playerName,
      jersey_number: jerseyNumber,
      roster_entry_id: rosterEntryId,
      write_metadata: options.writeMetadata ?? false,
      face_ids: options.faceIds ?? [],
    });
    return response.data;
  }

  async deassignFaces(faceIds: number[]): Promise<DeassignFacesResponse> {
    const response = await this.client.post<DeassignFacesResponse>('/api/faces/deassign', { face_ids: faceIds });
    return response.data;
  }

  async matchSimilarClusters(clusterId: number): Promise<MatchSimilarResponse> {
    const response = await this.client.post<MatchSimilarResponse>(
      `/api/players/${clusterId}/match-similar`,
    );
    return response.data;
  }

  async resetAllData(): Promise<{ success: boolean; deleted: Record<string, number> }> {
    const response = await this.client.post('/api/data/reset', { confirm: true });
    return response.data;
  }

  // ── Photo Batches (Import Groups) ─────────────────────────────────────────

  async getBatches(): Promise<BatchesResponse> {
    const response = await this.client.get<BatchesResponse>('/api/batches');
    return response.data;
  }

  async getBatch(batchId: number): Promise<{ batch: PhotoBatch; photos: any[] }> {
    const response = await this.client.get(`/api/batches/${batchId}`);
    return response.data;
  }

  async updateBatch(batchId: number, data: Partial<PhotoBatch>): Promise<{ success: boolean; batch: PhotoBatch }> {
    const response = await this.client.put<{ success: boolean; batch: PhotoBatch }>(`/api/batches/${batchId}`, data);
    return response.data;
  }

  async deleteBatch(batchId: number): Promise<{ success: boolean; affected_photos: number }> {
    const response = await this.client.delete<{ success: boolean; affected_photos: number }>(`/api/batches/${batchId}`);
    return response.data;
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

  setLocalAgentSettings(settings: AgentSettings): void {
    const cleanUrl = settings.localAgentUrl.trim().replace(/\/+$/, '') || '';
    this.baseURL = cleanUrl;
    this.agentToken = settings.agentToken.trim();
    this.client.defaults.baseURL = cleanUrl;
    window.localStorage.setItem(LOCAL_AGENT_URL_KEY, cleanUrl);
    window.localStorage.setItem(AGENT_TOKEN_KEY, this.agentToken);
  }

  getLocalAgentSettings(): AgentSettings {
    return {
      localAgentUrl: this.baseURL,
      agentToken: this.agentToken,
    };
  }

  /**
   * Get current base URL
   */
  getBaseURL(): string {
    return this.baseURL;
  }

  private withAgentToken(url: string): string {
    if (!this.agentToken) return url;
    const separator = url.includes('?') ? '&' : '?';
    return `${url}${separator}agent_token=${encodeURIComponent(this.agentToken)}`;
  }
}

/**
 * Singleton instance of PhotoTaggerClient
 * Default configuration: http://localhost:5000
 */
const photoTaggerClient = new PhotoTaggerClient();

export { PhotoTaggerClient, photoTaggerClient as default };
export type { SearchOptions };
