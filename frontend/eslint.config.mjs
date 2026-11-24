// Like the backend's ruff setup (.github/workflows/ci.yml): only rules that
// catch real breakage. Style is left to the editor and to review.
import js from '@eslint/js';
import { defineConfig } from 'eslint/config';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import tseslint from 'typescript-eslint';

export default defineConfig(
  { ignores: ['dist', 'coverage'] },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended, tseslint.configs.recommended],
    languageOptions: { globals: globals.browser },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      // A hook called conditionally or in a loop breaks React's state order
      'react-hooks/rules-of-hooks': 'error',
      // A dependency left out may be a stale value. A warning, but `npm run
      // lint` allows none (CI fails on it): one left out on purpose (a load on
      // mount, a refresh on one value only) says why in an
      // `eslint-disable-next-line ... -- reason` comment above the deps.
      // The plugin's React Compiler rules (refs, set-state-in-effect...)
      // stay off: this app isn't compiled, and the patterns they flag (the
      // latest value kept in a ref) are deliberate.
      'react-hooks/exhaustive-deps': 'warn',
      // `any` is a choice, not a bug
      '@typescript-eslint/no-explicit-any': 'off',
      // `const { [key]: _removed, ...rest } = obj` drops a key on purpose
      '@typescript-eslint/no-unused-vars': ['error', { ignoreRestSiblings: true, varsIgnorePattern: '^_' }],
    },
  },
  {
    files: ['tests/**', 'vite.config.ts', 'vitest.config.ts'],
    languageOptions: { globals: globals.node },
  },
);
