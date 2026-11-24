// Loaded before each test file (vitest.config.ts)
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Testing Library only unmounts by itself when the test functions are
// globals, which they aren't here (they're imported from 'vitest')
afterEach(cleanup);
