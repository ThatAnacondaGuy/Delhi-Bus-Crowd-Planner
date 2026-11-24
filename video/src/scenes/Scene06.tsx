import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import N from "../numbers.json";
import { C, clamp01, fmt, inOutCubic, lerp, outCubic, prog } from "../theme";
import { Cam, Caption, DrawBox, FadeIn, Laptop, Scene, Sfx, Shot, TapRing, World, Cursor, useClock } from "../components/ui";
import { R, capMeta, capUrl, cx, cy } from "../captures";
import { SCENE_CAPTIONS, sceneSpans } from "../captions";
import { LEAD_FRAMES } from "../timing";
import { useAssets } from "../assets";

const SCALE = 0.84;
const LAPTOP_X = 44;
const LAPTOP_Y = 52;
const SX = 720; // screen anchor inside the laptop
const SY = 450;

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

const MAP_FIRST = 18;
const MAP_LAST = 38;
const clock = (minutes: number) => {
  const m = Math.round(minutes);
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
};

const Big: React.FC<{ value: number; label: string; at: number; u: number; color: string }> = ({ value, label, at, u, color }) => {
  const shown = Math.round(value * prog(u, at, 45, outCubic));
  return (
    <div style={{ opacity: prog(u, at - 6, 12, outCubic), transform: `translateY(${(1 - prog(u, at - 6, 12, outCubic)) * 20}px)` }}>
      <div style={{ fontSize: 124, fontWeight: 700, color, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>{fmt(shown)}</div>
      <div style={{ fontSize: 40, fontWeight: 700, color: C.ink, marginTop: 6, lineHeight: 1.15 }}>{label}</div>
    </div>
  );
};

export const Scene06: React.FC = () => {
  const u = useClock(660);
  const f = useCurrentFrame();
  const { durationInFrames: D } = useVideoConfig();
  const { vo } = useAssets();
  const full = capMeta("o-full-selected");
  const rects = full.rects as Record<string, R>;
  const mapCard = capMeta("o-full").rects.map as R;
  const row1 = rects.row1;
  const strip = rects.strip;
  const legend = rects.legend;

  const top: Cam = { wx: SX, wy: SY, z: 1 };
  const tableCam: Cam = { wx: 14 + SX / 1.45 + 30, wy: cy(row1) + (SY - 330) / 1.45, z: 1.45 };
  const mapCam: Cam = { wx: cx(mapCard) - 60, wy: cy(mapCard), z: 1.26 };
  const stripCam: Cam = { wx: 36 + 1368 / 2 - 140, wy: strip.y + strip.h * 0.46, z: 1.02 };
  const cam = camAt(u, [[0, top], [34, top], [100, tableCam], [296, tableCam], [350, mapCam], [540, mapCam], [596, stripCam], [660, stripCam]]);

  // slider sweep 09:00 -> 19:00 over frames 262..510
  const t = prog(u, 362, 170, inOutCubic);
  const v = lerp(MAP_FIRST, MAP_LAST, t);
  const lo = Math.floor(v);
  const hi = Math.min(MAP_LAST, lo + 1);
  const frac = v - lo;
  const mk = (n: number) => `o-map-${String(n).padStart(2, "0")}`;
  const mapOn = u >= 346 && u < 604;
  const mapOpacity = prog(u, 346, 10) * (1 - prog(u, 590, 12));
  const minutes = 540 + 600 * t;

  const slideIn = prog(f, 0, 24, outCubic);
  const rise = (1 - slideIn) * 900;
  const numbersOn = prog(u, 140, 14) * (1 - prog(u, 300, 12));
  const clockOn = prog(u, 350, 12) * (1 - prog(u, 548, 12));
  const stripOn = prog(u, 604, 14);

  const spans = sceneSpans(6, SCENE_CAPTIONS[5], vo[5] != null ? Math.round(vo[5]! * 30) : null, 660, D, LEAD_FRAMES);
  const row = { ...row1 };
  return (
    <Scene fadeIn={0} fadeOut={10}>
      <div style={{ position: "absolute", left: LAPTOP_X, top: LAPTOP_Y + rise }}>
        <Laptop scale={SCALE}>
          <World cam={cam} ax={SX} ay={SY}>
            <Shot src={capUrl("o-full-selected")} w={full.w} h={full.h} />
            <DrawBox r={row} t={prog(u, 108, 18, outCubic)} color={C.teal} pad={4} width={5} radius={10} />
            {mapOn ? (
              <div style={{ position: "absolute", left: mapCard.x, top: mapCard.y, width: mapCard.w, height: mapCard.h, opacity: mapOpacity, borderRadius: 18, overflow: "hidden", background: C.white }}>
                <Shot src={capUrl(mk(lo))} w={mapCard.w} h={mapCard.h} />
                {frac > 0.001 && hi !== lo ? <Shot src={capUrl(mk(hi))} w={mapCard.w} h={mapCard.h} opacity={frac} /> : null}
              </div>
            ) : null}
            <DrawBox r={legend} t={prog(u, 618, 22, outCubic)} color={C.grey} pad={6} width={4} radius={10} />
            <Cursor pts={[[50, 560, 330], [96, cx(row1) - 220, cy(row1)]]} />
            <TapRing x={cx(row1) - 220} y={cy(row1)} at={98} />
          </World>
        </Laptop>
      </div>

      {/* numbers beside the row */}
      <div style={{ position: "absolute", left: 1350, top: 96, width: 540, opacity: numbersOn, display: "flex", flexDirection: "column", gap: 34 }}>
        <div style={{ fontSize: 58, fontWeight: 700, color: C.blue, lineHeight: 1, whiteSpace: "nowrap" }}>
          {N.operator.route} · {N.operator.depart}
        </div>
        <Big value={N.operator.crowded_rider_min_removed} label="crowded rider-minutes removed" at={152} u={u} color={C.teal} />
        <Big value={N.operator.riders_moved_down} label="riders moved down a level" at={176} u={u} color={C.teal} />
        <div style={{ fontSize: 34, color: C.grey, lineHeight: 1.25 }}>model estimates, scaled from app tickets</div>
      </div>

      {/* the clock while the slider moves */}
      <div style={{ position: "absolute", left: 1350, top: 200, width: 540, opacity: clockOn }}>
        <div style={{ fontSize: 150, fontWeight: 700, color: C.blue, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>{clock(minutes)}</div>
        <div style={{ fontSize: 40, color: C.grey, marginTop: 14, lineHeight: 1.2 }}>Corridor map, weekday: the time slider from 09:00 to 19:00</div>
      </div>

      <div style={{ position: "absolute", left: 1350, top: 120, width: 540, opacity: stripOn }}>
        <div style={{ fontSize: 56, fontWeight: 700, color: C.ink, lineHeight: 1.1 }}>Route heat strip</div>
        <div style={{ fontSize: 40, color: C.grey, marginTop: 14, lineHeight: 1.2 }}>Every stretch of one route across the day. Grey cells are No data.</div>
      </div>

      <Caption spans={spans} bottom={30} />
      <FadeIn at={0} dur={1}><span /></FadeIn>
      <Sfx name="tap" at={98} />
      <Sfx name="tap" at={152} volume={0.25} />
      <Sfx name="map-swoosh" at={350} volume={0.35} />
    </Scene>
  );
};
