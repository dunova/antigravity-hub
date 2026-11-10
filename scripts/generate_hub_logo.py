#!/usr/bin/env python3
"""
Generate the pure Omarchy-style silhouette logo & icon suite for Antigravity Hub v3.0.0.
- Strict Omarchy flat aesthetic: ZERO gradients, zero artificial shadows.
- Uses the authentic Google Antigravity sweeping aerodynamic arch silhouette.
- Crisp high-contrast monochrome vector icon:
  * For desktop application icon: #1c1c1e flat squircle container + #f2f2f7 Antigravity arch mark.
  * For README/docs badge: pure flat monochrome badge.
  * Synchronizes all hicolor png & svg icon sizes.
"""
import os
import re
import subprocess

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_LOGO_SVG = os.path.join(PROJECT_ROOT, "src", "assets", "logo.svg")
DOCS_ASSETS = os.path.join(PROJECT_ROOT, "docs", "assets")
PKGBUILD_SVG = os.path.join(PROJECT_ROOT, "pkgbuild", "antigravity-hub.svg")
HICOLOR_ROOT = os.path.expanduser("~/.local/share/icons/hicolor")

os.makedirs(DOCS_ASSETS, exist_ok=True)

# 1. Read vector path from src/assets/logo.svg
with open(SRC_LOGO_SVG, "r", encoding="utf-8") as f:
    src_content = f.read()

m = re.search(r'd="([^"]+)"', src_content)
if not m:
    raise ValueError(f"Could not extract path d attribute from {SRC_LOGO_SVG}")
path_d = m.group(1)

# 2. Build Omarchy App Icon SVG (512x512 with 480x480 rx=112 dark container, #1c1c1e flat, zero gradients)
app_icon_svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <title>Antigravity Hub</title>
  <!-- Omarchy dark squircle container (#1c1c1e flat surface, ZERO gradients) -->
  <rect x="16" y="16" width="480" height="480" rx="112" fill="#1c1c1e" stroke="#323238" stroke-width="4"/>

  <!-- Antigravity sweeping arch silhouette mark (#f2f2f7 light monochrome) -->
  <g transform="translate(76, 76) scale(15)" fill="#f2f2f7">
    <path d="{path_d}" />
  </g>
</svg>"""

with open(PKGBUILD_SVG, "w", encoding="utf-8") as f:
    f.write(app_icon_svg)

docs_logo_svg = os.path.join(DOCS_ASSETS, "antigravity-hub-logo.svg")
with open(docs_logo_svg, "w", encoding="utf-8") as f:
    f.write(app_icon_svg)

# 3. Generate PNGs using ImageMagick
sizes = [16, 32, 48, 64, 128, 256, 512]
docs_png = os.path.join(DOCS_ASSETS, "antigravity-hub-logo.png")
subprocess.run(["magick", PKGBUILD_SVG, "-resize", "512x512", docs_png], check=True)

for s in sizes:
    dir_1x = os.path.join(HICOLOR_ROOT, f"{s}x{s}", "apps")
    dir_2x = os.path.join(HICOLOR_ROOT, f"{s}x{s}@2", "apps")
    os.makedirs(dir_1x, exist_ok=True)
    os.makedirs(dir_2x, exist_ok=True)
    subprocess.run(["magick", PKGBUILD_SVG, "-resize", f"{s}x{s}", os.path.join(dir_1x, "antigravity-hub.png")], check=True)
    subprocess.run(["magick", PKGBUILD_SVG, "-resize", f"{s*2}x{s*2}", os.path.join(dir_2x, "antigravity-hub.png")], check=True)

# Also scalable svg
scalable_dir = os.path.join(HICOLOR_ROOT, "scalable", "apps")
os.makedirs(scalable_dir, exist_ok=True)
with open(os.path.join(scalable_dir, "antigravity-hub.svg"), "w", encoding="utf-8") as f:
    f.write(app_icon_svg)

print("Successfully generated all Omarchy silhouette icons and assets for v3.0.0.")
