// Scene 5: the planner on a phone, five shots cut at the four pauses between the five recorded parts (5a to 5e).
// Phrases (cue index): 5a 0-2, 5b 3-6, 5c 7-9, 5d 10-13, 5e 14-17. Every tap, chip, camera move and label lands on its phrase.
import React, { createContext, useContext } from "react";
import { Sequence, useCurrentFrame, useVideoConfig } from "remotion";
import N from "../numbers.json";
import { C, Level, LEVELS, RADIUS, SHADOW, TYPE, clamp01, inOutCubic, lerp, outCubic, prog, springSoft } from "../design";
import { Backdrop, Cam, Captions, Chapter, DrawBox, FitText, Phone, PopChip, SceneShell, Sfx, Shot, SoftCursor, Spot, TapRipple, World, camAt, ordered, useBeats } from "../components/kit";
import { R, capMeta, capUrl, cards, cx, cy } from "../captures";
import { WHY } from "../layout";

/* ------------------------------------------------------------------ stage */

const SCALE = 1.06;
const PHONE_X = 250;
const PHONE_Y = 70;
const AX = 195; // camera anchor inside the 390x844 screen
const AY = 422;
const COL_X = 860;
const COL_W = 1824 - COL_X;

type Stage = { x: number; y: number; scale: number };
const StageCtx = createContext<Stage>({ x: PHONE_X, y: PHONE_Y, scale: SCALE });
/** Shot-local frame of phrase i (k of the way through it). */
const ShotCtx = createContext<{ start: number }>({ start: 0 });

function useShotBeats() {
  const { beat, end } = useBeats();
  const { start } = useContext(ShotCtx);
  return { at: (i: number, k = 0) => beat(i, k) - start, end: (i: number) => end(i) - start };
}

const BEZEL = 13;
const toCanvas = (st: Stage, sx: number, sy: number) => ({ x: st.x + BEZEL * st.scale + sx * st.scale, y: st.y + BEZEL * st.scale + sy * st.scale });
// zoom stays at most about 1.12: the cards span x 16..374 of the 390 px screen, so more would cut their edges
const focus = (r: R, z0: number, at = 380): Cam => {
  const z = Math.min(1.12, z0 * 1.02);
  return { wx: AX, wy: cy(r) + (AY - at) / z, z };
};
const TOP: Cam = { wx: AX, wy: AY, z: 1 };

const PhoneStage: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const st = useContext(StageCtx);
  return (
    <div style={{ position: "absolute", left: st.x, top: st.y }}>
      <Phone scale={st.scale}>{children}</Phone>
    </div>
  );
};

/** A block in the right column: rises in with the soft spring on `from`, leaves on `to`. */
const Slot: React.FC<{ from: number; to?: number; top: number; children: React.ReactNode }> = ({ from, to = 1e9, top, children }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = springSoft(f, fps, from, 20) * (1 - prog(f, to, 8, inOutCubic));
  if (t <= 0.001) return null;
  return <div style={{ position: "absolute", left: COL_X, top, width: COL_W, opacity: t, transform: `translateY(${(1 - t) * 26}px)` }}>{children}</div>;
};

const Kicker: React.FC<{ text: string; color?: string }> = ({ text, color = C.textDim }) => <FitText text={text} size={TYPE.label} width={COL_W} weight={600} color={color} />;
const Head: React.FC<{ text: string; color?: string }> = ({ text, color = C.text }) => <FitText text={text} size={TYPE.h2} width={COL_W} maxLines={2} weight={800} color={color} lineHeight={1.12} />;

const Route: React.FC<{ name: string }> = ({ name }) => {
  const q = capMeta(name).query;
  return <Kicker text={`${q.from} → ${q.to} · ${q.day === "weekend" ? "Weekend" : "Weekday"} ${q.depart}`} />;
};

/** Role label + chip, the chip popping on `at`. */
const Verdict: React.FC<{ role: string; level: Level; at: number }> = ({ role, level, at }) => (
  <>
    <FitText text={role} size={TYPE.body} width={COL_W} weight={600} color={C.textDim} />
    <div style={{ marginTop: 14, height: 90 }}>
      <PopChip level={level} at={at} size={TYPE.h2} />
    </div>
  </>
);

const page = (name: string, extra?: React.ReactNode) => {
  const m = capMeta(name);
  return (
    <>
      <Shot src={capUrl(name)} w={m.w} h={m.h} />
      {extra}
    </>
  );
};

/* ------------------------------------------------------------------ 5a: the brief's example */

