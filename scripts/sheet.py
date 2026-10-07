"""Contact sheets + an index page for everything in renders/.

Generic: every subdirectory of renders/ becomes a sheet, cells keep their aspect.
"""
import glob, json, os
from PIL import Image, ImageDraw

CELL = 256
os.makedirs("renders/sheets", exist_ok=True)

kinds = sorted(d for d in os.listdir("renders")
               if os.path.isdir(os.path.join("renders", d)) and d != "sheets")
for kind in kinds:
    files = sorted(glob.glob(f"renders/{kind}/*.png"))
    if not files:
        continue
    sample = Image.open(files[0])
    ar = sample.width / sample.height
    tw = CELL
    th = max(1, int(round(CELL / ar)))
    cols = max(1, min(6, 1400 // tw))
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * (th + 18)), (12, 12, 12))
    dr = ImageDraw.Draw(sheet)
    for i, f in enumerate(files):
        im = Image.open(f).convert("RGB")
        im.thumbnail((tw, th))
        x, y = (i % cols) * tw, (i // cols) * (th + 18)
        sheet.paste(im, (x, y))
        dr.text((x + 4, y + th + 3), os.path.basename(f)[:-4], fill=(200, 190, 170))
    sheet.save(f"renders/sheets/{kind}.jpg", quality=88)

rows = []
for j in sorted(glob.glob("renders/*/*.json")):
    try:
        m = json.load(open(j))
    except Exception:
        continue
    rel = os.path.relpath(j[:-5] + ".png", "renders").replace(os.sep, "/")
    rows.append(f"| {m.get('kind', '')} | {m.get('id', '')} | {m.get('seed', '')} | "
                f"{m.get('seconds', '')}s | {m.get('size', '')} | ![]({rel}) |")

sheets_md = "\n\n".join(f"![{k}](sheets/{k}.jpg)" for k in kinds)
open("renders/README.md", "w").write(
    "# Renders\n\nBatch images produced by the `render` workflow (see the main branch).\n\n"
    + sheets_md + "\n\n| set | id | seed | time | size | image |\n|---|---|---|---|---|---|\n"
    + "\n".join(rows) + "\n")
print(f"sheets: {kinds}, rows: {len(rows)}")
