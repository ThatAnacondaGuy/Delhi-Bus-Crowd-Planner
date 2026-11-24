// Voice-driven timing. Pure functions, no imports, so `node --test` runs them directly (tests/sync.test.mjs).
//
// 1. scan_assets.mjs runs ffmpeg silencedetect on every clean voice file and stores the silences in public/assets.json.
// 2. speechFromSilences() turns those silences into speech segments (seconds from the start of the clean file).
// 3. mapCues() places the script's phrases on the segments in order: every phrase boundary goes to a real pause between
//    segments, chosen so each phrase's share of the speaking time is closest to its share of the script's characters.
//    When there are fewer pauses than boundaries, the remaining boundaries split a segment by relative character length.
// Captions and every visual beat are keyed to the cue times this returns.

export type Seg = [number, number];
export type Cue = { text: string; from: number; to: number; split: boolean };

/** Speech segments = the complement of the detected silences inside [0, dur]; tiny blips (< minSpeech s) are dropped. */
export function speechFromSilences(silences: Seg[], dur: number, minSpeech = 0.08): Seg[] {
  const sil = [...silences].map(([a, b]) => [Math.max(0, a), Math.min(dur, b)] as Seg).filter(([a, b]) => b > a).sort((x, y) => x[0] - y[0]);
  const out: Seg[] = [];
  let at = 0;
  for (const [a, b] of sil) {
    if (a > at) out.push([at, a]);
    at = Math.max(at, b);
  }
  if (dur > at) out.push([at, dur]);
  return out.filter(([a, b]) => b - a >= minSpeech).map(([a, b]) => [round3(a), round3(b)] as Seg);
}

const round3 = (x: number) => Math.round(x * 1000) / 1000;

/** Characters that take speaking time (letters and digits; a digit is said as roughly three letters). */
export function speechWeight(text: string): number {
  let w = 0;
  for (const ch of text) {
    if (/[0-9]/.test(ch)) w += 3;
    else if (/[\p{L}]/u.test(ch)) w += 1;
    else if (ch === " ") w += 0.4;
  }
  return Math.max(1, w);
}

const GAP_BONUS = 0.06; // per second of pause (up to 1.2 s): a long pause is a likelier phrase boundary
const SPLIT_COST = 0.16; // a boundary with no pause under it

/**
 * Phrases -> cues (seconds). segs must be sorted and non-overlapping.
 * Boundary k (between phrase k-1 and k) goes either to a pause j (between segs[j] and segs[j+1]) or, when no pause fits,
 * to the point of the speaking time that matches its character share ("split").
 */
