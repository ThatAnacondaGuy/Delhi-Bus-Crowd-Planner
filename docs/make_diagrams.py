"""Write the two animated diagrams used by the README, the technical note and the proposal.

    python docs/make_diagrams.py            # writes docs/assets/architecture*.svg and how-it-works*.svg

Pure Python, no dependencies. Each diagram comes in a light and a dark variant (README uses <picture> to pick one).
The animation is CSS only (no scripts), so it also runs when GitHub shows the file through <img>. Everything moves
inside `@media (prefers-reduced-motion: no-preference)`; with reduced motion the diagram is a still picture.
There are no data numbers in these diagrams on purpose: the numbers live in the rendered documents.
"""
from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent / "assets"
FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif'

THEMES = {
    "light": dict(bg="#fbfaf7", edge="#e3e0d6", lane="#f2f0e9", lane_edge="#e0ddd2", box="#ffffff", box_edge="#c9c5b8",
                  ink="#1d2327", muted="#566069", arrow="#8a96a1", packet="#0f766e", lit="#0f766e",
                  seats="#0f766e", standing="#b45309", crowded="#8f1d1d", nodata="#5f6670", chip="#eef4f3",
                  inputs="#5b6b7b", pipeline="#0f766e", outputs="#b45309", serve="#1f4e79", screens="#0f766e"),
    "dark": dict(bg="#0d1117", edge="#30363d", lane="#151b23", lane_edge="#2a323c", box="#1c232c", box_edge="#3d4752",
                 ink="#e6edf3", muted="#9aa7b4", arrow="#6e7b88", packet="#2dd4bf", lit="#2dd4bf",
                 seats="#2dd4bf", standing="#f59e0b", crowded="#f87171", nodata="#9aa7b4", chip="#232d38",
                 inputs="#8b9bab", pipeline="#2dd4bf", outputs="#f59e0b", serve="#7cb3ea", screens="#2dd4bf"),
}


def t(s: str) -> str:
    return escape(s)


# --------------------------------------------------------------------------- architecture


