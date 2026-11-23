// Offline single-file build only (see vite.offline.config.ts): worker code embedded in the page, started from a blob.
import SearchWorker from '../workers/search.worker.ts?worker&inline';
import CalibrateWorker from '../workers/calibrate.worker.ts?worker&inline';

export const createSearchWorker = () => new SearchWorker();
export const createCalibrateWorker = () => new CalibrateWorker();