const S5a: React.FC = () => {
  const u = useCurrentFrame();
  const { at } = useShotBeats();
  const name = "m-j1-full";
  const cs = cards(name);
  const cam = camAt(u, ordered([[0, TOP], [at(1) - 14, TOP], [at(1) + 14, focus(cs[0].chip, 1.1)], [at(2) - 8, focus(cs[0].chip, 1.1)], [at(2) + 18, focus(cs[1].chip, 1.1)]]));
  const s0 = prog(u, at(1), 10) * (1 - prog(u, at(2) - 6, 8));
  const s1 = prog(u, at(2) + 8, 10);
  return (
    <>
      <PhoneStage>
        <World cam={cam} ax={AX} ay={AY}>
          {page(name)}
          <Spot r={cs[0].chip} amount={s0} color={C.amberGlow} pad={8} radius={26} />
          <Spot r={cs[1].chip} amount={s1} color={C.tealGlow} pad={8} radius={26} />
        </World>
      </PhoneStage>
      <Slot from={at(0) - 6} top={150}>
        <Route name={name} />
        <div style={{ height: 14 }} />
        <Head text="The brief's own example, six in the evening" />
      </Slot>
      <Slot from={at(1) - 2} top={400}>
        <Verdict role="Fastest" level="standing" at={at(1) + 4} />
      </Slot>
      <Slot from={at(2) - 2} top={600}>
        <Verdict role="Less crowded · a slightly slower bus" level="seats" at={at(2) + 4} />
      </Slot>
      <Sfx name="pop" at={at(1) + 4} volume={0.45} />
      <Sfx name="pop" at={at(2) + 4} volume={0.45} />
      <Sfx name="chime" at={at(2) + 8} volume={0.55} />
    </>
  );
};

/* ------------------------------------------------------------------ 5b: the reverse */

const S5b: React.FC = () => {
  const u = useCurrentFrame();
  const { at } = useShotBeats();
  const m1 = capMeta("m-j1-full");
  const p = (m1.rects.presets as R[])[1];
  const tx = Math.min(cx(p), 352);
  const ty = cy(p);
  const tap = at(3) + 16;
  const swap = prog(u, tap + 8, 10);
  const cs = cards("m-j2-full");
  const cam2 = camAt(u, ordered([[0, TOP], [at(4) - 12, TOP], [at(4) + 14, focus(cs[0].chip, 1.1)], [at(6) - 10, focus(cs[0].chip, 1.1)], [at(6) + 16, focus(cs[1].chip, 1.04, 400)]]));
  return (
    <>
      <PhoneStage>
        <World cam={TOP} ax={AX} ay={AY} opacity={1 - swap}>
          {page("m-j1-full")}
          <SoftCursor pts={[[Math.max(2, tap - 22), 250, 470], [tap, tx, ty]]} hideAfter={6} />
          <TapRipple x={tx} y={ty} at={tap} />
        </World>
        <World cam={cam2} ax={AX} ay={AY} opacity={swap}>
          {page("m-j2-full")}
          <Spot r={cs[0].chip} amount={prog(u, at(4), 10) * (1 - prog(u, at(6) - 4, 8))} color={C.redGlow} pad={8} radius={26} />
          <DrawBox r={cs[1].card} t={prog(u, at(6) + 6, 20, outCubic)} color={C.amberGlow} pad={4} radius={22} />
        </World>
      </PhoneStage>
      <Slot from={at(3) - 6} top={150}>
        <Route name="m-j2-full" />
        <div style={{ height: 14 }} />
        <Head text="Reverse it, and the answer changes" />
      </Slot>
      <Slot from={at(4) - 2} to={at(6) - 4} top={400}>
        <Verdict role="Fastest" level="crowded" at={at(4) + 4} />
      </Slot>
      <Slot from={at(5) - 2} to={at(6) - 4} top={600}>
        <FitText text="Same road, the other direction" size={TYPE.body} width={COL_W} weight={600} color={C.text} />
      </Slot>
      <Slot from={at(6) - 2} top={400}>
        <Verdict role="Leave later" level="standing" at={at(6) + 6} />
      </Slot>
      <Sfx name="tap" at={tap} volume={0.45} />
      <Sfx name="pop" at={at(4) + 4} volume={0.45} />
      <Sfx name="ding" at={at(6) + 6} volume={0.4} />
    </>
  );
};

/* ------------------------------------------------------------------ 5c: Why? */

