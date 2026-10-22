"""Where the fonts are. Everything comes from the environment (or defaults to the Mac's system fonts), nothing is hard-coded to one machine."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..errors import ConfigError

SYSTEM_FONTS = "/System/Library/Fonts/Supplemental"


@dataclass(frozen=True)
class FontSet:
    """Font files for the lettering and the generated pages.

    * `caption`: bold Arabic face for panel captions (LETTER_FONT; Tahoma Bold, because Geeza Pro lacks the "!" glyph).
    * `title`, `body`: the cover and cast-page faces (Waseem.ttc, Baghdad.ttc in FONT_DIR).
    * `vazir_bold`, `vazir_regular`, `latin`: the lab page (site/private/fonts and the Geist file of the site's node_modules).
    """

    caption: Path
    title: Path
    body: Path
    vazir_bold: Path
    vazir_regular: Path
    latin: Path

    @classmethod
    def from_env(cls, env: Mapping[str, str], site_dir: Path) -> FontSet:
        base = Path(env.get("FONT_DIR", SYSTEM_FONTS))
        return cls(
            caption=Path(env.get("LETTER_FONT", str(base / "Tahoma Bold.ttf"))),
            title=base / "Waseem.ttc",
            body=base / "Baghdad.ttc",
            vazir_bold=site_dir / "private/fonts/Vazirmatn_700.ttf",
            vazir_regular=site_dir / "private/fonts/Vazirmatn_400.ttf",
            latin=site_dir / "node_modules/next/dist/compiled/@vercel/og/Geist-Regular.ttf",
        )

    def need(self, *names: str) -> None:
        """ConfigError naming every missing font file among the given fields."""
        missing = [f"{n}: {getattr(self, n)}" for n in names if not getattr(self, n).is_file()]
        if missing:
            raise ConfigError("font file(s) not found (set FONT_DIR / LETTER_FONT): " + "; ".join(missing))


def default_fonts(site_dir: Path | None = None) -> FontSet:
    return FontSet.from_env(os.environ, site_dir or Path("site"))
