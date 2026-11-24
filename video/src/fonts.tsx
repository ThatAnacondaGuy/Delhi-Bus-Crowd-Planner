// Fonts are loaded explicitly and the film does not draw (or measure) a single word before they are ready.
// Inter for English, Noto Sans Devanagari for Hindi, both pinned files served by @remotion/google-fonts. Rendering is held
// with delayRender until both loaders resolve AND document.fonts.ready, so every fitText/measureText call measures the
// same font the frame is painted with.
import React, { useEffect, useState } from "react";
import { continueRender, delayRender } from "remotion";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadDeva } from "@remotion/google-fonts/NotoSansDevanagari";

const inter = loadInter("normal", { weights: ["400", "500", "600", "700", "800"], subsets: ["latin", "latin-ext"] });
const deva = loadDeva("normal", { weights: ["400", "600", "700"], subsets: ["devanagari", "latin"] });

export const FONT_EN = inter.fontFamily;
export const FONT_HI = deva.fontFamily;
/** The family stack every element uses: Inter first, Devanagari glyphs from Noto Sans Devanagari. */
export const FONT = `"${FONT_EN}", "${FONT_HI}", sans-serif`;

let ready = false;
const loaded: Promise<void> = Promise.all([inter.waitUntilDone(), deva.waitUntilDone()])
  .then(() => (typeof document !== "undefined" ? document.fonts.ready : undefined))
  .then(() => {
    ready = true;
  });

/** Renders its children only once the fonts are in; holds the frame until then. */
export const FontGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [ok, setOk] = useState(ready);
  const [handle] = useState(() => (ready ? null : delayRender("fonts: Inter + Noto Sans Devanagari", { timeoutInMilliseconds: 60000 })));
  useEffect(() => {
    if (ok) return;
    loaded.then(() => {
      setOk(true);
      if (handle != null) continueRender(handle);
    });
  }, [ok, handle]);
  return ok ? <>{children}</> : null;
};