const S5c: React.FC = () => {
  const u = useCurrentFrame();
  const { at, end } = useShotBeats();
  const st = useContext(StageCtx);
  const name = "m-j1-full";
  const cs = cards(name);
  const scrollY0 = cs[0].chip.y - 132; // where the app had scrolled to when the sheet was captured
  const base: Cam = { wx: AX, wy: scrollY0 + AY, z: 1 };
  const zoomTo: Cam = { wx: AX, wy: scrollY0 + WHY.focus.y, z: 1.08 };
  const tap = at(7) + 10;
  const cam = camAt(u, ordered([[0, { ...base, wy: base.wy - 90 }], [Math.max(1, tap - 12), base], [tap + 30, base], [at(8) + 10, zoomTo]]));
  const why = cs[0].why;
  const rise = prog(u, tap + 4, 20, outCubic);
  const dark = prog(u, tap + 4, 12);
  const pt = (q: { x: number; y: number }) => toCanvas(st, AX + (q.x - cam.wx) * cam.z, AY + (scrollY0 + q.y - cam.wy) * cam.z);
  const span9 = Math.max(30, end(9) - at(9));
  const items = [
    { at: at(8), label: `about 1 in ${N.one_in} riders`, sub: "app tickets, scaled up to everyone on board", q: WHY.lead, y: 300 },
    { at: at(9), label: "People on board", sub: "the range on the busiest stretch", q: WHY.people, y: 470 },
    { at: at(9) + span9 * 0.33, label: "Seats", sub: "what the bus has", q: WHY.seats, y: 610 },
    { at: at(9) + span9 * 0.66, label: "Rated total", sub: "seats plus standing places", q: WHY.rated, y: 750 },
  ];
  return (
    <>
      <PhoneStage>
        <World cam={cam} ax={AX} ay={AY}>
          {page(name)}
          <SoftCursor pts={[[Math.max(2, tap - 20), 300, scrollY0 + 640], [tap, cx(why), cy(why)]]} hideAfter={6} />
          <TapRipple x={cx(why)} y={cy(why)} at={tap} />
          <div style={{ position: "absolute", left: 0, top: scrollY0, width: 390, height: 844, background: "#0d1117", opacity: 0.5 * dark }} />
          <div style={{ position: "absolute", left: 0, top: scrollY0 + WHY.panelTop, width: 390, height: 844 - WHY.panelTop, overflow: "hidden", transform: `translateY(${(1 - rise) * 440}px)` }}>
            <Shot src={capUrl("m-j1-why")} w={390} h={844} y={-WHY.panelTop} />
          </div>
        </World>
      </PhoneStage>
      <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0, pointerEvents: "none" }}>
        {items.map((it, i) => {
          const a = pt(it.q);
          const t = prog(u, it.at, 16, outCubic);
          const bx = COL_X - 24;
          const by = it.y + 30;
          const len = Math.hypot(bx - a.x, by - a.y);
          return t > 0 ? (
            <g key={i}>
              <line x1={a.x} y1={a.y} x2={bx} y2={by} stroke={C.blueGlow} strokeWidth={3} strokeDasharray={len} strokeDashoffset={len * (1 - t)} />
              <circle cx={a.x} cy={a.y} r={8} fill={C.blueGlow} opacity={t} />
              <circle cx={a.x} cy={a.y} r={8 + 14 * t} fill="none" stroke={C.blueGlow} strokeWidth={2} opacity={1 - t} />
            </g>
          ) : null;
        })}
      </svg>
      <Slot from={at(7) - 6} top={150}>
        <Head text="Tap Why?" />
      </Slot>
      {items.map((it, i) => (
        <Slot key={i} from={it.at + 8} top={it.y}>
          <FitText text={it.label} size={TYPE.body} width={COL_W} weight={800} color={C.blueGlow} />
          <FitText text={it.sub} size={TYPE.label} width={COL_W} weight={500} color={C.textDim} style={{ marginTop: 4 }} />
        </Slot>
      ))}
      <Sfx name="tap" at={tap} volume={0.45} />
      {items.map((it, i) => (
        <Sfx key={i} name="pop" at={it.at + 8} volume={0.3} />
      ))}
    </>
  );
};

/* ------------------------------------------------------------------ 5d: Mandi House to Laxmi Nagar */

