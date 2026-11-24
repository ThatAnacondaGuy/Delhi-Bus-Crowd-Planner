// Scene 6: the operator view on a laptop. The laptop rises on phrase 0; the camera finds the ranked table and the cursor
// picks row 1 on "Where would one extra trip help most?" (1); the trip is named on (2); the counters run on (3) and (4);
// the corridor map's time slider sweeps the day from phrase 4 on; "Model estimates, not counts." lands on (5).
import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import N from "../numbers.json";
import { C, RADIUS, SHADOW, TYPE, inOutCubic, lerp, outCubic, prog, springSoft } from "../design";
import { Backdrop, Cam, Captions, Chapter, Counter, DrawBox, FitText, Laptop, SceneShell, Sfx, Shot, SoftCursor, StylisedMap, TapRipple, World, camAt, fitLine, ordered, useBeats } from "../components/kit";
import { R, capMeta, capUrl, cx, cy } from "../captures";

const SCALE = 0.74;
const LX = 96;
const LY = 170;
const SX = 720; // camera anchor in screen coordinates
const SY = 450;
const PX = 1290; // right panel
const PW = 1824 - PX;

const MAP_FIRST = 18; // o-map-18 = 09:00, one every half hour
const MAP_LAST = 38; // 19:00
const clock = (minutes: number) => {
  const m = Math.round(minutes / 5) * 5;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
};

const Panel: React.FC<{ from: number; to?: number; top: number; children: React.ReactNode }> = ({ from, to = 1e9, top, children }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = springSoft(f, fps, from, 20) * (1 - prog(f, to, 8, inOutCubic));
  if (t <= 0.001) return null;
  return <div style={{ position: "absolute", left: PX, top, width: PW, opacity: t, transform: `translateY(${(1 - t) * 24}px)` }}>{children}</div>;
};

