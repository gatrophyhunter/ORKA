// Worker factories. The normal build emits each worker as its own file next to the page. The offline single-file build
// (vite.offline.config.ts) swaps this module for workers.inline.ts, which embeds the worker code in the page.
export const createSearchWorker = () => new Worker(new URL('../workers/search.worker.ts', import.meta.url), { type: 'module' });
export const createCalibrateWorker = () => new Worker(new URL('../workers/calibrate.worker.ts', import.meta.url), { type: 'module' });