const S5d: React.FC = () => {
  const u = useCurrentFrame();
  const { at } = useShotBeats();
  const name = "m-j4-full";
  const cs = cards(name);
  const cam = camAt(u, ordered([[0, TOP], [at(10) + 10, TOP], [at(10) + 34, focus(cs[0].chip, 1.1)], [at(11) - 6, focus(cs[0].chip, 1.1)], [at(11) + 24, focus(cs[1].chip, 1.04, 400)]]));
  const arrow = prog(u, at(11), 22, inOutCubic);
  return (
    <>
      <PhoneStage>
        <World cam={cam} ax={AX} ay={AY}>
          {page(name)}
          <Spot r={cs[0].chip} amount={prog(u, at(10) + 20, 12) * (1 - prog(u, at(11) - 2, 8))} color={C.redGlow} pad={8} radius={26} />
          <DrawBox r={cs[1].card} t={prog(u, at(12), 22, outCubic)} color={C.amberGlow} pad={4} radius={22} />
        </World>
      </PhoneStage>
      <Slot from={at(10) - 6} top={150}>
        <Route name={name} />
        <div style={{ height: 14 }} />
        <Verdict role="Fastest" level="crowded" at={at(10) + 20} />
      </Slot>
      <div style={{ position: "absolute", left: COL_X + 40, top: 420, opacity: clamp01(arrow * 2) }}>
        <svg width={80} height={90} viewBox="0 0 80 90">
          <path d="M40 4 L40 74" stroke={C.textDim} strokeWidth={5} strokeLinecap="round" fill="none" strokeDasharray={70} strokeDashoffset={70 * (1 - arrow)} />
          <path d="M22 56 L40 78 L58 56" stroke={C.textDim} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" fill="none" opacity={arrow > 0.85 ? 1 : 0} />
        </svg>
      </div>
      <Slot from={at(11)} top={530}>
        <FitText text="Leave a little later" size={TYPE.body} width={COL_W} weight={600} color={C.textDim} />
        <div style={{ marginTop: 14, height: 90 }}>
          <PopChip level="standing" at={at(12)} size={TYPE.h2} />
        </div>
      </Slot>
      <Slot from={at(13) - 2} top={760}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <svg width={40} height={40} viewBox="0 0 40 40">
            <circle cx="20" cy="20" r="18" fill="none" stroke={C.tealGlow} strokeWidth="3" />
            <path d="M11 21 L18 28 L30 13" fill="none" stroke={C.tealGlow} strokeWidth="4.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <FitText text="Offered only when it's really better" size={TYPE.body} width={COL_W - 60} weight={600} color={C.text} />
        </div>
      </Slot>
      <Sfx name="pop" at={at(10) + 20} volume={0.45} />
      <Sfx name="ding" at={at(12)} volume={0.4} />
    </>
  );
};

/* ------------------------------------------------------------------ 5e: how sure, No data, the chip family */

const FAMILY: Level[] = ["seats", "standing", "crowded", "no_data"];

const EvidencePill: React.FC<{ en: string; hi: string; glow: number }> = ({ en, hi, glow }) => (
  <div style={{ display: "inline-flex", alignItems: "center", gap: 14, padding: "12px 24px", borderRadius: RADIUS.pill, background: "rgba(255,255,255,0.08)", border: `2px solid rgba(255,255,255,${0.18 + 0.5 * glow})`, boxShadow: glow ? `0 0 ${30 * glow}px ${C.amberGlow}55` : undefined }}>
    <span style={{ fontSize: TYPE.label, fontWeight: 700, color: C.text, whiteSpace: "nowrap" }}>{en}</span>
    <span style={{ fontSize: TYPE.label, fontWeight: 500, color: C.textDim, whiteSpace: "nowrap" }}>· {hi}</span>
  </div>
);

