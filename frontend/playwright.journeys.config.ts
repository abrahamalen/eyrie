import { defineConfig, devices } from '@playwright/test'

// The journey suite: one recorded walk-through per user journey, feeding the
// report at journeys/index.html.
//
// It records video for every test and runs one at a time, which the report depends on.
// Run it with `make journeys` (scripts/journeys.sh): the journeys need the throwaway
// backend that script seeds and starts.
export default defineConfig({
  testDir: './e2e',
  // Serial, single worker: parallel runs interleave and the videos become
  // impossible to follow.
  fullyParallel: false,
  workers: 1,
  // Journeys pause on camera between steps, so they take longer than unit tests.
  timeout: 60_000,
  // One retry in CI so a single slow call doesn't block a merge. The report
  // marks retried journeys 'flaky' so they still get fixed.
  retries: process.env.CI ? 1 : 0,
  // The json reporter is what build_report.py reads to pair each test with
  // its video and screenshots.
  reporter: [['list'], ['json', { outputFile: 'journeys/results.json' }]],
  outputDir: 'journeys/raw',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:5173',
    // JOURNEY_VIDEO=retain-on-failure keeps CI fast by recording only failures.
    video: (process.env.JOURNEY_VIDEO as 'on' | 'retain-on-failure' | undefined) ?? 'on',
    // Full-page stills at the end of every test, on top of the ones a journey
    // takes itself with the `shot()` helper.
    screenshot: 'on',

    trace: 'retain-on-failure',
    // A HAR of every request the journey made, saved next to its video. The
    // report lists the failed ones, which is how a green test with a broken
    // pane gets caught.
    recordHar: { mode: 'minimal', path: 'har.har' },
  },
  // Every journey runs on both.
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } } },
    // Pixel 7 runs on Chromium, so there's no second browser to download.
    { name: 'phone', use: { ...devices['Pixel 7'] } },
  ],
})
