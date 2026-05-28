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
  APIError,
  SearchOptions,
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
   * @param baseURL Base URL of the PhotoTagger API (default: http://localhost:5000)
   */
  constructor(baseURL: string = 'http://localhost:5000') {
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
