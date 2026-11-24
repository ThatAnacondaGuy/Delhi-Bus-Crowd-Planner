import React, { createContext, useContext } from "react";
import { Sequence, useCurrentFrame, useVideoConfig } from "remotion";
import N from "../numbers.json";
import { C, Level, LEVELS, clamp01, inOutCubic, lerp, outCubic, prog } from "../theme";
import { Cam, Caption, Chip, Cursor, DrawBox, FadeIn, Phone, Scene, Sfx, Shot, Spot, TapRing, World } from "../components/ui";
import { R, capMeta, capUrl, cards, cx, cy } from "../captures";
import { sceneCaptionSpans } from "../captions";
import { LEAD_FRAMES, TAIL_FRAMES, shotStarts } from "../timing";
import { useAssets } from "../assets";
import { WHY } from "../layout";

/* ------------------------------------------------------------------ stage: the phone and the caption column */

type Stage = { x: number; y: number; scale: number };
const StageCtx = createContext<Stage>({ x: 190, y: 22, scale: 1 });
const PHONE_X = 190;
const PHONE_Y = 22;
const AX = 195;
const AY = 422;

const toCanvas = (st: Stage, sx: number, sy: number) => ({ x: st.x + 12 * st.scale + sx * st.scale, y: st.y + 12 * st.scale + sy * st.scale });

/** Camera over page coordinates: puts the centre of a rectangle at screen height `at`, zoom z. */
// gentle zoom (at most 1.12) keeps every card edge on screen
const focus = (r: R, z: number, at = 360): Cam => ({ wx: AX, wy: cy(r) + (AY - at) / z, z });
const TOP: Cam = { wx: AX, wy: AY, z: 1 };

function camAt(u: number, keys: [number, Cam][]): Cam {
  if (u <= keys[0][0]) return keys[0][1];
  for (let i = 1; i < keys.length; i++) {
    if (u <= keys[i][0]) {
      const [t0, c0] = keys[i - 1];
      const [t1, c1] = keys[i];
      const t = inOutCubic(clamp01((u - t0) / Math.max(1, t1 - t0)));
      return { wx: lerp(c0.wx, c1.wx, t), wy: lerp(c0.wy, c1.wy, t), z: lerp(c0.z, c1.z, t) };
    }
  }
  return keys[keys.length - 1][1];
}

/** Local frame of a shot, compressed when the shot is shorter than its nominal length (nothing is cut off). */
function useShot(nominal: number) {
  const f = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  return durationInFrames < nominal ? (f * nominal) / durationInFrames : f;
}

const PhoneStage: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const st = useContext(StageCtx);
  return (
    <div style={{ position: "absolute", left: st.x, top: st.y }}>
      <Phone scale={st.scale}>{children}</Phone>
    </div>
  );
};

const Col: React.FC<{ children: React.ReactNode; top?: number }> = ({ children, top = 150 }) => (
  <div style={{ position: "absolute", left: 760, top, width: 1060, display: "flex", flexDirection: "column", gap: 26 }}>{children}</div>
);

const Label: React.FC<{ children: React.ReactNode; size?: number; color?: string }> = ({ children, size = 56, color = C.ink }) => (
  <div style={{ fontSize: size, fontWeight: 700, color, lineHeight: 1.15 }}>{children}</div>
);

/** shows children between two frames with a short fade */
const Between: React.FC<{ u: number; from: number; to?: number; children: React.ReactNode; rise?: number }> = ({ u, from, to = 99999, children, rise = 14 }) => {
  const t = Math.min(prog(u, from, 12, outCubic), 1 - prog(u, to, 6));
  if (t <= 0) return null;
  return <div style={{ opacity: t, transform: `translateY(${(1 - t) * rise}px)` }}>{children}</div>;
};

const Route: React.FC<{ name: string }> = ({ name }) => {
  const q = capMeta(name).query;
  return (
    <div style={{ fontSize: 36, color: C.grey, fontWeight: 400 }}>
      {q.from} → {q.to} · {q.day === "weekend" ? "Weekend" : "Weekday"} {q.depart}
    </div>
  );
};