export function mapCues(texts: string[], segs: Seg[]): Cue[] {
  const N = texts.length;
  if (N === 0) return [];
  if (segs.length === 0) return texts.map((text) => ({ text, from: 0, to: 0, split: true }));
  const M = segs.length;
  const speech = segs.map(([a, b]) => b - a);
  const total = speech.reduce((a, b) => a + b, 0);
  const cumAfter: number[] = []; // speaking-time fraction at the end of seg j
  speech.reduce((acc, s, j) => ((cumAfter[j] = (acc + s) / total), acc + s), 0);
  const w = texts.map(speechWeight);
  const wsum = w.reduce((a, b) => a + b, 0);
  const target: number[] = []; // target fraction for boundary k = 1..N-1 (index k-1)
  w.reduce((acc, x, i) => (i < N - 1 && target.push((acc + x) / wsum), acc + x), 0);

  // memoised DP over (boundary k, last pause used j, whether the previous boundary was a split)
  type Res = { cost: number; picks: (number | null)[] };
  const memo = new Map<string, Res>();
  const solve = (k: number, lastJ: number, lastPos: number): Res => {
    if (k > N - 1) return { cost: 0, picks: [] };
    const key = `${k}|${lastJ}|${lastPos.toFixed(5)}`;
    const hit = memo.get(key);
    if (hit) return hit;
    const t = target[k - 1];
    let best: Res = { cost: Infinity, picks: [] };
    // a pause j > lastJ whose position is after the previous boundary, leaving enough pauses is not required (splits exist)
    for (let j = lastJ + 1; j < M - 1; j++) {
      const p = cumAfter[j];
      if (p <= lastPos + 1e-9) continue;
      const gap = segs[j + 1][0] - segs[j][1];
      const c = Math.abs(p - t) - GAP_BONUS * Math.min(gap, 1.2);
      const rest = solve(k + 1, j, p);
      if (c + rest.cost < best.cost) best = { cost: c + rest.cost, picks: [j, ...rest.picks] };
    }
    if (t > lastPos + 1e-6) {
      const rest = solve(k + 1, lastJ, t);
      if (SPLIT_COST + rest.cost < best.cost) best = { cost: SPLIT_COST + rest.cost, picks: [null, ...rest.picks] };
    }
    memo.set(key, best);
    return best;
  };
  const picks = solve(1, -1, 0).picks;

  // speaking-time fraction -> seconds in the file
  const timeAt = (frac: number) => {
    let acc = 0;
    for (let j = 0; j < M; j++) {
      const s = speech[j] / total;
      if (frac <= acc + s + 1e-9) return segs[j][0] + ((frac - acc) / s) * speech[j];
      acc += s;
    }
    return segs[M - 1][1];
  };

  const cues: Cue[] = [];
  let from = segs[0][0];
  let fromSplit = false;
  for (let i = 0; i < N; i++) {
    let to: number;
    let next: number;
    let split = false;
    if (i === N - 1) {
      to = segs[M - 1][1];
      next = to;
    } else {
      const j = picks[i];
      if (j == null) {
        to = next = timeAt(target[i]);
        split = true;
      } else {
        to = segs[j][1];
        next = segs[j + 1][0];
      }
    }
    cues.push({ text: texts[i], from: round3(from), to: round3(to), split: fromSplit });
    from = next;
    fromSplit = split;
  }
  return cues;
}

/** The segments that fall inside [a, b) (seconds), clipped. */
export function segsWithin(segs: Seg[], a: number, b: number): Seg[] {
  return segs
    .filter(([s, e]) => e > a && s < b)
    .map(([s, e]) => [Math.max(s, a), Math.min(e, b)] as Seg)
    .filter(([s, e]) => e - s > 0.02);
}

/** Without a voice file: spread the phrases over [a, b] by character share (the script's own pace). */
export function spreadCues(texts: string[], a: number, b: number): Cue[] {
  const w = texts.map(speechWeight);
  const sum = w.reduce((x, y) => x + y, 0);
  let at = a;
  return texts.map((text, i) => {
    const len = ((b - a) * w[i]) / sum;
    const c = { text, from: round3(at), to: round3(at + len * 0.92), split: true };
    at += len;
    return c;
  });
}

/* ------------------------------------------------------------------ caption lines */

/** At most two lines of at most maxChars characters, balanced (the break that makes the lines most even). */
export function wrapCaption(text: string, maxChars = 42): string[] {
  const t = text.trim().replace(/\s+/g, " ");
  if (t.length <= maxChars) return [t];
  const words = t.split(" ");
  let best: string[] | null = null;
  let bestScore = Infinity;
  for (let i = 1; i < words.length; i++) {
    const a = words.slice(0, i).join(" ");
    const b = words.slice(i).join(" ");
    if (a.length > maxChars || b.length > maxChars) continue;
    // even lines, and a slight preference for breaking after punctuation
    const sc = Math.abs(a.length - b.length) - (/[,:;—–-]$/.test(a) ? 6 : 0);
    if (sc < bestScore) {
      bestScore = sc;
      best = [a, b];
    }
  }
  if (!best) throw new Error(`caption does not fit two lines of ${maxChars} characters: "${t}"`);
  return best;
}

/** Font size that makes a measured width fit an available width (never above the scale size, never below the floor). */
export function fitSize(widthAtSize: number, size: number, available: number, floor = 32): number {
  if (widthAtSize <= available) return size;
  return Math.max(floor, Math.floor((size * available) / widthAtSize));
}
