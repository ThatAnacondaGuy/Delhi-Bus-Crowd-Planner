"""Static checks on the commuter screen (no browser is installed here; the controller does the real browser run)."""
import re
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"
FILES = {n: (FRONT / n) for n in ("index.html", "app.css", "app.js")}
FORBIDDEN = re.compile(r"κ|kappa|mcraptor|pareto|sigmoid|\bscore\b", re.I)
COPY = [("Usually seats", "आमतौर पर सीट मिल जाती है"),
        ("Usually standing", "आमतौर पर खड़े होकर जाना पड़ता है"),
        ("Usually crowded", "आमतौर पर भारी भीड़"),
        ("No data", "जानकारी नहीं"),
        ("Based on many tickets", "कई टिकटों पर आधारित"),
        ("Rough guess", "अंदाज़ा (कम टिकट)"),
        ("Full buses may not stop", "भरी बस शायद न रुके")]
CREDIT = "Data: Transport Stack / IIIT Delhi; ticketing from ONDC e-ticketing."


def text(name: str) -> str:
    return FILES[name].read_text(encoding="utf-8")


def everything() -> str:
    return "\n".join(text(n) for n in FILES)


def test_files_exist():
    assert all(p.is_file() for p in FILES.values())


def test_no_tailwind_cdn_no_chartjs_leaflet_pinned():
    allt = everything()
    assert "cdn.tailwindcss.com" not in allt
    assert not re.search(r"chart\.?js", allt, re.I)
    assert "leaflet@1.9.4/dist/leaflet.js" in allt and "leaflet@1.9.4/dist/leaflet.css" in allt
    assert not re.search(r"leaflet@(?!1\.9\.4)", allt)


def test_leaflet_is_lazy():
    assert "leaflet" not in text("index.html").lower()          # only app.js loads it, on the Show map tap


def test_all_copy_strings_present():
    allt = everything()
    for en, hi in COPY:
        assert en in allt, en
        assert hi in allt, hi


def test_credit_line():
    assert CREDIT in text("index.html")


def test_no_forbidden_words():
    for n in FILES:
        assert not FORBIDDEN.search(text(n)), n


def test_no_percent_next_to_a_level():
    # the time bar uses flex weights, so neither the page nor the script contains a percent sign at all
    for n in ("index.html", "app.js"):
        assert "%" not in text(n), n
    assert not re.search(r"content:[^;}]*%", text("app.css"))


def test_levels_pair_word_dots_colour():
    js, css = text("app.js"), text("app.css")
    for dots in ("●○○", "●●○", "●●●"):
        assert dots in js
    for lv in ("seats", "standing", "crowded", "no_data"):
        assert f".lvl-{lv}" in css
    assert re.search(r"\.lvl-no_data[^{]*\{[^}]*dashed", css)


def test_api_strings_never_go_through_innerhtml():
    js = text("app.js")
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js and "document.write" not in js


def test_base_size_and_tap_targets():
    css = text("app.css")
    assert re.search(r"font-size:\s*16px", css) and "48px" in css
    assert "Noto Sans Devanagari" in css + text("index.html")
    assert 'name="viewport"' in text("index.html")


def test_presets_in_order():
    js = text("app.js")
    spots = [js.index(p) for p in ("ISBT Anand Vihar", "Ambedkar Nagar", "Mandi House")]
    assert spots == sorted(spots)
    assert js.count("Ambedkar Nagar") >= 2 and "AIIMS" in js and "Laxmi Nagar" in js


def test_hindi_labels_for_roles_and_buttons():
    js = text("app.js")
    for hi in ("सबसे तेज़", "कम भीड़", "थोड़ा बाद निकलें", "क्यों?", "नक्शा देखें", "मुझे सीट चाहिए",
               "सोम–शुक्र", "शनि–रवि", "रास्ता देखें"):
        assert hi in js, hi


def test_why_sheet_text_and_dynamic_n():
    js = text("app.js")
    assert "Women riding free and pass holders are not in this data, so buses can be fuller than shown." in js
    assert "app_riders_one_in" in js and "never more than a bus can hold" in js
    assert not re.search(r"1 in 40|1 in 44", js)             # N comes from /v1/health, never hard-coded