class Arch:
    STEP = 0.45  # seconds between steps of the choreography
    PAUSE = 2.6  # rest at the end of each loop

    def __init__(self, theme: str):
        self.c = THEMES[theme]
        self.theme = theme
        self.parts: list[str] = []
        self.clock = 0  # step counter
        self.max_clock = 0

    def at(self, k: int | None = None) -> float:
        if k is not None:
            self.clock = k
        self.max_clock = max(self.max_clock, self.clock)
        return round(self.clock * self.STEP, 2)

    def lane(self, y, h, name, colour):
        c = self.c
        self.parts.append(f'<rect x="10" y="{y}" width="940" height="{h}" rx="12" fill="{c["lane"]}" stroke="{c["lane_edge"]}"/>')
        self.parts.append(f'<rect x="10" y="{y + 12}" width="4" height="{h - 24}" rx="2" fill="{colour}"/>')
        self.parts.append(f'<text x="28" y="{y + h / 2 + 4}" class="lane" fill="{c["muted"]}">{t(name)}</text>')

    def box(self, x, y, w, h, title, sub=(), colour=None, delay=None, title_size=13.5):
        c = self.c
        colour = colour or c["pipeline"]
        d = self.at() if delay is None else delay
        g = [f'<g><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{c["box"]}" stroke="{c["box_edge"]}"/>',
             f'<rect x="{x}" y="{y + 8}" width="3.5" height="{h - 16}" rx="1.75" fill="{colour}"/>',
             f'<text x="{x + 14}" y="{y + 22}" class="bt" font-size="{title_size}" fill="{c["ink"]}">{t(title)}</text>']
        for i, line in enumerate(sub):
            g.append(f'<text x="{x + 14}" y="{y + 39 + 14 * i}" class="st" fill="{c["muted"]}">{t(line)}</text>')
        g.append(f'<rect class="lit" x="{x - 1}" y="{y - 1}" width="{w + 2}" height="{h + 2}" rx="9" fill="none" '
                 f'stroke="{c["lit"]}" stroke-width="2.2" style="animation-delay:{d}s"/></g>')
        self.parts.append("".join(g))

    def chip(self, x, y, w, text, delay):
        c = self.c
        self.parts.append(
            f'<g><rect x="{x}" y="{y}" width="{w}" height="28" rx="14" fill="{c["chip"]}" stroke="{c["box_edge"]}"/>'
            f'<text x="{x + w / 2}" y="{y + 18}" text-anchor="middle" class="cp" fill="{c["ink"]}">{t(text)}</text>'
            f'<rect class="lit" x="{x - 1}" y="{y - 1}" width="{w + 2}" height="30" rx="15" fill="none" stroke="{c["lit"]}" '
            f'stroke-width="2" style="animation-delay:{delay}s"/></g>')

    def arrow(self, d, delay=None):
        c = self.c
        dl = self.at() if delay is None else delay
        self.parts.append(
            f'<path d="{d}" class="arr" fill="none" stroke="{c["arrow"]}" stroke-width="1.6" marker-end="url(#ah)"/>'
            f'<path d="{d}" class="march" fill="none" stroke="{c["arrow"]}" stroke-width="1.6" opacity="0"/>'
            f'<path d="{d}" class="dot" pathLength="100" fill="none" stroke="{c["packet"]}" stroke-width="7" '
            f'stroke-linecap="round" style="animation-delay:{dl}s"/>')

    def build(self) -> str:
        c = self.c
        W, H = 960, 724
        P = self.parts
        # lanes
        self.lane(14, 108, "INPUTS", c["inputs"])
        self.lane(134, 288, "PIPELINE", c["pipeline"])
        self.lane(434, 88, "OUTPUTS", c["outputs"])
        self.lane(534, 72, "SERVE", c["serve"])
        self.lane(618, 94, "SCREENS", c["screens"])

        xs3 = [130, 410, 690]
        # k = choreography step
        self.at(0)
        self.box(130, 34, 250, 68, "ONDC app tickets", ["where each rider boarded and got off,", "the bus type, the time"], c["inputs"])
        self.box(410, 34, 250, 68, "GTFS timetable", ["routes, stops, scheduled trips,", "the shape of every route"], c["inputs"], delay=self.at())
        self.box(690, 34, 250, 68, "GPS feed", ["where buses really were,", "so we know which trips ran"], c["inputs"], delay=self.at())

        a_y, a_h = 154, 52
        axs = [130, 340, 550, 760]
        stages = [("1  Clean", ["drop bad rows, outage windows"]),
                  ("2  Resolve stops", ["match ticket stops to GTFS"]),
                  ("3  Network clock & assets", ["run times, places, bus mix"]),
                  ("4  GPS trips that ran", ["share of timetable trips run"])]
        self.at(1)
        self.arrow("M220 102 V152")
        self.arrow("M470 102 V152", delay=self.at())
        self.arrow("M600 102 V152", delay=self.at())
        self.arrow("M850 102 V152", delay=self.at())
        for i, (title, sub) in enumerate(stages):
            self.at(2 + 2 * i)
            self.box(axs[i], a_y, 180, a_h, title, sub, c["pipeline"], title_size=13)
            if i < 3:
                self.at(3 + 2 * i)
                self.arrow(f"M{axs[i] + 180} {a_y + 26} H{axs[i + 1] - 2}")
        self.at(9)
        self.arrow("M850 206 V230")

        # loads
        self.at(10)
        self.box(130, 232, 810, 82, "5  Loads: how many people are on each stretch", [], c["pipeline"])
        chips = ["riders on stretches", "alighting correction", "bus supply", "scale-up", "levels", "evidence"]
        cw, gap = 120, 12.4
        for i, name in enumerate(chips):
            self.chip(round(146 + i * (cw + gap), 1), 268, cw, name, round((11 + i) * self.STEP, 2))
        self.max_clock = max(self.max_clock, 16)

        self.at(17)
        self.arrow("M255 314 V338")
        row_c = [(130, "6  Operator ranking", ["which extra trips relieve most"]),
                 (410, "7  Validate", ["gates, checks, honest misses"]),
                 (690, "8  Render", ["documents filled from the numbers"])]
        for i, (x, title, sub) in enumerate(row_c):
            self.at(18 + 2 * i)
            self.box(x, 340, 250, 52, title, sub, c["pipeline"])
            if i < 2:
                self.at(19 + 2 * i)
                self.arrow(f"M{x + 250} 366 H{row_c[i + 1][0] - 2}")

        # outputs
        self.at(23)
        self.arrow("M255 392 V456")
        self.arrow("M535 392 V456", delay=self.at())
        self.arrow("M815 392 V456", delay=self.at())
        self.at(24)
        self.box(130, 458, 250, 54, "Crowding & planner tables", ["level, people range, evidence"], c["outputs"])
        self.box(410, 458, 250, 54, "Validation report", ["gates, expectations, repeatability"], c["outputs"], delay=self.at())
        self.box(690, 458, 250, 54, "Documents", ["README, technical note, proposal"], c["outputs"], delay=self.at())

        # serve
        self.at(25)
        self.arrow("M255 512 V550")
        self.at(26)
        self.box(130, 548, 810, 50, "Planner + API (FastAPI)", [], c["serve"])
        P.append(f'<text x="{130 + 14}" y="{548 + 40}" class="st" fill="{c["muted"]}">finds the journeys, adds each stretch\'s crowding level, offers three options: fastest, less crowded, leave later</text>')
        # screens
        self.at(27)
        self.arrow("M255 598 V640")
        self.arrow("M535 598 V640", delay=self.at())
        self.arrow("M815 598 V640", delay=self.at())
        self.at(28)
        self.box(130, 642, 250, 58, "Commuter screen", ["phone first, English and Hindi"], c["screens"])
        self.box(410, 642, 250, 58, "Operator view", ["extra-trip ranking, corridor map"], c["screens"], delay=self.at())
        self.box(690, 642, 250, 58, "Live demo", ["static Space: precomputed answers"], c["screens"], delay=self.at())

        cycle = round((self.max_clock + 3) * self.STEP + self.PAUSE, 1)
        css = self.css(cycle)
        defs = (f'<defs><marker id="ah" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
                f'<path d="M1 1 L9 5 L1 9 z" fill="{c["arrow"]}"/></marker></defs>')
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
                f'aria-labelledby="t d"><title id="t">System architecture</title>'
                f'<desc id="d">Tickets, timetable and GPS feed go through an eight-stage pipeline into crowding tables, a validation '
                f'report and documents; a planner and API serve the commuter screen, the operator view and the live demo.</desc>')
        return head + f"<style>{css}</style>" + defs + f'<rect width="{W}" height="{H}" rx="14" fill="{c["bg"]}" stroke="{c["edge"]}"/>' + "".join(P) + "</svg>\n"

    def css(self, cycle: float) -> str:
        return f"""
text{{font-family:{FONT}}}
.lane{{font-size:11px;font-weight:700;letter-spacing:.14em}}
.bt{{font-weight:700}}
.st{{font-size:11.5px}}
.cp{{font-size:11px}}
.lit,.dot{{opacity:0}}
@media (prefers-reduced-motion: no-preference){{
.march{{opacity:.55;stroke-dasharray:3 7;animation:march 1.1s linear infinite}}
.lit{{animation:lit {cycle}s ease-in-out infinite}}
.dot{{stroke-dasharray:.01 300;animation:dot {cycle}s linear infinite}}
}}
@keyframes march{{to{{stroke-dashoffset:-10}}}}
@keyframes lit{{0%{{opacity:0}}2.5%{{opacity:1}}9%{{opacity:.85}}17%{{opacity:0}}100%{{opacity:0}}}}
@keyframes dot{{0%{{opacity:1;stroke-dashoffset:300}}4.2%{{opacity:1;stroke-dashoffset:200}}4.3%{{opacity:0;stroke-dashoffset:200}}100%{{opacity:0;stroke-dashoffset:200}}}}
"""