const worldImg = (name: string, extra?: React.ReactNode) => {
  const m = capMeta(name);
  return (
    <>
      <Shot src={capUrl(name)} w={m.w} h={m.h} />
      {extra}
    </>
  );
};

/* ------------------------------------------------------------------ 5a: journey 1 */

const S5a: React.FC = () => {
  const u = useShot(300);
  const name = "m-j1-full";
  const cs = cards(name);
  const keys: [number, Cam][] = [
    [0, TOP], [40, TOP], [85, focus(cs[0].chip, 1, 360)], [135, focus(cs[0].chip, 1.12, 330)], [170, focus(cs[0].chip, 1.12, 330)],
    [212, focus(cs[1].chip, 1, 360)], [255, focus(cs[1].chip, 1.12, 330)], [300, focus(cs[1].chip, 1.12, 330)],
  ];
  const cam = camAt(u, keys);
  const s0 = prog(u, 100, 18) * (1 - prog(u, 172, 14));
  const s1 = prog(u, 232, 18);
  return (
    <>
      <PhoneStage>
        <World cam={cam} ax={AX} ay={AY}>
          {worldImg(name)}
          <Spot r={cs[0].chip} amount={s0} color={C.amber} pad={8} radius={26} />
          <Spot r={cs[1].chip} amount={s1} color={C.teal} pad={8} radius={26} />
        </World>
      </PhoneStage>
      <Col>
        <FadeIn at={4}>
          <Route name={name} />
        </FadeIn>
        <Between u={u} from={56} to={196}>
          <Label color={C.grey}>Fastest</Label>
          <Chip level="standing" size={84} style={{ marginTop: 14 }} />
        </Between>
      </Col>
      <Col top={280}>
        <Between u={u} from={206}>
          <Label color={C.grey}>Less crowded</Label>
          <Chip level="seats" size={84} style={{ marginTop: 14 }} />
        </Between>
      </Col>
      <Sfx name="chime" at={236} volume={0.9} />
    </>
  );
};

/* ------------------------------------------------------------------ 5b: the reverse */

const S5b: React.FC = () => {
  const u = useShot(240);
  const m1 = capMeta("m-j1-full");
  const p = (m1.rects.presets as R[])[1];
  const tx = Math.min(cx(p), 352);
  const ty = cy(p);
  const cs = cards("m-j2-full");
  const keys: [number, Cam][] = [[0, TOP], [52, TOP], [90, focus(cs[0].chip, 1.12, 330)], [135, focus(cs[0].chip, 1.12, 330)], [178, focus(cs[1].chip, 1, 380)], [240, focus(cs[1].chip, 1, 380)]];
  const cam2 = camAt(u, keys);
  const swap = prog(u, 38, 10);
  return (
    <>
      <PhoneStage>
        <World cam={TOP} ax={AX} ay={AY} opacity={1 - swap}>
          {worldImg("m-j1-full")}
          <Cursor pts={[[6, 250, 470], [28, tx, ty]]} />
          <TapRing x={tx} y={ty} at={30} />
        </World>
        <World cam={cam2} ax={AX} ay={AY} opacity={swap}>
          {worldImg("m-j2-full")}
          <DrawBox r={cs[1].card} t={prog(u, 176, 22, outCubic)} color={C.amber} pad={4} radius={22} />
        </World>
      </PhoneStage>
      <Col>
        <FadeIn at={4}>
          <Label>The same road, the other direction</Label>
        </FadeIn>
        <Between u={u} from={60} to={170}>
          <Label color={C.grey}>Fastest</Label>
          <Chip level="crowded" size={84} style={{ marginTop: 14 }} />
        </Between>
      </Col>
      <Col top={330}>
        <Between u={u} from={178}>
          <Label color={C.grey}>Leave later</Label>
          <Chip level="standing" size={84} style={{ marginTop: 14 }} />
        </Between>
      </Col>
      <Sfx name="tap" at={30} />
      <Sfx name="chime" at={64} volume={0.9} />
    </>
  );
};

/* ------------------------------------------------------------------ 5c: Why? */

