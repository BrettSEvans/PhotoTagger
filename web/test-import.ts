import photoTaggerClient, { PhotoTaggerClient } from './src/api/photoTaggerClient';
import { 
  Photo, 
  DetectedFace, 
  IdentifiedPlayer,
  SearchResult,
  SearchResponse,
  CrawlResponse,
  FacesResponse,
  InfoResponse,
  HealthCheckResponse
} from './src/types/index';

// Type checking - verify all types compile
const testPhoto: Photo = {
  id: 1,
  file_path: '/path/to/photo.jpg',
  file_hash: 'abc123',
  file_size: 1024,
  created_at: new Date().toISOString(),
  ingested_at: new Date().toISOString(),
};

const testFace: DetectedFace = {
  id: 1,
  photo_id: 1,
  bbox: [0, 0, 100, 100],
  confidence: 0.95,
  embedding: new Array(512).fill(0.1),
};

// Verify client singleton exists and has correct methods
const client = photoTaggerClient;
console.log('Client methods:');
console.log('- healthCheck:', typeof client.healthCheck);
console.log('- getInfo:', typeof client.getInfo);
console.log('- crawlPhotos:', typeof client.crawlPhotos);
console.log('- processOCR:', typeof client.processOCR);
console.log('- search:', typeof client.search);
console.log('- getFaces:', typeof client.getFaces);

// Verify constructor works
const customClient = new PhotoTaggerClient('http://example.com');
console.log('Custom client created with custom URL');

console.log('All imports and types verified successfully!');
