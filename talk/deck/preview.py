"""Local preview of the Slides-artifact deck: one 1920x1080 PNG per slide.

Renders each `project/slides/<id>.html` section as a plain page (Google Fonts linked,
`/_blob/<id>` images mapped to the local sprite SVGs, x-embed -> iframe srcdoc) and
screenshots it with headless Chrome, so layout problems are visible before publishing.

    python3 talk/deck/preview.py            # all slides -> talk/deck/preview/NN-<id>.png
    python3 talk/deck/preview.py raga tala  # just these
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SLIDES = HERE / "project" / "slides"
SPRITES = HERE.parent / "sprites"
OUT = HERE / "preview"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FONTS = ("https://fonts.googleapis.com/css2?family=Zilla+Slab:wght@400;600;700&family=Mulish:wght@400..800"
         "&family=Pixelify+Sans:wght@400..700&family=JetBrains+Mono:wght@400;600&family=Noto+Sans+Devanagari:wght@600&display=swap")
BASE_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1920px;height:1080px;background:#000;overflow:hidden}
section{position:relative;width:1920px;height:1080px;overflow:hidden}
section:not([style*="display"]){display:flex;flex-direction:column}
h1{font-size:96px;font-weight:600;line-height:1.1}h2{font-size:64px;font-weight:600;line-height:1.15}
h3{font-size:44px;font-weight:600;line-height:1.2}p,li{font-size:32px;line-height:1.4}
aside{display:none}img{display:block}x-shape{display:block}
td,th{padding:.35em .6em;border-bottom:1px solid #2a2138;vertical-align:top}table{border-collapse:collapse;width:100%}
"""


def blob_map() -> dict[str, str]:
    """`/_blob/<id>` -> local SVG path, from the uploaded-asset map."""
    assets = json.loads((SPRITES / "assets.json").read_text())
    files = {"system": SPRITES / "p-system.svg"}
    out: dict[str, str] = {}
    for name, url in assets.items():
        p = SPRITES / "svg" / (f"p-{name}.svg" if (SPRITES / "svg" / f"p-{name}.svg").exists() else f"i-{name}.svg")
        out[url] = (files.get(name) or p).as_uri()
    titles = HERE / "titles" / "assets.json"
    if titles.exists():
        for name, url in json.loads(titles.read_text()).items():
            out[url] = (HERE / "titles" / f"{name}.png").as_uri()
    shots = HERE / "shots" / "assets.json"
    if shots.exists():
        for name, url in json.loads(shots.read_text()).items():
            out[url] = (HERE / "shots" / f"{name}.png").as_uri()
    audio = HERE.parent / "audio"
    if (audio / "assets.json").exists():
        for clip, a in json.loads((audio / "assets.json").read_text()).items():
            out[a["still"]] = (audio / f"{clip}.png").as_uri()
    return out


def embed_to_iframe(m: re.Match[str]) -> str:
    style, inner = m.group(1), m.group(2)
    return f'<iframe style="{style};border:0" srcdoc="{html.escape(inner, quote=True)}"></iframe>'


def drop_empty_divs(section: str) -> str:
    """Mirror the Slides viewer: an empty, unpainted <div> (no background, border, shadow or
    flex grow) is dropped, so it can't hold space."""
    def keep(m: re.Match[str]) -> str:
        st = m.group(1)
        return m.group(0) if any(k in st for k in ("background", "border", "box-shadow", "flex:1")) else ""
    return re.sub(r'<div style="([^"]*)"></div>', keep, section)


def page(section: str, blobs: dict[str, str]) -> str:
    section = drop_empty_divs(section)
    for url, local in blobs.items():
        section = section.replace(url, local)
    section = re.sub(r'<x-embed style="([^"]*)">(.*?)</x-embed>', embed_to_iframe, section, flags=re.S)
    return (f'<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="{FONTS}">'
            f"<style>{BASE_CSS}</style></head><body>{section}</body></html>")


def main(ids: list[str]) -> None:
    order = json.loads((HERE / "project" / "deck.json").read_text())["order"]
    blobs = blob_map()
    OUT.mkdir(exist_ok=True)
    for i, sid in enumerate(order, 1):
        if ids and sid not in ids:
            continue
        src = OUT / f"{i:02d}-{sid}.html"
        src.write_text(page((SLIDES / f"{sid}.html").read_text(), blobs))
        png = OUT / f"{i:02d}-{sid}.png"
        subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--force-device-scale-factor=1",
                        "--window-size=1920,1080", "--virtual-time-budget=4000",
                        f"--screenshot={png}", src.as_uri()], check=True, capture_output=True)
        print(png.name)


if __name__ == "__main__":
    main(sys.argv[1:])