const S5c: React.FC = () => {
  const u = useShot(270);
  const st = useContext(StageCtx);
  const name = "m-j1-full";
  const cs = cards(name);
  const scrollY0 = cs[0].chip.y - 132; // where the app had scrolled to when the sheet was captured
  const base: Cam = { wx: AX, wy: scrollY0 + AY, z: 1 };
  const zoomTo: Cam = { wx: AX, wy: scrollY0 + WHY.focus.y, z: 1.12 };
  const cam = camAt(u, [[0, { ...base, wy: base.wy - 90 }], [32, base], [92, base], [140, zoomTo], [270, zoomTo]]);
  const why = cs[0].why;
  const rise = prog(u, 42, 24, outCubic);
  const dark = prog(u, 42, 14);
  const pt = (q: { x: number; y: number }) => {
    const sx = AX + (q.x - cam.wx) * cam.z;
    const sy = AY + (scrollY0 + q.y - cam.wy) * cam.z;
    return toCanvas(st, sx, sy);
  };
  const items: { at: number; label: string; sub: string; q: { x: number; y: number }; y: number }[] = [
    { at: 104, label: `about 1 in ${N.one_in} riders`, sub: "app tickets, scaled up to everyone on board", q: WHY.lead, y: 250 },
    { at: 128, label: "People on board", sub: "the range on the busiest stretch", q: WHY.people, y: 430 },
    { at: 152, label: "Seats", sub: "what the bus has", q: WHY.seats, y: 610 },
    { at: 176, label: "Rated total", sub: "seats plus standing places", q: WHY.rated, y: 760 },
  ];
  return (
    <>
      <PhoneStage>
        <World cam={cam} ax={AX} ay={AY}>
          {worldImg(name)}
          <Cursor pts={[[8, 300, scrollY0 + 640], [30, cx(why), cy(why)]]} />
          <TapRing x={cx(why)} y={cy(why)} at={34} />
          <div style={{ position: "absolute", left: 0, top: scrollY0, width: 390, height: 844, background: "#0d1117", opacity: 0.5 * dark }} />
          <div style={{ position: "absolute", left: 0, top: scrollY0 + WHY.panelTop, width: 390, height: 844 - WHY.panelTop, overflow: "hidden", transform: `translateY(${(1 - rise) * 440}px)` }}>
            <Shot src={capUrl("m-j1-why")} w={390} h={844} y={-WHY.panelTop} />
          </div>
        </World>
      </PhoneStage>
      <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0, pointerEvents: "none" }}>
        {items.map((it, i) => {
          const a = pt(it.q);
          const t = prog(u, it.at, 18, outCubic);
          const bx = 780;
          const by = it.y + 36;
          const len = Math.hypot(bx - a.x, by - a.y);
          return t > 0 ? (
            <g key={i} opacity={Math.min(1, t * 2)}>
              <line x1={a.x} y1={a.y} x2={bx} y2={by} stroke={C.blue} strokeWidth={3} strokeDasharray={len} strokeDashoffset={len * (1 - t)} />
              <circle cx={a.x} cy={a.y} r={8} fill={C.blue} />
            </g>
          ) : null;
        })}
      </svg>
      <FadeIn at={4} style={{ position: "absolute", left: 760, top: 120 }}>
        <Label>Tap Why?</Label>
      </FadeIn>
      {items.map((it, i) => (
        <div key={i} style={{ position: "absolute", left: 800, top: it.y }}>
          <Between u={u} from={it.at + 10}>
            <Label size={52} color={C.blue}>
              {it.label}
            </Label>
            <div style={{ fontSize: 36, color: C.grey, marginTop: 4 }}>{it.sub}</div>
          </Between>
        </div>
      ))}
      <Sfx name="tap" at={34} />
    </>
  );
};

/* ------------------------------------------------------------------ 5d: Mandi House to Laxmi Nagar */

