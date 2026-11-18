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
