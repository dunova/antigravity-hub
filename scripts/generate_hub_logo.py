#!/usr/bin/env python3
"""
Generate the frameless Neo-Brutalist Antigravity Hub logo & icon suite.
- 100% transparent background (NO outer squircle/window frame).
- Uses the exact original Antigravity "A" arch silhouette.
- Restyles the arch interior into bold Neo-Brutalist color blocks with solid black divider lines,
  pop-art halftone texture, crisp specular highlight, thick black Neo-Brutalist outline,
  hard offset shadow, and the signature "⚡ HUB" pill badge at the base.
"""
import os
import math
import base64
import subprocess
from io import BytesIO
from PIL import Image, ImageDraw, ImageFilter

ORIG_ICON_PATH = os.path.expanduser("~/.local/share/icons/hicolor/512x512/apps/antigravity.png")
if not os.path.exists(ORIG_ICON_PATH):
    ORIG_ICON_PATH = "/usr/share/pixmaps/antigravity.png"

OUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "assets"))
os.makedirs(OUT_DIR, exist_ok=True)


def build_neo_brutalist_arch() -> str:
    """
    Extracts the exact silhouette of the original Antigravity 'A' arch,
    scales it to fill a 1024x1024 transparent canvas, and renders a pure
    Neo-Brutalist color-block & halftone interior with thick black contour
    and hard offset drop shadow.
    """
    orig = Image.open(ORIG_ICON_PATH).convert("RGBA")
    # Tight crop around the original arch with margin for stroke & shadow
    crop = orig.crop((82, 90, 430, 412))
    # Scale up to fill the 1024x1024 canvas boldly
    tw, th = 840, 776
    up = crop.resize((tw, th), Image.Resampling.LANCZOS)
    px = up.load()

    # Extract high-precision alpha mask of the original Antigravity arch silhouette
    raw_mask = Image.new("L", (tw, th), 0)
    mpx = raw_mask.load()
    for y in range(th):
        for x in range(tw):
            r, g, b, a = px[x, y]
            if a < 16:
                continue
            whiteness = min(r, g, b) / 255.0
            raw_alpha = 1.0 - whiteness
            if raw_alpha > 0.045:
                eff_a = min(1.0, (raw_alpha - 0.045) / 0.10)
                mpx[x, y] = int(eff_a * 255)

    # Smooth silhouette contour for ultra-clean vector-like edges
    smooth_mask = raw_mask.filter(ImageFilter.GaussianBlur(2.2)).point(
        lambda p: min(255, max(0, int((p - 110) * 8)))
    )

    # Create Neo-Brutalist color-block interior on (tw, th)
    interior = Image.new("RGBA", (tw, th), (0, 0, 0, 255))
    ipx = interior.load()

    # 5 bold Neo-Brutalist color zones across the "A" arch (with black 14px divider lines between bands!)
    # Band colors matching the Mac Neo-Brutalism palette:
    # 0: Lemon Yellow (#FFE600) - Apex crown
    # 1: Hot Coral / Orange (#FF6B2B) - Upper right / high energy
    # 2: Electric Mint Green (#22C55E) - Left mid wing
    # 3: Vivid Purple (#A855F7) - Right mid wing
    # 4: Electric Cyan (#00E5FF) - Lower legs
    band_width_divider = 13.0  # black line thickness in wave space

    for y in range(th):
        ny = y / float(th)
        for x in range(tw):
            nx = x / float(tw)
            # Curved diagonal wave coordinates for dynamic Neo-Brutalist color blocking
            # Wave 1 separates the crown (#FFE600) from the mid-body
            w1 = (y - 235) + 0.32 * (x - tw * 0.45) + 28.0 * math.sin(nx * math.pi * 2.2)
            # Wave 2 separates the mid-body from the lower cyan legs (#00E5FF)
            w2 = (y - 455) - 0.25 * abs(x - tw * 0.50) + 24.0 * math.cos(nx * math.pi * 2.0)
            # Diagonal split in the middle zone (left green/cyan vs right coral/purple)
            w_mid = (x - tw * 0.48) + 0.28 * (y - 340)

            # Check if on a black Neo-Brutalist divider line between color blocks
            if abs(w1) < band_width_divider or abs(w2) < band_width_divider:
                ipx[x, y] = (0, 0, 0, 255)
                continue
            if w1 >= band_width_divider and w2 <= -band_width_divider and abs(w_mid) < band_width_divider:
                ipx[x, y] = (0, 0, 0, 255)
                continue

            # Assign bold Neo-Brutalist color block
            if w1 < 0:
                # Crown: Lemon Yellow #FFE600 -> Warm Amber #FF9F1C on far right
                t = max(0.0, min(1.0, (nx - 0.35) * 2.2))
                cr = 255
                cg = int(230 * (1 - t) + 120 * t)
                cb = int(0 * (1 - t) + 45 * t)
            elif w2 < 0:
                if w_mid < 0:
                    # Left wing: Vivid Neo Green #22C55E
                    cr, cg, cb = 34, 211, 102
                else:
                    # Right wing: Hot Pink/Coral #FF3B6B -> Violet #C084FC
                    t = max(0.0, min(1.0, (ny - 0.28) * 3.0))
                    cr = int(255 * (1 - t) + 192 * t)
                    cg = int(59 * (1 - t) + 132 * t)
                    cb = int(107 * (1 - t) + 252 * t)
            else:
                # Lower legs: Electric Sky Cyan #00D8FF on left, Deep Neo Blue #38BDF8 on right
                if x < tw * 0.5:
                    cr, cg, cb = 14, 210, 255
                else:
                    cr, cg, cb = 56, 189, 248

            # Pop-art / Neo-Brutalist subtle halftone dot pattern inside the blocks
            grid = 22
            gx = (x % grid) - grid / 2.0
            gy = (y % grid) - grid / 2.0
            if (gx * gx + gy * gy) < 9.5:
                # Subtle darker dot for tactile Neo-Brutalist texture
                cr = int(cr * 0.91)
                cg = int(cg * 0.91)
                cb = int(cb * 0.91)

            ipx[x, y] = (cr, cg, cb, 255)

    # Add a crisp inner black inset shadow on the bottom/right & white specular pop highlight on top-left
    # Outer black stroke mask (~20px thick Neo-Brutalist outline)
    stroke_aa = smooth_mask.filter(ImageFilter.GaussianBlur(12.5)).point(
        lambda p: min(255, max(0, int((p - 14) * 14)))
    )

    canvas = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    ox = (1024 - tw) // 2 - 12
    oy = 56

    # 1. Hard solid black Neo-Brutalist offset shadow (+28px, +30px)
    shadow_img = Image.new("RGBA", (tw, th), (0, 0, 0, 255))
    canvas.paste(shadow_img, (ox + 28, oy + 30), stroke_aa)

    # 2. Thick solid black Neo-Brutalist contour
    stroke_img = Image.new("RGBA", (tw, th), (0, 0, 0, 255))
    canvas.paste(stroke_img, (ox, oy), stroke_aa)

    # 3. Paste Neo-Brutalist color-block interior
    canvas.paste(interior, (ox, oy), smooth_mask)

    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def build_master_svg(arch_b64: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <!-- 1. Frameless Neo-Brutalist Antigravity "A" Arch (100% Transparent Background) -->
  <image x="0" y="0" width="1024" height="1024" href="data:image/png;base64,{arch_b64}"/>

  <!-- 2. Neo-Brutalist "⚡ HUB" Pill Badge across the Lower Arch Bridge -->
  <g transform="translate(262, 742)">
    <!-- Hard Offset Black Shadow -->
    <rect x="20" y="20" width="480" height="142" rx="42" fill="#000000"/>
    <!-- Bright Lemon-Yellow Pill Body -->
    <rect x="0" y="0" width="480" height="142" rx="42" fill="#FFE600" stroke="#000000" stroke-width="20"/>
    <!-- Lightning Icon inside Badge -->
    <polygon points="98,24 54,78 88,78 74,118 122,62 88,62" fill="#000000" stroke="#000000" stroke-width="4" stroke-linejoin="round"/>
    <!-- Crisp Extra-Bold "HUB" Typography -->
    <text x="286" y="106" font-family="'JetBrains Mono', 'DejaVu Sans', sans-serif" font-size="100" font-weight="900" letter-spacing="6" text-anchor="middle" fill="#000000" stroke="#000000" stroke-width="6" paint-order="stroke fill">HUB</text>
  </g>
</svg>
'''


def main():
    arch_b64 = build_neo_brutalist_arch()
    master_svg = build_master_svg(arch_b64)

    svg_repo_path = os.path.join(OUT_DIR, "antigravity-hub-logo.svg")
    with open(svg_repo_path, "w", encoding="utf-8") as f:
        f.write(master_svg)

    tmp_1024 = "/tmp/antigravity_hub_1024.png"
    subprocess.run(["rsvg-convert", "-w", "1024", "-h", "1024", svg_repo_path, "-o", tmp_1024], check=True)
    hi = Image.open(tmp_1024).convert("RGBA")

    repo_png_path = os.path.join(OUT_DIR, "antigravity-hub-logo.png")
    icon_512 = hi.resize((512, 512), Image.Resampling.LANCZOS)
    icon_512.save(repo_png_path, "PNG")
    print("Saved frameless Neo-Brutalist master 512x512 PNG:", repo_png_path)

    sizes = [512, 256, 128, 64, 48, 32, 16]
    for sz in sizes:
        resized = hi.resize((sz, sz), Image.Resampling.LANCZOS)
        for suffix in [f"{sz}x{sz}", f"{sz}x{sz}@2"]:
            tdir = os.path.expanduser(f"~/.local/share/icons/hicolor/{suffix}/apps")
            os.makedirs(tdir, exist_ok=True)
            resized.save(os.path.join(tdir, "antigravity-hub.png"), "PNG")

    svg_dir = os.path.expanduser("~/.local/share/icons/hicolor/scalable/apps")
    os.makedirs(svg_dir, exist_ok=True)
    with open(os.path.join(svg_dir, "antigravity-hub.svg"), "w", encoding="utf-8") as f:
        f.write(master_svg)

    hub_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "hub"))
    hi.resize((64, 64), Image.Resampling.LANCZOS).save(os.path.join(hub_dir, "favicon.png"), "PNG")
    icon_512.save(os.path.join(hub_dir, "app_icon_512.png"), "PNG")
    print("All frameless Neo-Brutalist icons generated successfully.")


if __name__ == "__main__":
    main()