const S5e: React.FC = () => {
  const u = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { at } = useShotBeats();
  const m1 = capMeta("m-j1-full");
  const hi = m1.rects.langHi as R;
  const hiCs = cards("m-j1-hi-full");
  const ndCs = cards("m-nodata-full");
  const tap = at(14) + 8;
  const toHi = prog(u, tap + 8, 8);
  const toND = prog(u, at(16) - 4, 8);
  const hiCam = camAt(u, ordered([[0, TOP], [tap + 14, TOP], [tap + 40, focus(hiCs[0].evidence ?? hiCs[0].chip, 1.1, 420)]]));
  const ndCam = camAt(u, ordered([[0, TOP], [at(16), TOP], [at(16) + 24, focus(ndCs[0].chip, 1.1, 380)]]));
  const rough = prog(u, at(15), 10) * (1 - prog(u, at(16) - 6, 8));
  const famAt = at(17) - 4;
  return (
    <>
      <PhoneStage>
        <World cam={TOP} ax={AX} ay={AY} opacity={1 - toHi}>
          {page("m-j1-full")}
          <SoftCursor pts={[[Math.max(2, tap - 20), 240, 440], [tap, cx(hi), cy(hi)]]} hideAfter={6} />
          <TapRipple x={cx(hi)} y={cy(hi)} at={tap} />
        </World>
        {toHi > 0 && toND < 1 ? (
          <World cam={hiCam} ax={AX} ay={AY} opacity={toHi * (1 - toND)}>
            {page("m-j1-hi-full")}
            {hiCs[0].evidence ? <Spot r={hiCs[0].evidence} amount={prog(u, at(15), 10)} color={C.amberGlow} pad={6} radius={10} /> : null}
          </World>
        ) : null}
        {toND > 0 ? (
          <World cam={ndCam} ax={AX} ay={AY} opacity={toND}>
            {page("m-nodata-full", <DrawBox r={ndCs[0].chip} t={prog(u, at(16) + 20, 24, outCubic)} color={C.grey} pad={6} radius={24} />)}
          </World>
        ) : null}
      </PhoneStage>

      <Slot from={at(14) - 6} to={famAt} top={150}>
        <Kicker text="English · हिंदी" />
        <div style={{ height: 14 }} />
        <Head text="Each card says how sure we are" />
      </Slot>
      <Slot from={at(14) + 16} to={at(16) - 6} top={420}>
        <EvidencePill en="Rough guess" hi="अंदाज़ा (कम टिकट)" glow={rough} />
        <div style={{ height: 18 }} />
        <EvidencePill en="Based on many tickets" hi="कई टिकटों पर आधारित" glow={0} />
      </Slot>
      <Slot from={at(16) - 2} to={famAt} top={420}>
        <Verdict role="Too little data?" level="no_data" at={at(16) + 8} />
      </Slot>

      {/* the chip family, with the Hindi the app shows */}
      <div style={{ position: "absolute", left: COL_X, top: 130, width: COL_W }}>
        {FAMILY.map((lv, i) => {
          const t = springSoft(u, fps, famAt + i * 5, 18);
          if (t <= 0.001) return null;
          return (
            <div key={lv} style={{ position: "absolute", left: 0, top: i * 172, opacity: t, transform: `translateX(${(1 - t) * 60}px)` }}>
              <PopChip level={lv} at={famAt + i * 5} size={TYPE.body} />
              <div style={{ marginTop: 10, paddingLeft: 16 }}>
                <FitText text={LEVELS[lv].hi} size={TYPE.label} width={COL_W - 16} weight={600} color={LEVELS[lv].glow} />
              </div>
            </div>
          );
        })}
      </div>
      <Sfx name="tap" at={tap} volume={0.45} />
      <Sfx name="pop" at={at(16) + 8} volume={0.45} />
      {FAMILY.map((_, i) => (
        <Sfx key={i} name="pop" at={famAt + i * 5} volume={0.3} />
      ))}
    </>
  );
};

/* ------------------------------------------------------------------ the scene */

const SHOTS = [S5a, S5b, S5c, S5d, S5e];

export const Scene05: React.FC = () => {
  const f = useCurrentFrame();
  const { durationInFrames: D, fps } = useVideoConfig();
  const { tl, beat } = useBeats();
  const starts = tl.shots;
  const ends = [...starts.slice(1), D];
  const slideIn = springSoft(f, fps, 0, 26);
  const off = prog(f, D - 16, 16, inOutCubic);
  const shrink = prog(f, beat(17) - 8, 18, inOutCubic);
  const float = Math.sin(f / 45) * 6;
  const scale = lerp(SCALE, SCALE * 0.94, shrink);
  const x = lerp(-520, PHONE_X, slideIn) - off * 900;
  const y = PHONE_Y + float + shrink * 20;
  const stage: Stage = { x, y, scale };
  return (
    <SceneShell>
      <Backdrop tint={[C.blue, C.teal, "#40275a"]} />
      <Chapter n="03" text="The planner" hold={starts[1] - 20} x={COL_X} />
      <StageCtx.Provider value={stage}>
        {SHOTS.map((S, i) => (
          <Sequence key={i} from={starts[i]} durationInFrames={Math.max(1, ends[i] - starts[i])} layout="none" name={`5${"abcde"[i]}`}>
            <ShotCtx.Provider value={{ start: starts[i] }}>
              <S />
            </ShotCtx.Provider>
          </Sequence>
        ))}
      </StageCtx.Provider>
      {/* shot changes: a soft flash on the phone glass */}
      {starts.slice(1).map((s, i) => {
        const t = 1 - Math.abs(f - s) / 6;
        return t > 0 ? <div key={i} style={{ position: "absolute", left: x + 14 * scale, top: y + 14 * scale, width: 390 * scale, height: 844 * scale, borderRadius: 47 * scale, background: "#ffffff", opacity: 0.35 * t }} /> : null;
      })}
      <Captions region={[COL_X - 24, 1824]} />
      {starts.slice(1).map((s, i) => (
        <Sfx key={i} name="swoop" at={s - 4} volume={0.18} len={30} />
      ))}
    </SceneShell>
  );
};