export const Scene06: React.FC = () => {
  const f = useCurrentFrame();
  const { fps, durationInFrames: D } = useVideoConfig();
  const { beat } = useBeats();
  const [b0, b1, b2, b3, b4, b5] = [0, 1, 2, 3, 4, 5].map((i) => beat(i));
  const full = capMeta("o-full-selected");
  const rects = full.rects as Record<string, R>;
  const mapCard = capMeta("o-full").rects.map as R;
  const row1 = rects.row1;

  const top: Cam = { wx: SX, wy: SY, z: 1 };
  // the table fills the screen edge to edge (page x 4..964) so the map panel on its right is never cut in half
const tableCam: Cam = { wx: 484, wy: cy(row1) + (SY - 330) / 1.5, z: 1.5 };
  const mapCam: Cam = { wx: cx(mapCard) - 40, wy: cy(mapCard), z: 1.3 };
  const cam = camAt(f, ordered([[0, top], [b1 - 6, top], [b1 + 30, tableCam], [b4 - 8, tableCam], [b4 + 26, mapCam]]));

  const sweepFrom = b4 + 20;
  const sweepTo = D - 24;
  const t = prog(f, sweepFrom, sweepTo - sweepFrom, inOutCubic);
  const v = lerp(MAP_FIRST, MAP_LAST, t);
  const lo = Math.floor(v);
  const hi = Math.min(MAP_LAST, lo + 1);
  const frac = v - lo;
  const mk = (n: number) => `o-map-${String(n).padStart(2, "0")}`;
  const mapOpacity = prog(f, b4 + 10, 12);
  const minutes = 540 + 600 * t;

  const rise = springSoft(f, fps, b0 - 10, 30);
  const tap = b1 + 34;
  const routeLine = `${N.operator.route} · ${N.operator.depart}`;
  const routeSize = fitLine(routeLine, TYPE.h1, PW, 800);
  const statSize = Math.min(fitLine("19,589", TYPE.stat, PW, 800), fitLine("7,363", TYPE.stat, PW, 800));
  const clockOn = prog(f, sweepFrom - 6, 10);

  return (
    <SceneShell>
      <Backdrop tint={[C.blue, "#3b2a5c", C.teal]} />
      <StylisedMap draw={1} glow={0.6} opacity={0.18} />
      <Chapter n="04" text="For operators" />

      <div style={{ position: "absolute", left: LX, top: LY + (1 - rise) * 700, transform: `perspective(1800px) rotateX(${(1 - rise) * 18}deg)`, transformOrigin: "50% 100%" }}>
        <Laptop scale={SCALE}>
          <World cam={cam} ax={SX} ay={SY}>
            <Shot src={capUrl("o-full-selected")} w={full.w} h={full.h} />
            <DrawBox r={row1} t={prog(f, tap + 4, 18, outCubic)} color={C.teal} pad={4} width={5} radius={10} />
            {mapOpacity > 0 ? (
              <div style={{ position: "absolute", left: mapCard.x, top: mapCard.y, width: mapCard.w, height: mapCard.h, opacity: mapOpacity, borderRadius: 18, overflow: "hidden", background: C.white }}>
                <Shot src={capUrl(mk(lo))} w={mapCard.w} h={mapCard.h} />
                {frac > 0.001 && hi !== lo ? <Shot src={capUrl(mk(hi))} w={mapCard.w} h={mapCard.h} opacity={frac} /> : null}
              </div>
            ) : null}
            <SoftCursor pts={[[tap - 26, 560, 330], [tap, cx(row1) - 220, cy(row1)]]} hideAfter={10} />
            <TapRipple x={cx(row1) - 220} y={cy(row1)} at={tap} color={C.teal} />
          </World>
        </Laptop>
        {/* the time slider's clock, floating on the glass */}
        <div style={{ position: "absolute", left: 40, bottom: 70, padding: "14px 26px", borderRadius: RADIUS.lg, background: "rgba(6,10,20,0.82)", border: "1px solid rgba(255,255,255,0.14)", boxShadow: SHADOW.card, opacity: clockOn, display: "flex", alignItems: "center", gap: 22 }}>
          <div style={{ fontSize: TYPE.h2, fontWeight: 800, color: C.text, fontVariantNumeric: "tabular-nums" }}>{clock(minutes)}</div>
          <div style={{ width: 380 }}>
            <FitText text="Weekday · corridor map" size={TYPE.label} width={380} weight={600} color={C.textDim} />
            <div style={{ position: "relative", height: 8, marginTop: 10, borderRadius: 4, background: "rgba(255,255,255,0.15)" }}>
              <div style={{ position: "absolute", left: 0, top: 0, height: 8, width: `${t * 100}%`, borderRadius: 4, background: C.amberGlow }} />
              <div style={{ position: "absolute", left: `calc(${t * 100}% - 9px)`, top: -5, width: 18, height: 18, borderRadius: 9, background: C.text }} />
            </div>
          </div>
        </div>
      </div>

      <Panel from={b0 - 4} to={b2 - 6} top={190}>
        <FitText text="A second screen, for bus operators" size={TYPE.h2} width={PW} maxLines={3} weight={800} color={C.text} />
      </Panel>
      <Panel from={b1 - 2} to={b2 - 6} top={450}>
        <FitText text="Where would one extra trip help most?" size={TYPE.body} width={PW} maxLines={3} weight={600} color={C.textDim} />
      </Panel>
      <Panel from={b2 - 2} top={170}>
        <FitText text="Weekday · best extra trip" size={TYPE.label} width={PW} weight={600} color={C.textDim} />
        <div style={{ fontSize: routeSize, fontWeight: 800, color: C.text, whiteSpace: "nowrap", marginTop: 6, letterSpacing: -1 }}>{routeLine}</div>
      </Panel>
      <Panel from={b3 - 4} top={330}>
        <Counter value={N.operator.crowded_rider_min_removed} at={b3} dur={50} size={statSize} color={C.tealGlow} />
        <FitText text="crowded rider-minutes removed" size={TYPE.body} width={PW} maxLines={2} weight={600} color={C.text} style={{ marginTop: 10 }} />
      </Panel>
      <Panel from={b4 - 4} top={580}>
        <Counter value={N.operator.riders_moved_down} at={b4} dur={50} size={statSize} color={C.tealGlow} />
        <FitText text="riders moved down a level" size={TYPE.body} width={PW} maxLines={2} weight={600} color={C.text} style={{ marginTop: 10 }} />
      </Panel>
      <Panel from={b5 - 2} top={820}>
        <FitText text="Model estimates, not counts" size={TYPE.label} width={PW} weight={600} color={C.amberGlow} />
      </Panel>

      <Captions />
      <Sfx name="whoosh" at={b0 - 10} volume={0.25} len={40} />
      <Sfx name="tap" at={tap} volume={0.45} />
      <Sfx name="pop" at={b2} volume={0.35} />
      <Sfx name="tap" at={b3} volume={0.3} />
      <Sfx name="tap" at={b4} volume={0.3} />
      <Sfx name="map-swoosh" at={sweepFrom} volume={0.3} />
    </SceneShell>
  );
};