def test_card_renders_no_data():
    """Structural: no browser here. no_data maps to the No data copy and the grey dashed chip; a null headline
    (walk-only option) is handled; the api's no_data headline (evidence none) gets no evidence line."""
    js, css = text("app.js"), text("app.css")
    assert re.search(r"no_data\s*:\s*\{[^}]*en:\s*\"No data\"", js, re.S)
    assert "chip lvl-" in js or "lvl-${" in js or '"lvl-" +' in js
    assert re.search(r"\.lvl-no_data[^{]*\{[^}]*(grey|gray|#[0-9a-f]{3,6})[^}]*dashed|\.lvl-no_data[^{]*\{[^}]*dashed", css)
    assert re.search(r"headline\s*(===|==)\s*null|!\s*\w+\.headline|headline\s*\?", js)
    assert "walk" in js and "evidence" in js


# ---------------------------------------------------------------- operator view (Task 18)

OP_FILES = {n: (FRONT / n) for n in ("operator.html", "operator.js")}


def optext(name: str) -> str:
    return OP_FILES[name].read_text(encoding="utf-8")


def op_everything() -> str:
    return "\n".join(optext(n) for n in OP_FILES) + "\n" + text("app.css") + "\n" + (FRONT / "operator.css").read_text(encoding="utf-8")


def test_operator_files_exist():
    assert all(p.is_file() for p in OP_FILES.values())


def test_operator_standard_terms_and_title():
    html = optext("operator.html")
    for s in ("Extra trips that help most", "maximum load section", "load factor"):
        assert s in html, s
    assert "Cluster (DIMTS)" in optext("operator.js") + html


def test_operator_links_csv_and_apis():
    allt = optext("operator.html") + optext("operator.js")
    assert "/v1/operator/trips.csv" in allt
    for api in ("/v1/operator/trips", "/v1/corridors", "/v1/crowding"):
        assert api in optext("operator.js"), api


def test_operator_no_forbidden_words_no_tailwind_leaflet_pinned():
    for n in OP_FILES:
        assert not FORBIDDEN.search(optext(n)), n
    allt = op_everything()
    assert "cdn.tailwindcss.com" not in allt
    assert not re.search(r"chart\.?js", allt, re.I)
    assert "leaflet@1.9.4/dist/leaflet.js" in allt and "leaflet@1.9.4/dist/leaflet.css" in allt
    assert not re.search(r"leaflet@(?!1\.9\.4)", allt)
    assert "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" in allt     # same SRI as the commuter map
    assert "tile.openstreetmap.org" in allt and "OpenStreetMap" in allt


def test_operator_css_has_no_forbidden_words():
    css = (FRONT / "operator.css").read_text(encoding="utf-8")
    assert not FORBIDDEN.search(css)
    assert "/static/operator.css" in optext("operator.html") and "/static/app.css" in optext("operator.html")


def test_operator_credit_line_and_viewport():
    html = optext("operator.html")
    assert CREDIT in html and 'name="viewport"' in html


def test_operator_api_strings_never_go_through_innerhtml():
    js = optext("operator.js")
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js and "document.write" not in js


def test_operator_day_switch_defaults_weekday_and_slider_steps():
    html, js = optext("operator.html"), optext("operator.js")
    assert re.search(r'data-day="weekday"[^>]*aria-pressed="true"', html)
    assert re.search(r'data-day="weekend"[^>]*aria-pressed="false"', html)
    assert 'type="range"' in html                                   # the corridor time slider
    assert re.search(r"weekday\s*:\s*30", js) and re.search(r"weekend\s*:\s*60", js)   # 30-min and 60-min steps


def test_operator_legends_pair_words_with_colour():
    js, html = optext("operator.js"), optext("operator.html")
    for word in ("Seats", "Standing", "Crowded", "No data"):
        assert word in js, word
    assert "aria-label" in js                                        # heat-strip cells carry a text label
    assert "buses that ran" in (js + html).lower() and "estimate" in js.lower()