# --------------------------------------------------------------------------- how it works


def wrap(text: str, n: int) -> list[str]:
    out, cur = [], ""
    for w in text.split():
        if len(cur) + len(w) + 1 > n and cur:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        out.append(cur)
    return out


class Story:
    SLOT = 2.8
    PAUSE = 3.0
    N = 5

    def __init__(self, theme: str):
        self.c = THEMES[theme]
        self.keyframes: dict[float, str] = {}
        self.cycle = self.N * self.SLOT + self.PAUSE

    def rv(self, start: float, kind: str = "rise") -> str:
        """Class name of a build-up animation that starts `start` seconds into the loop and holds to the end."""
        key = (round(start, 2), kind)
        name = f"r{len(self.keyframes)}"
        for k, (n, _) in list(self.keyframes.items()):
            if k == key:
                return n
        p0 = key[0] / self.cycle * 100
        p1 = (key[0] + 0.5) / self.cycle * 100
        end = f"{self.cycle - 0.9:.2f}"
        e0 = (self.cycle - 0.9) / self.cycle * 100
        e1 = (self.cycle - 0.3) / self.cycle * 100
        frm = {"rise": "transform:translateY(8px)", "grow": "transform:scaleY(0)", "pop": "transform:scale(.4)",
               "fade": "transform:none", "slide": "transform:translateX(-14px)"}[kind]
        to = "transform:none"
        css = (f"@keyframes {name}{{0%,{p0:.2f}%{{opacity:0;{frm}}}{p1:.2f}%{{opacity:1;{to}}}"
               f"{e0:.2f}%{{opacity:1;{to}}}{e1:.2f}%,100%{{opacity:0;{to}}}}}")
        self.keyframes[key] = (name, css)
        return name

    def anim(self, start: float, kind: str = "rise") -> str:
        n = self.rv(start, kind)
        return f'class="a {n}"'

    def build(self) -> str:
        c = self.c
        W, H = 960, 440
        P: list[str] = []
        pw, gap, py, ph = 174, 12, 78, 340
        px = [21 + i * (pw + gap) for i in range(self.N)]
        titles = ["A ticket", "Spread out", "Scaled up", "Compared", "A level"]
        caps = ["Someone boards at Stop A and gets off at Stop D, on a bus of a known type.",
                "Its ride is spread over each stretch it covers, at the time the bus was there.",
                "App tickets are a sample. We scale up to everyone on board, never above what a bus can hold.",
                "People on board are compared with the bus's seats and its rated total.",
                "Seats, standing or crowded: a word, dots and colour. If we know too little, we say so."]
        P.append(f'<text x="21" y="34" class="h1" fill="{c["ink"]}">How one ticket becomes a crowding level</text>')
        P.append(f'<text x="21" y="56" class="st" fill="{c["muted"]}">Illustrative example with a made-up ticket. The real pipeline does this for every ticket, stretch and hour.</text>')
        for i in range(self.N):
            x, s = px[i], i * self.SLOT
            P.append(f'<rect x="{x}" y="{py}" width="{pw}" height="{ph}" rx="12" fill="{c["lane"]}" stroke="{c["lane_edge"]}"/>')
            P.append(f'<rect class="lit" x="{x - 1}" y="{py - 1}" width="{pw + 2}" height="{ph + 2}" rx="13" fill="none" stroke="{c["lit"]}" stroke-width="2.4" style="animation-delay:{s}s"/>')
            P.append(f'<circle cx="{x + 24}" cy="{py + 28}" r="12" fill="{c["pipeline"]}"/><text x="{x + 24}" y="{py + 33}" text-anchor="middle" class="num" fill="#ffffff">{i + 1}</text>')
            P.append(f'<text x="{x + 44}" y="{py + 33}" class="bt" fill="{c["ink"]}">{t(titles[i])}</text>')
            for j, line in enumerate(wrap(caps[i], 25)):
                P.append(f'<text x="{x + 14}" y="{py + 262 + 16 * j}" class="cap" fill="{c["muted"]}">{t(line)}</text>')
            if i < self.N - 1:
                cx = x + pw + gap / 2
                P.append(f'<path d="M{cx - 3} {py + 28 - 5} l5 5 l-5 5" fill="none" stroke="{c["arrow"]}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')

        # ---- panel 1: ticket
        x, s = px[0], 0 * self.SLOT
        tx, ty = x + 22, py + 64
        P.append(f'<g {self.anim(s + .2, "rise")}><rect x="{tx}" y="{ty}" width="130" height="150" rx="10" fill="{c["box"]}" stroke="{c["box_edge"]}" stroke-width="1.5"/>'
                 f'<text x="{tx + 14}" y="{ty + 24}" class="tk" fill="{c["muted"]}">BOARDS</text><text x="{tx + 14}" y="{ty + 44}" class="bt" fill="{c["ink"]}">Stop A</text>'
                 f'<line x1="{tx + 12}" y1="{ty + 62}" x2="{tx + 118}" y2="{ty + 62}" stroke="{c["box_edge"]}" stroke-dasharray="4 4"/>'
                 f'<text x="{tx + 14}" y="{ty + 84}" class="tk" fill="{c["muted"]}">GETS OFF</text><text x="{tx + 14}" y="{ty + 104}" class="bt" fill="{c["ink"]}">Stop D</text>'
                 f'<text x="{tx + 14}" y="{ty + 132}" class="tk" fill="{c["muted"]}">12 m bus, morning</text>'
                 f'<circle cx="{tx}" cy="{ty + 62}" r="6" fill="{c["lane"]}"/><circle cx="{tx + 130}" cy="{ty + 62}" r="6" fill="{c["lane"]}"/></g>')

        # ---- panel 2: stretches
        x, s = px[1], 1 * self.SLOT
        lx0, lx1, ly = x + 24, x + 150, py + 190
        P.append(f'<line x1="{lx0}" y1="{ly}" x2="{lx1}" y2="{ly}" stroke="{c["arrow"]}" stroke-width="3" stroke-linecap="round"/>')
        stops = [lx0 + i * (lx1 - lx0) / 3 for i in range(4)]
        for i, sx in enumerate(stops):
            P.append(f'<circle cx="{sx:.1f}" cy="{ly}" r="5" fill="{c["box"]}" stroke="{c["ink"]}" stroke-width="2"/><text x="{sx:.1f}" y="{ly + 22}" text-anchor="middle" class="tk" fill="{c["ink"]}">{"ABCD"[i]}</text>')
        heights = [34, 52, 40]
        for i in range(3):
            bx = stops[i] + 5
            bw = (lx1 - lx0) / 3 - 10
            P.append(f'<g {self.anim(s + .3 + .35 * i, "grow")} style="transform-box:fill-box;transform-origin:50% 100%"><rect x="{bx:.1f}" y="{ly - 14 - heights[i]}" width="{bw:.1f}" height="{heights[i]}" rx="4" fill="{c["pipeline"]}" opacity=".85"/></g>')
        P.append(f'<g {self.anim(s + .3, "fade")}><text x="{x + 14}" y="{py + 76}" class="tk" fill="{c["muted"]}">share of the rider in</text><text x="{x + 14}" y="{py + 90}" class="tk" fill="{c["muted"]}">each stretch</text></g>')

        # ---- panel 3: scale up
        x, s = px[2], 2 * self.SLOT
        P.append(f'<circle cx="{x + 30}" cy="{py + 150}" r="9" fill="{c["pipeline"]}"/><text x="{x + 30}" y="{py + 178}" text-anchor="middle" class="tk" fill="{c["muted"]}">1 ticket</text>')
        P.append(f'<path d="M{x + 50} {py + 150} h20" stroke="{c["arrow"]}" stroke-width="2" stroke-linecap="round"/><path d="M{x + 65} {py + 144} l6 6 l-6 6" fill="none" stroke="{c["arrow"]}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')
        k = 0
        for row in range(5):
            for col in range(4):
                dx, dy = x + 84 + col * 20, py + 90 + row * 20
                P.append(f'<circle {self.anim(s + .4 + .05 * k, "pop")} style="transform-box:fill-box;transform-origin:center" cx="{dx}" cy="{dy}" r="6.5" fill="{c["pipeline"]}" opacity=".9"/>')
                k += 1
        P.append(f'<g {self.anim(s + 1.8, "fade")}><text x="{x + 114}" y="{py + 208}" text-anchor="middle" class="tk" fill="{c["muted"]}">everyone on board</text></g>')

        # ---- panel 4: compare
        x, s = px[3], 3 * self.SLOT
        bx0, base = x + 40, py + 214
        seat_y, tot_y, top_y = base - 70, base - 118, base - 96
        P.append(f'<line x1="{x + 16}" y1="{base}" x2="{x + 158}" y2="{base}" stroke="{c["arrow"]}" stroke-width="2"/>')
        P.append(f'<g {self.anim(s + .2, "grow")} style="transform-box:fill-box;transform-origin:50% 100%"><rect x="{bx0}" y="{top_y}" width="62" height="{base - top_y}" rx="5" fill="{c["standing"]}"/></g>')
        P.append(f'<g {self.anim(s + 1.0, "fade")}><text x="{bx0 + 31}" y="{top_y + 20}" text-anchor="middle" class="tk" fill="#ffffff">on board</text></g>')
        for yy, lab in ((seat_y, "seats"), (tot_y, "rated total")):
            P.append(f'<g {self.anim(s + .6, "slide")}><line x1="{x + 16}" y1="{yy}" x2="{x + 158}" y2="{yy}" stroke="{c["ink"]}" stroke-width="1.5" stroke-dasharray="5 4"/><text x="{x + 108}" y="{yy - 5}" class="tk" fill="{c["ink"]}">{lab}</text></g>')

        # ---- panel 5: levels
        x, s = px[4], 4 * self.SLOT
        levels = [("Usually seats", "●○○", c["seats"], False), ("Usually standing", "●●○", c["standing"], True),
                  ("Usually crowded", "●●●", c["crowded"], False), ("No data", "○○○", c["nodata"], False)]
        for i, (lab, dots, col, chosen) in enumerate(levels):
            cy = py + 66 + i * 46
            dash = ' stroke-dasharray="4 3"' if lab == "No data" else ""
            cls = self.anim(s + .3 + .15 * i, "fade")
            P.append(f'<g {cls}><g class="{"pick" if chosen else "dim"}"><rect x="{x + 10}" y="{cy}" width="154" height="38" rx="19" fill="none" stroke="{col}" stroke-width="2.2"{dash}/>'
                     f'<text x="{x + 20}" y="{cy + 24}" class="ch" fill="{c["ink"]}">{t(lab)}</text><text x="{x + 154}" y="{cy + 24}" text-anchor="end" class="ch" fill="{col}">{dots}</text></g></g>')
        # highlight ring appears last
        cy = py + 66 + 46
        P.append(f'<rect {self.anim(s + 1.4, "fade")} x="{x + 6}" y="{cy - 4}" width="162" height="46" rx="23" fill="none" stroke="{c["standing"]}" stroke-width="3"/>')

        kf = "".join(css for _, css in self.keyframes.values())
        css = f"""
text{{font-family:{FONT}}}
.h1{{font-size:20px;font-weight:700}}
.st{{font-size:12px}}
.bt{{font-size:14px;font-weight:700}}
.num{{font-size:13px;font-weight:700}}
.cap{{font-size:12px}}
.tk{{font-size:11px;font-weight:600}}
.ch{{font-size:11px;font-weight:600}}
.lit{{opacity:0}}
@media (prefers-reduced-motion: no-preference){{
.lit{{animation:lit {self.cycle}s ease-in-out infinite}}
.a{{animation-duration:{self.cycle}s;animation-iteration-count:infinite;animation-timing-function:cubic-bezier(.2,.7,.2,1)}}
}}
@keyframes lit{{0%{{opacity:0}}3%{{opacity:1}}{round(100 * self.SLOT / self.cycle - 1, 1)}%{{opacity:.9}}{round(100 * self.SLOT / self.cycle + 3, 1)}%{{opacity:0}}100%{{opacity:0}}}}
{kf}
"""
        # each .a element uses its own keyframes: bind names
        binds = "".join(f".{n}{{animation-name:{n}}}" for n, _ in self.keyframes.values())
        css = css.replace("@keyframes lit", f"@media (prefers-reduced-motion: no-preference){{{binds}}}\n@keyframes lit", 1)
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t d">'
                f'<title id="t">How one ticket becomes a crowding level</title>'
                f'<desc id="d">Five steps: a ticket from Stop A to Stop D; its ride spread over the stretches it covers; scaled up to everyone on board; compared with the bus seats and rated total; shown as a level such as usually standing.</desc>')
        return head + f"<style>{css}</style>" + f'<rect width="{W}" height="{H}" rx="14" fill="{c["bg"]}" stroke="{c["edge"]}"/>' + "".join(P) + "</svg>\n"


def write_all(out: Path = OUT) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for theme, suffix in (("light", ""), ("dark", "-dark")):
        for name, cls in (("architecture", Arch), ("how-it-works", Story)):
            p = out / f"{name}{suffix}.svg"
            p.write_text(cls(theme).build(), encoding="utf-8")
            files.append(p)
    return files


if __name__ == "__main__":
    for f in write_all(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT):
        print(f, f.stat().st_size, "bytes")
