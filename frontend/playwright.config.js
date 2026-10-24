import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './browser-tests',
  workers: 1,
  timeout: 30000,
  use: {
    channel: 'msedge',
    baseURL: 'http://127.0.0.1:4173',
    launchOptions: { args: ['--mute-audio'] },
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npm run preview -- --host 127.0.0.1 --port 4173',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: false,
  },
});
