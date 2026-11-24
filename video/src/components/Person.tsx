import React from "react";

/** A flat rider icon (head and shoulders). Size is the height in px. */
export const Person: React.FC<{ x: number; y: number; size: number; color: string; opacity?: number }> = ({ x, y, size, color, opacity = 1 }) => (
  <svg width={size * 0.62} height={size} viewBox="0 0 31 50" style={{ position: "absolute", left: x, top: y, opacity }}>
    <circle cx="15.5" cy="9" r="8" fill={color} />
    <path d="M2 49 C2 30 8 21 15.5 21 C23 21 29 30 29 49 Z" fill={color} />
  </svg>
);