const S5d: React.FC = () => {
  const u = useShot(330);
  const name = "m-j4-full";
  const cs = cards(name);
  const keys: [number, Cam][] = [
    [0, TOP], [35, TOP], [80, focus(cs[0].chip, 1, 360)], [125, focus(cs[0].chip, 1.12, 330)], [160, focus(cs[0].chip, 1.12, 330)],
    [210, focus(cs[1].chip, 1, 380)], [255, focus(cs[1].chip, 1.12, 340)], [330, focus(cs[1].chip, 1.12, 340)],
  ];
  const cam = camAt(u, keys);
  const arrow = prog(u, 168, 26, inOutCubic);
  return (
    <>
      <PhoneStage>
        <World cam={cam} ax={AX} ay={AY}>
          {worldImg(name)}
          <Spot r={cs[0].chip} amount={prog(u, 95, 16) * (1 - prog(u, 165, 12))} color={C.red} pad={8} radius={26} />
          <DrawBox r={cs[1].card} t={prog(u, 212, 22, outCubic)} color={C.amber} pad={4} radius={22} />
        </World>
      </PhoneStage>
      <Col top={130}>
        <FadeIn at={4}>
          <Route name={name} />
        </FadeIn>
        <Between u={u} from={60}>
          <Label color={C.grey}>Fastest</Label>
          <Chip level="crowded" size={84} style={{ marginTop: 14 }} />
        </Between>
        <div style={{ height: 70, marginLeft: 120 }}>
          <svg width={120} height={70} viewBox="0 0 120 70">
            <path d="M60 4 L60 56" stroke={C.grey} strokeWidth={5} strokeLinecap="round" fill="none" strokeDasharray={52} strokeDashoffset={52 * (1 - arrow)} />
            <path d="M44 42 L60 60 L76 42" stroke={C.grey} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" fill="none" opacity={arrow > 0.85 ? 1 : 0} />
          </svg>
        </div>
        <Between u={u} from={196}>
          <Label color={C.grey}>Leave later</Label>
          <Chip level="standing" size={84} style={{ marginTop: 14 }} />
        </Between>
      </Col>
      <Sfx name="ding" at={206} volume={0.5} />
    </>
  );
};

/* ------------------------------------------------------------------ 5e: Hindi, evidence, No data, the chip family */

const FAMILY: Level[] = ["seats", "standing", "crowded", "no_data"];

