import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('**/health', route => {
    route.fulfill({ json: { status: 'ok' } });
  });
  await page.route('**/api/processing-summary', route => {
    route.fulfill({ json: { total_photos: 0, tagged: 0, needs_review: 0 } });
  });
  await page.route('**/api/confirmed-photos**', route => {
    route.fulfill({ json: { photos: [] } });
  });
  await page.route('**/api/review-photos**', route => {
    route.fulfill({ json: { photos: [] } });
  });
  await page.route('**/api/roster', route => {
    route.fulfill({ json: { entries: [], total: 0 } });
  });
  await page.route('**/api/detection-status', route => {
    route.fulfill({ json: { face_count: 0, cluster_count: 0 } });
  });
  await page.route('**/api/players', route => {
    route.fulfill({ json: { players: [], total: 0 } });
  });
  await page.route('**/api/photos**', route => {
    route.fulfill({ json: { photos: [], total: 0, page: 1, per_page: 20 } });
  });
});

test('core navigation surfaces load without backend data', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'PhotoTagger' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Upload' })).toBeVisible();

  await page.getByRole('button', { name: 'Roster' }).click();
  await expect(page.getByRole('heading', { name: 'Roster' })).toBeVisible();

  await page.getByRole('button', { name: 'Review' }).click();
  await expect(page.getByRole('heading', { name: 'Cleanup Workspace' })).toBeVisible();

  await page.getByRole('button', { name: 'Players' }).click();
  await expect(page.getByRole('heading', { name: 'Players' })).toBeVisible();

  await page.getByRole('button', { name: 'Gallery' }).click();
  await expect(page.getByRole('heading', { name: 'Gallery' })).toBeVisible();

  await page.getByRole('button', { name: 'Search' }).click();
  await expect(page.getByRole('heading', { name: 'Search' })).toBeVisible();
});
