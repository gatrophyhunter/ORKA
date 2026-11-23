// Runs powder calibration (Levenberg–Marquardt over many simulations) off the main thread.
import { calibrate, type CalibrationInput, type CalibrationResult } from '../engine/calibrate';

export type CalibrateMessage = { type: 'done'; result: CalibrationResult } | { type: 'error'; message: string };

self.onmessage = (e: MessageEvent<CalibrationInput>) => {
  try {
    const result = calibrate(e.data);
    (self as unknown as Worker).postMessage({ type: 'done', result } satisfies CalibrateMessage);
  } catch (err) {
    (self as unknown as Worker).postMessage({ type: 'error', message: err instanceof Error ? err.message : String(err) } satisfies CalibrateMessage);
  }
};
