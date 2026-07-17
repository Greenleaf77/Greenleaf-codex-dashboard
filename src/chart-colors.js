export const BASE_MODEL_COLORS = [
  "#1E88E5", "#FB8C00", "#43A047", "#D81B60", "#C9A227",
  "#5E35B1", "#00ACC1", "#E53935", "#00897B", "#8D6E63",
];

const TONES = [
  { lightnessDelta: 0, chromaMultiplier: 1 },
  { lightnessDelta: -0.16, chromaMultiplier: 0.95 },
  { lightnessDelta: 0.14, chromaMultiplier: 0.72 },
  { lightnessDelta: -0.02, chromaMultiplier: 0.5 },
];
const COLORS_PER_BLOCK = BASE_MODEL_COLORS.length * TONES.length;
const BLOCKS_PER_HUE_CYCLE = 20;
const HUE_CYCLE_OFFSET = 137.507764;

function srgbToLinear(value) {
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

function linearToSrgb(value) {
  return value <= 0.0031308 ? value * 12.92 : 1.055 * value ** (1 / 2.4) - 0.055;
}

function linearSrgbToOklab({ r, g, b }) {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return {
    l: 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    a: 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    b: 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  };
}

function oklabToLinearSrgb({ l, a, b }) {
  const lRoot = l + 0.3963377774 * a + 0.2158037573 * b;
  const mRoot = l - 0.1055613458 * a - 0.0638541728 * b;
  const sRoot = l - 0.0894841775 * a - 1.291485548 * b;
  const lChannel = lRoot ** 3;
  const mChannel = mRoot ** 3;
  const sChannel = sRoot ** 3;
  return {
    r: 4.0767416621 * lChannel - 3.3077115913 * mChannel + 0.2309699292 * sChannel,
    g: -1.2684380046 * lChannel + 2.6097574011 * mChannel - 0.3413193965 * sChannel,
    b: -0.0041960863 * lChannel - 0.7034186147 * mChannel + 1.707614701 * sChannel,
  };
}

function hexToOklch(hex) {
  const channels = [1, 3, 5].map((offset) => srgbToLinear(Number.parseInt(hex.slice(offset, offset + 2), 16) / 255));
  const lab = linearSrgbToOklab({ r: channels[0], g: channels[1], b: channels[2] });
  const hue = Math.atan2(lab.b, lab.a) * 180 / Math.PI;
  return {
    l: lab.l,
    c: Math.hypot(lab.a, lab.b),
    h: (hue + 360) % 360,
  };
}

function oklchToLinearSrgb({ l, c, h }) {
  const radians = h * Math.PI / 180;
  return oklabToLinearSrgb({ l, a: c * Math.cos(radians), b: c * Math.sin(radians) });
}

function inSrgbGamut(channels) {
  return Object.values(channels).every((value) => value >= 0 && value <= 1);
}

function oklchToHex(color) {
  let chroma = color.c;
  let channels = oklchToLinearSrgb(color);
  if (!inSrgbGamut(channels)) {
    let low = 0;
    let high = chroma;
    for (let index = 0; index < 24; index += 1) {
      chroma = (low + high) / 2;
      channels = oklchToLinearSrgb({ ...color, c: chroma });
      if (inSrgbGamut(channels)) low = chroma;
      else high = chroma;
    }
    channels = oklchToLinearSrgb({ ...color, c: low });
  }
  return [channels.r, channels.g, channels.b]
    .map((value) => Math.round(Math.min(1, Math.max(0, linearToSrgb(value))) * 255).toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase()
    .padStart(7, "#");
}

export function modelColorForSlot(slot) {
  if (!Number.isInteger(slot) || slot < 0) throw new RangeError("Invalid model color slot");
  if (slot < BASE_MODEL_COLORS.length) return BASE_MODEL_COLORS[slot];

  const blockIndex = Math.floor(slot / COLORS_PER_BLOCK);
  const indexInBlock = slot % COLORS_PER_BLOCK;
  const tone = TONES[Math.floor(indexInBlock / BASE_MODEL_COLORS.length)];
  const family = indexInBlock % BASE_MODEL_COLORS.length;
  const base = hexToOklch(BASE_MODEL_COLORS[family]);
  const completedCycles = Math.floor(blockIndex / BLOCKS_PER_HUE_CYCLE);
  return oklchToHex({
    l: Math.min(0.86, Math.max(0.30, base.l + tone.lightnessDelta)),
    c: base.c * tone.chromaMultiplier,
    h: (base.h + blockIndex * 18 + completedCycles * HUE_CYCLE_OFFSET) % 360,
  });
}

export function chartColorMap(models) {
  return new Map(models.map((row, index) => [row.model, modelColorForSlot(index)]));
}
