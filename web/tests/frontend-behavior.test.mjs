import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { test } from 'node:test';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');

function source(path) {
  return readFileSync(resolve(root, path), 'utf8');
}

test('processing jobs are polled through terminal states', () => {
  const client = source('src/api/photoTaggerClient.ts');

  assert.match(client, /async pollJob<TResult = unknown>/);
  assert.match(client, /job\.status === 'succeeded'/);
  assert.match(client, /job\.status === 'failed'/);
  assert.match(client, /Processing job timed out/);
});

test('processing pages use job polling instead of synchronous processing results', () => {
  const upload = source('src/components/PhotoUpload.tsx');
  const players = source('src/pages/PlayersPage.tsx');
  const cleanup = source('src/pages/ReviewPage.tsx');

  assert.match(upload, /pollJob<CrawlResult>\(response\.job_id/);
  assert.match(players, /pollJob<FaceDetectionResult>\(response\.job_id/);
  assert.match(players, /pollJob<ClusterPlayersResult>\(response\.job_id/);
  assert.match(cleanup, /pollJob<FaceDetectionResult>\(det\.job_id/);
  assert.match(cleanup, /pollJob<ClusterPlayersResult>\(clu\.job_id/);
});

test('photo removal actions require confirmation before deassigning faces', () => {
  const search = source('src/pages/SearchPage.tsx');
  const cleanup = source('src/pages/ReviewPage.tsx');

  assert.match(search, /window\.confirm\(`Remove \$\{photo\.filename\} from \$\{playerName\}\?`\)/);
  assert.match(search, /if \(!confirmed\) return;[\s\S]*deassignFaces\(\[photo\.face_id\]\)/);
  assert.match(cleanup, /window\.confirm\(`Remove \$\{photo\?\.filename \?\? 'this photo'\} from \$\{clusterName\}\?`\)/);
  assert.match(cleanup, /if \(!confirmed\) return;[\s\S]*deassignFaces\(\[faceId\]\)/);
});

test('confirmed tags hide ambiguous duplicate photo and jersey matches', () => {
  const upload = source('src/pages/UploadPage.tsx');

  assert.match(upload, /confirmedPhotosForDisplay/);
  assert.match(upload, /ambiguousConfirmedCount/);
  assert.match(upload, /new Set\(group\.map\(photo => photo\.player_name\)\)/);
  assert.match(upload, /Ambiguous auto-tags hidden/);
});

test('tailwind css pipeline is configured for the geometric design system', () => {
  const configPath = resolve(root, 'postcss.config.js');

  assert.equal(existsSync(configPath), true);
  const config = source('postcss.config.js');
  assert.match(config, /tailwindcss/);
  assert.match(config, /autoprefixer/);
});

test('review workspace excludes face matches below sixty percent confidence', () => {
  const client = source('src/api/photoTaggerClient.ts');
  const review = source('src/pages/ReviewPage.tsx');

  assert.match(client, /min_face_confidence/);
  assert.match(review, /MIN_REVIEW_FACE_CONFIDENCE\s*=\s*0\.6/);
  assert.match(review, /getPlayerPhotos\(cluster\.id,\s*\{ minFaceConfidence: MIN_REVIEW_FACE_CONFIDENCE \}\)/);
});

test('review assignments can write xmp sidecar metadata for selected photos', () => {
  const client = source('src/api/photoTaggerClient.ts');
  const review = source('src/pages/ReviewPage.tsx');
  const types = source('src/types/index.ts');

  assert.match(types, /AssignClusterResponse/);
  assert.match(client, /write_metadata/);
  assert.match(client, /face_ids/);
  assert.match(review, /Write XMP sidecar metadata/);
  assert.match(review, /writeMetadata/);
  assert.match(review, /Array\.from\(selected\)/);
  assert.match(review, /sidecar/);
});

test('frontend supports a configurable protected local agent', () => {
  const client = source('src/api/photoTaggerClient.ts');
  const app = source('src/App.tsx');

  assert.match(client, /phototagger\.localAgentUrl/);
  assert.match(client, /phototagger\.agentToken/);
  assert.match(client, /X-PhotoTagger-Agent-Token/);
  assert.match(client, /setLocalAgentSettings/);
  assert.match(app, /Local Agent/);
  assert.match(app, /Local agent disconnected/);
});