const S5e: React.FC = () => {
  const u = useShot(300);
  const m1 = capMeta("m-j1-full");
  const hi = m1.rects.langHi as R;
  const hiCs = cards("m-j1-hi-full");
  const seatCs = cards("m-j5-seat-full");
  const seatIdx = Math.max(0, seatCs.findIndex((c) => c.roles.includes("less_crowded")));
  const ndCs = cards("m-nodata-full");
  const toHi = prog(u, 28, 8);
  const toSeat = prog(u, 78, 8);
  const toND = prog(u, 124, 8);
  const hiCam = camAt(u, [[0, TOP], [40, TOP], [72, focus(hiCs[0].chip, 1.12, 330)], [300, focus(hiCs[0].chip, 1.12, 330)]]);
  const seatCam = camAt(u - 78, [[0, TOP], [14, TOP], [44, focus(seatCs[seatIdx].chip, 1, 380)], [300, focus(seatCs[seatIdx].chip, 1, 380)]]);
  const ndCam = camAt(u - 124, [[0, TOP], [10, TOP], [34, focus(ndCs[0].chip, 1.12, 330)], [300, focus(ndCs[0].chip, 1.12, 330)]]);
  const fam = (i: number) => prog(u, 192 + i * 12, 18, outCubic);
  const pulse = prog(u, 248, 24, inOutCubic);
  const hiPtr = { x: cx(hi), y: cy(hi) };
  const layer = (name: string, cam: Cam, op: number, extra?: React.ReactNode) =>
    op > 0 ? (
      <World cam={cam} ax={AX} ay={AY} opacity={op}>
        {worldImg(name, extra)}
      </World>
    ) : null;
  return (
    <>
      <PhoneStage>
        <World cam={TOP} ax={AX} ay={AY} opacity={1 - toHi}>
          {worldImg("m-j1-full")}
          <Cursor pts={[[6, 240, 440], [24, hiPtr.x, hiPtr.y]]} />
          <TapRing x={hiPtr.x} y={hiPtr.y} at={26} />
        </World>
        {layer("m-j1-hi-full", hiCam, toHi * (1 - toSeat))}
        {layer("m-j5-seat-full", seatCam, toSeat * (1 - toND), <Spot r={seatCs[seatIdx].card} amount={prog(u, 100, 14)} color={C.teal} pad={4} radius={22} />)}
        {layer("m-nodata-full", ndCam, toND, <DrawBox r={ndCs[0].chip} t={prog(u, 160, 24, outCubic)} color={C.grey} pad={6} radius={24} />)}
      </PhoneStage>

      <Col top={130}>
        <Between u={u} from={4} to={122}>
          <Label>Each card says how sure we are</Label>
        </Between>
        <Between u={u} from={126} to={186}>
          <Label color={C.grey}>Too little data?</Label>
          <Chip level="no_data" size={84} style={{ marginTop: 14 }} />
        </Between>
      </Col>
      <Col top={340}>
        <Between u={u} from={24} to={76}>
          <Label size={48} color={C.grey}>
            English · हिंदी
          </Label>
        </Between>
        <Between u={u} from={86} to={122}>
          <Label size={44} color={C.grey}>
            Rough guess · अंदाज़ा (कम टिकट)
          </Label>
        </Between>
      </Col>

      <Col top={40}>
        {FAMILY.map((lv, i) => (
          <div key={lv} style={{ opacity: fam(i), transform: `translateX(${(1 - fam(i)) * 80}px)`, display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-start" }}>
            <Chip
              level={lv}
              size={56}
              glow={lv === "no_data" ? Math.sin(pulse * Math.PI) : 0}
              style={{ transform: lv === "no_data" ? `scale(${1 + 0.06 * Math.sin(pulse * Math.PI)})` : undefined, transformOrigin: "left center" }}
            />
            <div style={{ fontSize: 38, color: LEVELS[lv].color, fontWeight: 700, paddingLeft: 12 }}>{LEVELS[lv].hi}</div>
          </div>
        ))}
        <Between u={u} from={236}>
          <div style={{ fontSize: 40, color: C.grey }}>Rough guess · अंदाज़ा (कम टिकट)</div>
          <div style={{ fontSize: 40, color: C.grey, marginTop: 8 }}>Based on many tickets · कई टिकटों पर आधारित</div>
        </Between>
      </Col>
      <Sfx name="tap" at={26} />
      <Sfx name="pop" at={248} volume={0.5} />
    </>
  );
};

/* ------------------------------------------------------------------ the scene */

const SHOTS = [S5a, S5b, S5c, S5d, S5e];

export const Scene05: React.FC = () => {
  const f = useCurrentFrame();
  const { durationInFrames: D } = useVideoConfig();
  const { parts, vo } = useAssets();
  const starts = shotStarts(D, parts);
  const ends = [...starts.slice(1), D];
  // phone: slides in over 24 frames, shrinks and moves left for the chip family, slides off in the last 24
  const k = Math.min(1, (ends[4] - starts[4]) / 300);
  const shrinkAt = starts[4] + Math.round(186 * k);
  const slideIn = prog(f, 0, 24, outCubic);
  const shrink = prog(f, shrinkAt, 24, inOutCubic);
  const off = prog(f, D - 24, 24, inOutCubic);
  const scale = lerp(1, 0.7, shrink);
  const x = lerp(-480, PHONE_X, slideIn) - 100 * shrink - off * 760;
  const y = lerp(PHONE_Y, 190, shrink);
  const stage: Stage = { x, y, scale };

  // captions: each part's text is spread over its own span of the voice
  const spans = sceneCaptionSpans(5, { voFrames: vo[4] != null ? Math.round(vo[4]! * 30) : null, duration: D, base: 1440, lead: LEAD_FRAMES, tail: TAIL_FRAMES, partStarts: starts });
  return (
    <Scene>
      <StageCtx.Provider value={stage}>
        {SHOTS.map((S, i) => (
          <Sequence key={i} from={starts[i]} durationInFrames={Math.max(1, ends[i] - starts[i])} layout="none" name={`5${"abcde"[i]}`}>
            <S />
          </Sequence>
        ))}
      </StageCtx.Provider>
      <Caption spans={spans} bottom={30} />
    </Scene>
  );
};