# ---------------------------------------------------------------- polish pass (Task 17b)

def test_first_screen_explains_itself():
    html, js, css = text("index.html"), text("app.js"), text("app.css")
    assert 'id="tagline"' in html and 'data-t="tagline"' in html and 'id="key"' in html
    assert "tagline:" in js and "buildKey" in js
    assert ".key" in css
    # the key reuses the same level table as the chips, so word + dots + colour cannot drift apart
    assert re.search(r"function buildKey[^}]*pick\(L\)", js, re.S) or "pick(level(" in js


def test_cards_have_route_pills_callout_and_focus_ring():
    js, css = text("app.js"), text("app.css")
    assert "route-pill" in js and ".route-pill" in css
    assert "callout" in js and ".callout" in css
    assert css.count(":focus-visible") >= 2


def test_motion_is_gentle_and_switched_off_for_reduced_motion():
    css = text("app.css")
    assert "@keyframes" in css
    m = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{(.*?)\n\}", css, re.S)
    assert m and "animation: none" in m.group(1) and "transition" in m.group(1)
    for ms in re.findall(r"animation:[^;]*?(\d+)ms", css):
        assert 150 <= int(ms) <= 400, ms


def test_map_has_stop_markers_and_a_marker_legend():
    js = text("app.js")
    for word in ("board", "change", "alight"):
        assert word in js
    assert "divIcon" in js and "maxZoom" in js and ".pin" in text("app.css")


def test_hindi_for_why_lead_flag_words_and_demo_banner():
    js = text("app.js")
    assert "FLAG_WORDS_HI" in js and "WOMEN_SENTENCE_HI" in js
    for hi in ("ऐप टिकटों पर आधारित", "भरी बस", "महिला"):
        assert hi in js
    data = (FRONT / "data.js").read_text(encoding="utf-8")
    assert "लाइव डेमो" in data and "lang" in data
    assert "banner(" in js and re.search(r"banner\(.*state\.lang", js)


def test_operator_tiles_slider_ticks_wrapped_notes_and_sticky_header():
    html, js, css = optext("operator.html"), optext("operator.js"), (FRONT / "operator.css").read_text(encoding="utf-8")
    assert 'id="tiles"' in html and "renderTiles" in js
    assert "reduce" in js                                  # the tiles are sums over the rows already loaded
    assert re.search(r"\.op-table thead th\s*\{[^}]*position:\s*sticky", css)
    assert re.search(r"\.op-flags\s*\{[^}]*min-width:\s*(?:1[5-9]|2\d)\dpx", css) and "white-space: normal" in css
    assert 'id="ticks"' in html and "renderTicks" in js
    assert "prefers-reduced-motion" in css or "transition" not in css


# ---------------------------------------------------------------- the compact demo banner (Task 21b)

def test_demo_banner_is_one_short_line_on_phones_with_the_full_sentence_behind_a_tap():
    data = (FRONT / "data.js").read_text(encoding="utf-8")
    css = text("app.css")
    assert "demo-short" in data and "demo-full" in data and "demo-more" in data
    assert "Full planner on GitHub ›" in data and "Demo trips" in data      # honest and short
    assert 'setAttribute("aria-expanded"' in data and "demo-open" in data  # the tap opens the full sentence
    base = re.search(r"\.demo-banner\s*\{([^}]*)\}", css).group(1)
    assert re.search(r"font-size:\s*(1[6-9]|2\d)px", base), "phone banner text must be at least 16px"
    assert re.search(r"\.demo-short\s*\{[^}]*white-space:\s*nowrap", css)   # one line, never wraps
    assert re.search(r"\.demo-full\s*\{[^}]*display:\s*none", css)           # hidden on phones until tapped
    wide = re.search(r"@media \(min-width: 600px\)\s*\{\s*\.demo-banner[^}]*\}\s*\.demo-banner \.demo-short\s*\{\s*display:\s*none", css)
    assert wide, "from 600px the full sentence replaces the short line"
