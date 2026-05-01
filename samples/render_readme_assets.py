"""Rasterize README diagram SVGs to PNG (GitHub / IDE preview; SVG often blocked in README)."""

from __future__ import annotations

from pathlib import Path

import fitz

_HERE = Path(__file__).resolve().parent
_ASSETS = _HERE / "assets"


def main() -> None:
    for name in ("samples-hub",):
        svg = _ASSETS / f"{name}.svg"
        png = _ASSETS / f"{name}.png"
        doc = fitz.open(svg)
        pix = doc[0].get_pixmap(alpha=False, dpi=144)
        pix.save(png)
        doc.close()
        print(f"Wrote {png} ({pix.width}x{pix.height})")


if __name__ == "__main__":
    main()
