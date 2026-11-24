import React from "react";
import QRCode from "qrcode";

/** QR code drawn as SVG at build time (error correction H, quiet zone kept). */
export const Qr: React.FC<{ text: string; size: number; fg?: string; bg?: string }> = ({ text, size, fg = "#1d2327", bg = "#ffffff" }) => {
  const q = QRCode.create(text, { errorCorrectionLevel: "H" });
  const n = q.modules.size;
  const quiet = 4;
  const total = n + 2 * quiet;
  const cells: React.ReactNode[] = [];
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      if (q.modules.data[r * n + c]) cells.push(<rect key={`${r}-${c}`} x={c + quiet} y={r + quiet} width={1.02} height={1.02} />);
    }
  }
  return (
    <svg width={size} height={size} viewBox={`0 0 ${total} ${total}`} shapeRendering="crispEdges" style={{ background: bg, borderRadius: 12 }}>
      <g fill={fg}>{cells}</g>
    </svg>
  );
};
