import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
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
