/**
 * The capture quality gate, in the browser, at ~10 fps.
 *
 * Mirrors app/vision/quality.py exactly. A bad photo caught here costs five seconds;
 * caught later it costs a wrong report — which is why the shutter stays locked until all
 * four metrics pass.
 */

export interface QualityThresholds {
  minBlur: number;
  maxGlare: number;
  minCoverage: number;
  maxSkewDegrees: number;
}

export const DEFAULT_THRESHOLDS: QualityThresholds = {
  minBlur: 60,
  maxGlare: 0.06,
  minCoverage: 0.6,
  maxSkewDegrees: 6,
};

export interface QualityReport {
  blur: number;
  glare: number;
  coverage: number;
  skew: number;
  failures: string[];
  passed: boolean;
  band: "green" | "amber" | "red";
}

export function toGrayscale(data: ImageData): { gray: Float64Array; w: number; h: number } {
  const { width: w, height: h, data: px } = data;
  const gray = new Float64Array(w * h);
  for (let i = 0, p = 0; i < gray.length; i++, p += 4) {
    gray[i] = 0.299 * px[p] + 0.587 * px[p + 1] + 0.114 * px[p + 2];
  }
  return { gray, w, h };
}

/** Variance of the Laplacian. Higher is sharper. */
export function blurScore(gray: Float64Array, w: number, h: number): number {
  let sum = 0;
  let sumSq = 0;
  let n = 0;
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      const lap =
        gray[i - w] + gray[i + w] + gray[i - 1] + gray[i + 1] - 4 * gray[i];
      sum += lap;
      sumSq += lap * lap;
      n++;
    }
  }
  if (n === 0) return 0;
  const mean = sum / n;
  return sumSq / n - mean * mean;
}

/**
 * Blown-out fraction, measured relative to the page's own paper level.
 * A naive "pixels above 245" test calls a clean white page 78% glare.
 */
export function glareFraction(gray: Float64Array, margin = 6): number {
  const hist = new Uint32Array(256);
  let brightCount = 0;
  for (let i = 0; i < gray.length; i++) {
    const v = Math.min(255, Math.max(0, Math.round(gray[i])));
    if (v >= 128) {
      hist[v]++;
      brightCount++;
    }
  }
  if (brightCount === 0) return 0;
  let paperLevel = 128;
  let best = 0;
  for (let v = 128; v < 256; v++) {
    if (hist[v] > best) {
      best = hist[v];
      paperLevel = v;
    }
  }
  if (paperLevel >= 255 - margin) return 0;
  let over = 0;
  for (let i = 0; i < gray.length; i++) if (gray[i] > paperLevel + margin) over++;
  return over / gray.length;
}

export function skewDegrees(top: [[number, number], [number, number]]): number {
  const [[x0, y0], [x1, y1]] = top;
  return Math.abs((Math.atan2(y1 - y0, Math.max(x1 - x0, 1e-9)) * 180) / Math.PI);
}

export function assess(
  data: ImageData,
  opts: { quadArea?: number; topEdge?: [[number, number], [number, number]] } = {},
  thresholds: QualityThresholds = DEFAULT_THRESHOLDS,
): QualityReport {
  const { gray, w, h } = toGrayscale(data);
  const frameArea = w * h;
  const report: QualityReport = {
    blur: blurScore(gray, w, h),
    glare: glareFraction(gray),
    coverage: (opts.quadArea ?? frameArea) / frameArea,
    skew: opts.topEdge ? skewDegrees(opts.topEdge) : 0,
    failures: [],
    passed: false,
    band: "red",
  };
  if (report.blur < thresholds.minBlur) report.failures.push("blur");
  if (report.glare > thresholds.maxGlare) report.failures.push("glare");
  if (report.coverage < thresholds.minCoverage) report.failures.push("coverage");
  if (report.skew > thresholds.maxSkewDegrees) report.failures.push("skew");
  report.passed = report.failures.length === 0;
  report.band = report.passed ? "green" : report.failures.length === 1 ? "amber" : "red";
  return report;
}
