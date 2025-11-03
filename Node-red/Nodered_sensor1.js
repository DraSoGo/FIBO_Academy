function getMedian(arr) {
  const sorted = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 0) {
    return (sorted[mid - 1] + sorted[mid]) / 2;
  } else {
    return sorted[mid];
  }
}

function hampelFilter(data, windowSize, threshold = 3.0) {
  const n = data.length;
  const newData = [...data];
  const k = (windowSize - 1) / 2;

  for (let i = 0; i < n; i++) {
    const start = Math.max(0, i - k);
    const end = Math.min(n - 1, i + k);
    const windowData = data.slice(start, end + 1);

    const median = getMedian(windowData);
    const deviations = windowData.map(val => Math.abs(val - median));
    const mad = getMedian(deviations);
    const scale = 1.4826 * mad;

    if (scale > 0) {
      if (Math.abs(data[i] - median) > (threshold * scale)) {
        newData[i] = median;
      } else {
        newData[i] = data[i];
      }
    } else {
      newData[i] = data[i];
    }
  }
  return newData;
}

function savitzkyGolayFilter(data) {
  const coeffs = [-3, 12, 17, 12, -3];
  const denominator = 35;
  const k = (coeffs.length-1)/2;
  const n = data.length;
  const newData = [];

  for (let i = 0; i < n; i++) {
    if (i < k || i >= n - k) {
      newData.push(data[i]);
    } else {
      let sum = 0;
      for (let j = 0; j < coeffs.length; j++) {
        sum += data[i - k + j] * coeffs[j];
      }
      newData.push(sum / denominator);
    }
  }
  return newData;
}

const ZERO_THRESHOLD = 1.0;
const END_ON_ZEROS   = 1;

const HAMPEL_WINDOW_SIZE = 5;
const HAMPEL_THRESHOLD   = 3.0;
const MIN_RUN            = 10;

// replace Hampel/Savitzky with simple moving average window
const MOVING_AVG_WINDOW = 5;

function movingAverage(data, windowSize) {
  const n = data.length;
  if (n === 0) return [];
  const w = Math.max(1, Math.floor(windowSize));
  const out = new Array(n);
  let sum = 0;
  // initial window
  for (let i = 0; i < Math.min(w, n); i++) {
    sum += data[i];
    out[i] = sum / (i + 1); // ramp-up at start
  }
  for (let i = w; i < n; i++) {
    sum += data[i] - data[i - w];
    out[i] = sum / w;
  }
  // optionally smooth early indices to use full-window trailing average:
  // keep as-is (ramp) to preserve causality
  return out;
}

const moduleName = String(msg.payload?.module ?? "");
const val = Number(msg.payload?.high ?? 0);

let run1 = context.get('run1') || [];
let zeroCount1 = context.get('zeroCount1') || 0;

if (Number.isFinite(val) && val > ZERO_THRESHOLD) {
  run1.push(val);
  zeroCount1 = 0;
  context.set('run1', run1);
  context.set('zeroCount1', zeroCount1);
  return null;
}

if (run1.length >= MIN_RUN) {
  zeroCount1 += 1;
  context.set('zeroCount1', zeroCount1);

  if (zeroCount1 >= END_ON_ZEROS) {
    const smoothData = movingAverage(run1, MOVING_AVG_WINDOW);
    const maxVal = smoothData.length ? Math.max(...smoothData) : 0;

    context.set('run1', []);
    context.set('zeroCount1', 0);
    let state = 0
    if (maxVal >= 7 && maxVal <= 9) {
      state = 1
    }
    msg.payload = {
      module: moduleName,
      high: Number(maxVal.toFixed(1)),
      status: state
    };
    return msg;
  }

  context.set('run1', run1);
  return null;
}

context.set('run1', []);
context.set('zeroCount1', 0);
return null;