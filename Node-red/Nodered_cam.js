function getMedian(arr) {
  const sorted = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 0) {
    return (sorted[mid - 1] + sorted[mid]) / 2;
  } else {
    return sorted[mid];
  }
}

function hampelFilterData(data, windowSize, threshold = 3.0, status) {
  const n = data.length;
  const newData = [];
  const newState = [];
  const k = (windowSize - 1) / 2;

  for (let i = 0; i < n; i++) {
    const start = Math.max(0, i - k);
    const end = Math.min(n - 1, i + k);
    const windowData = data.slice(start, end + 1);

    const median = getMedian(windowData);
    const deviations = windowData.map((val) => Math.abs(val - median));
    const mad = getMedian(deviations);
    const scale = 1.4826 * mad;

    if (scale > 0) {
      if (Math.abs(data[i] - median) <= threshold * scale) {
        newData.push(data[i]);
        newState.push(status[i]);
    }
} else {
    newData.push(data[i]);
    newState.push(status[i]);
    }
  }
  return newData;
}

function hampelFilterState(data, windowSize, threshold = 3.0, status) {
  const n = data.length;
  const newData = [];
  const newState = [];
  const k = (windowSize - 1) / 2;

  for (let i = 0; i < n; i++) {
    const start = Math.max(0, i - k);
    const end = Math.min(n - 1, i + k);
    const windowData = data.slice(start, end + 1);

    const median = getMedian(windowData);
    const deviations = windowData.map((val) => Math.abs(val - median));
    const mad = getMedian(deviations);
    const scale = 1.4826 * mad;

    if (scale > 0) {
      if (Math.abs(data[i] - median) <= threshold * scale) {
        newData.push(data[i]);
        newState.push(status[i]);
    }
} else {
    newData.push(data[i]);
    newState.push(status[i]);
    }
  }
  return newState;
}

const ZERO_THRESHOLD = 0.5;
const END_ON_ZEROS = 1;

const HAMPEL_WINDOW_SIZE = 5;
const HAMPEL_THRESHOLD = 3.0;
const MIN_RUN = 5;

const moduleName = String(msg.payload?.module ?? "");
const valL = Number(msg.payload?.length ?? 0);
const valW = Number(msg.payload?.width ?? 0);
const state = Number(msg.payload?.status ?? 0);

let run3 = context.get("run3") || [];
let run3s = context.get("run3s") || [];
let run3w = context.get("run3w") || [];
let zeroCount3 = context.get("zeroCount3") || 0;

if (Number.isFinite(valL) && valL > ZERO_THRESHOLD) {
  run3.push(valL);
  run3w.push(valW);
  run3s.push(state);
  zeroCount3 = 0;
  context.set("run3", run3);
  context.set("run3s", run3s);
  context.set("run3w", run3w);
  context.set("zeroCount3", zeroCount3);
  return null;
}

if (run3.length >= MIN_RUN) {
  zeroCount3 += 1;
  context.set("zeroCount3", zeroCount3);

  if (zeroCount3 >= END_ON_ZEROS) {
    const noSpikesL = hampelFilterData(
      run3,
      HAMPEL_WINDOW_SIZE,
      HAMPEL_THRESHOLD,
      run3s
    );
    const noSpikesW = hampelFilterData(
      run3w,
      HAMPEL_WINDOW_SIZE,
      HAMPEL_THRESHOLD,
      run3s
    );
    const noSpikesState = hampelFilterState(
      run3,
      HAMPEL_WINDOW_SIZE,
      HAMPEL_THRESHOLD,
      run3s
    );
    const avgdataL = noSpikesL.reduce((a, b) => a + b, 0) / noSpikesL.length;
    const avgdataW = noSpikesW.reduce((a, b) => a + b, 0) / noSpikesW.length;
    const avgstate = Math.round(noSpikesState.reduce((a, b) => a + b, 0) / noSpikesState.length);

    context.set("run3", []);
    context.set("zeroCount3", 0);
    let st = 0
    if (avgstate == 1 && avgdataL >= 20 && avgdataL <= 25 && avgdataW >= 7 && avgdataW <= 9) {
      st = 1
    }
    msg.payload = {
      module: moduleName,
      length: Number(avgdataL.toFixed(1)),
      width: Number(avgdataW.toFixed(1)),
      Matter: Number(avgstate.toFixed(0)),
      Status: st
    };
    return msg;
  }

  context.set("run3", run3);
  return null;
}

context.set("run3", []);
context.set("zeroCount3", 0);
return null;
