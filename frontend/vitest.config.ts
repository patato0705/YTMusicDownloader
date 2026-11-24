import { defineConfig, mergeConfig } from 'vitest/config';
import viteConfig from './vite.config';

// The app's Vite config (plugins, JSON imports) plus the test settings
export default mergeConfig(viteConfig, defineConfig({
  test: {
    // A browser-like DOM for every test: components, and api/client.ts
    // reading window.location
    environment: 'jsdom',
    include: ['tests/**/*.test.{ts,tsx}'],
    setupFiles: ['tests/setup.ts'],
    // Each test file gets a fresh copy of every module: module state (the
    // access token in api/client.ts, the memory caches) doesn't leak between files
    isolate: true,
    restoreMocks: true,
    unstubGlobals: true,
  },
}));
