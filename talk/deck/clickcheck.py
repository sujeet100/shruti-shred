"""Clickability check: in headless Chrome, is every audio clip the topmost element at its own
centre? A transparent element painted above a clip swallows the click (no hand cursor in
the viewer). Run after build.py:  python3 talk/deck/clickcheck.py"""
import re, subprocess, sys
from pathlib import Path
DECK = Path(__file__).resolve().parent
sys.path.insert(0, str(DECK))
import preview  # noqa: E402

JS = """<script>addEventListener('load',()=>{const out=[];document.querySelectorAll('img[data-video]').forEach(im=>{
const r=im.getBoundingClientRect();const pts=[[.5,.5],[.15,.5],[.85,.5]];
const bad=pts.filter(([fx,fy])=>document.elementFromPoint(r.left+r.width*fx,r.top+r.height*fy)!==im).length;
out.push(im.getAttribute('data-video').slice(-6)+':'+(bad?'BLOCKED':'ok'));});
document.body.setAttribute('data-hit',out.join(' '));});</script>"""
blobs = preview.blob_map()
tmp = DECK / "preview"; tmp.mkdir(exist_ok=True)
for f in sorted((DECK / "project/slides").glob("*.html")):
    html = f.read_text()
    if "data-video" not in html:
        continue
    pg = preview.page(html, blobs).replace("</body>", JS + "</body>")
    src = tmp / f"hit-{f.stem}.html"; src.write_text(pg)
    dom = subprocess.run([preview.CHROME, "--headless=new", "--window-size=1920,1080", "--virtual-time-budget=3000",
                          "--dump-dom", src.as_uri()], capture_output=True, text=True).stdout
    m = re.search(r'data-hit="([^"]*)"', dom)
    print(f"{f.stem:12s}", m.group(1) if m else "NO RESULT")
