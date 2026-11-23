// Offline single-file build: `npm run build:offline` → release/orka-offline.html, one HTML file that runs from disk
// (file://) with no server and no network. Lazy data and the two workers are inlined; scripts/inline-offline.mjs then
// folds the script and stylesheet into the page.
import path from 'node:path';
import { defineConfig, mergeConfig } from 'vite';
import base from './vite.config';

export default mergeConfig(
  base,
  defineConfig({
    publicDir: false,
    resolve: { alias: [{ find: /^\.\/workers$/, replacement: path.resolve(__dirname, 'src/ui/workers.inline.ts') }] },
    build: {
      outDir: 'dist-offline',
      emptyOutDir: true,
      sourcemap: false,
      cssCodeSplit: false,
      modulePreload: false,
      assetsInlineLimit: 100_000_000,
      rollupOptions: { output: { inlineDynamicImports: true } },
    },
  }),
);
