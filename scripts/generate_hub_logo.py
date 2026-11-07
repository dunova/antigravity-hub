#!/usr/bin/env python3
"""
Generate the optimized Antigravity Hub logo & icon suite (Neo-Brutalism + Original Antigravity Rainbow Arch).
Extracts the rainbow arch from antigravity.png by un-compositing the white background, boosts vibrancy,
adds Neo-Brutalist contour & hard shadow, and composites with crisp SVG vector badge via rsvg-convert.
"""
import os
import base64
import subprocess
from io import BytesIO
from PIL import Image, ImageFilter, ImageEnhance

ORIG_ICON_PATH = os.path.expanduser("~/.local/share/icons/hicolor/512x512/apps/antigravity.png")
if not os.path.exists(ORIG_ICON_PATH):
    ORIG_ICON_PATH = "/usr/share/pixmaps/antigravity.png"

OUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "assets"))
os.makedirs(OUT_DIR, exist_ok=True)


def extract_clean_rainbow_arch() -> str:
    """
    Un-composites the original Antigravity rainbow arch from its white background,
    enhances color vibrancy, adds a crisp Neo-Brutalist black outline + hard shadow,
    and returns a base64 PNG data URI at 1024x1024 canvas coordinates.
    """
    orig = Image.open(ORIG_ICON_PATH).convert("RGBA")
    # Crop with generous margin around the rainbow arch (bbox 104..412, 110..393) so stroke dilation never clips
    crop = orig.crop((68, 76, 444, 424))
    # Upscale 2x first for smooth subpixel un-compositing
    tw, th = 680, 630
    up = crop.resize((tw, th), Image.Resampling.LANCZOS)
    px = up.load()

    clean = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    cpx = clean.load()

    for y in range(th):
        for x in range(tw):
            r, g, b, a = px[x, y]
            if a < 16:
                continue
            # Distance from pure white (255, 255, 255)
            # Since every point on the rainbow arch is saturated (red/orange/yellow/green/blue),
            # at least one channel is significantly below 255.
            min_c = min(r, g, b)
            whiteness = min_c / 255.0
            raw_alpha = 1.0 - whiteness
            # Smooth ramp: anything with raw_alpha < 0.035 is pure background white
            if raw_alpha <= 0.035:
                continue
            # Full opacity inside the arch body (raw_alpha >= 0.16)
            eff_a = min(1.0, (raw_alpha - 0.035) / 0.125)
            # Un-premultiply white from the edge pixels so there is zero white halo
            if eff_a < 1.0 and raw_alpha > 0.001:
                ur = int(max(0, min(255, (r - 255.0 * (1.0 - raw_alpha)) / raw_alpha)))
                ug = int(max(0, min(255, (g - 255.0 * (1.0 - raw_alpha)) / raw_alpha)))
                ub = int(max(0, min(255, (b - 255.0 * (1.0 - raw_alpha)) / raw_alpha)))
            else:
                ur, ug, ub = r, g, b
            cpx[x, y] = (ur, ug, ub, int(eff_a * 255))

    # Boost saturation & contrast of the extracted rainbow arch
    r, g, b, a = clean.split()
    rgb = Image.merge("RGB", (r, g, b))
    rgb = ImageEnhance.Color(rgb).enhance(1.32)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.10)
    vivid_arch = Image.merge("RGBA", (*rgb.split(), a))

    # Build a crisp isotropic circular Neo-Brutalist black border + offset drop shadow around the arch
    # (Using GaussianBlur + threshold instead of square MaxFilter so tips remain 100% round and organic)
    binary_mask = a.point(lambda p: 255 if p > 85 else 0)
    smooth_mask = binary_mask.filter(ImageFilter.GaussianBlur(1.5)).point(lambda p: 255 if p > 115 else 0)
    stroke_aa = smooth_mask.filter(ImageFilter.GaussianBlur(8.5)).point(lambda p: min(255, max(0, int((p - 18) * 14))))

    pad = 64
    layer = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
    # Hard offset shadow (+16, +18)
    shadow_img = Image.new("RGBA", (tw, th), (15, 17, 23, 255))
    layer.paste(shadow_img, (pad + 16, pad + 18), stroke_aa)

    # Solid black Neo-Brutalist outline
    stroke_img = Image.new("RGBA", (tw, th), (0, 0, 0, 255))
    layer.paste(stroke_img, (pad, pad), stroke_aa)

    # Vivid rainbow arch interior
    layer.paste(vivid_arch, (pad, pad), smooth_mask)

    buf = BytesIO()
    layer.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def build_master_svg(arch_b64: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <defs>
    <clipPath id="card-clip">
      <rect x="64" y="64" width="872" height="872" rx="206" ry="206"/>
    </clipPath>
    <pattern id="neo-dots" x="0" y="0" width="44" height="44" patternUnits="userSpaceOnUse">
      <circle cx="22" cy="22" r="3.2" fill="#D5CEC0" opacity="0.75"/>
    </pattern>
    <linearGradient id="card-bg" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#FFFDF9"/>
      <stop offset="100%" stop-color="#F4EFE6"/>
    </linearGradient>
  </defs>

  <!-- 1. Neo-Brutalist Hard Offset Card Shadow -->
  <rect x="92" y="92" width="872" height="872" rx="206" ry="206" fill="#0F1117"/>

  <!-- 2. Clipped Squircle Interior -->
  <g clip-path="url(#card-clip)">
    <!-- Warm Paper Base + Dot Matrix -->
    <rect x="64" y="64" width="872" height="872" fill="url(#card-bg)"/>
    <rect x="64" y="218" width="872" height="718" fill="url(#neo-dots)"/>

    <!-- Top Neo-Brutalism Lemon-Yellow Header Bar (#FFE600) -->
    <rect x="64" y="64" width="872" height="156" fill="#FFE600"/>
    <line x1="64" y1="220" x2="936" y2="220" stroke="#000000" stroke-width="18"/>

    <!-- Three Quota Track Dots (Purple Gemini 4, Sky Blue Gemini 3.8, Orange Claude 5.5) -->
    <g transform="translate(0, 4)">
      <!-- Purple G4 -->
      <circle cx="176" cy="144" r="24" fill="#000000"/>
      <circle cx="170" cy="138" r="24" fill="#C084FC" stroke="#000000" stroke-width="9"/>
      <!-- Cyan G3.8 -->
      <circle cx="252" cy="144" r="24" fill="#000000"/>
      <circle cx="246" cy="138" r="24" fill="#38BDF8" stroke="#000000" stroke-width="9"/>
      <!-- Orange Claude -->
      <circle cx="328" cy="144" r="24" fill="#000000"/>
      <circle cx="322" cy="138" r="24" fill="#FB923C" stroke="#000000" stroke-width="9"/>
    </g>

    <!-- Top-Right Green Active Pill in Header -->
    <g transform="translate(744, 106)">
      <rect x="6" y="6" width="114" height="64" rx="32" fill="#000000"/>
      <rect x="0" y="0" width="114" height="64" rx="32" fill="#22C55E" stroke="#000000" stroke-width="9"/>
      <polygon points="64,10 38,35 55,35 48,54 76,29 59,29" fill="#FFE600" stroke="#000000" stroke-width="5" stroke-linejoin="round"/>
    </g>

    <!-- 3. Extracted & Outlined Original Antigravity Rainbow Arch -->
    <image x="116" y="162" width="768" height="720" href="data:image/png;base64,{arch_b64}"/>

    <!-- 4. Neo-Brutalist "⚡ HUB" Pill Badge across the Arch Base -->
    <g transform="translate(290, 740)">
      <!-- Hard Offset Shadow -->
      <rect x="14" y="14" width="420" height="124" rx="36" fill="#000000"/>
      <!-- Lemon-Yellow Pill Body -->
      <rect x="0" y="0" width="420" height="124" rx="36" fill="#FFE600" stroke="#000000" stroke-width="15"/>
      <!-- Lightning Icon inside Badge -->
      <polygon points="86,22 48,68 78,68 66,102 108,54 78,54" fill="#000000" stroke="#000000" stroke-width="3" stroke-linejoin="round"/>
      <!-- Crisp Extra-Bold "HUB" Typography -->
      <text x="252" y="93" font-family="'JetBrains Mono', 'DejaVu Sans', sans-serif" font-size="88" font-weight="900" letter-spacing="5" text-anchor="middle" fill="#000000" stroke="#000000" stroke-width="5" paint-order="stroke fill">HUB</text>
    </g>
  </g>

  <!-- 5. Outer Squircle Thick Black Neo-Brutalist Border -->
  <rect x="64" y="64" width="872" height="872" rx="206" ry="206" fill="none" stroke="#000000" stroke-width="24"/>
</svg>
'''


def main():
    arch_b64 = extract_clean_rainbow_arch()
    master_svg = build_master_svg(arch_b64)

    svg_repo_path = os.path.join(OUT_DIR, "antigravity-hub-logo.svg")
    with open(svg_repo_path, "w", encoding="utf-8") as f:
        f.write(master_svg)

    # Render 1024x1024 via rsvg-convert then downsample with Lanczos for razor-sharp edges
    tmp_1024 = "/tmp/antigravity_hub_1024.png"
    subprocess.run(["rsvg-convert", "-w", "1024", "-h", "1024", svg_repo_path, "-o", tmp_1024], check=True)
    hi = Image.open(tmp_1024).convert("RGBA")

    repo_png_path = os.path.join(OUT_DIR, "antigravity-hub-logo.png")
    icon_512 = hi.resize((512, 512), Image.Resampling.LANCZOS)
    icon_512.save(repo_png_path, "PNG")
    print("Saved master 512x512 PNG:", repo_png_path)

    # Save multi-resolution hicolor icons for Linux Desktop & App Launcher
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

    # Save web app favicons in hub/ directory
    hub_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "hub"))
    hi.resize((64, 64), Image.Resampling.LANCZOS).save(os.path.join(hub_dir, "favicon.png"), "PNG")
    icon_512.save(os.path.join(hub_dir, "app_icon_512.png"), "PNG")
    print("All icons generated successfully.")


if __name__ == "__main__":
    main()
