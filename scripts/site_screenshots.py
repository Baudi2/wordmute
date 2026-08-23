"""Refresh the landing page's four screenshots from the design renders.

docs/design/*.png are 2x-density shots for the design round-trips
(3102x2142 for a window); the page needs them at 1x and ~150 KB. Run
after `python scripts/render_screenshots.py`:

    python scripts/site_screenshots.py
"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "docs" / "design"
SITE = ROOT / "docs" / "screenshots"

# page file -> design render (keep in sync with docs/index.html)
PICKS = {
    "queue.png": "02_queue_running.png",
    "review.png": "18_dialog_review.png",
    "add-url.png": "16_dialog_add_url_single.png",
    "wordlists.png": "09_tab_wordlists_find.png",
}

app = QGuiApplication(sys.argv)
SITE.mkdir(exist_ok=True)
for target, source in PICKS.items():
    image = QImage(str(DESIGN / source))
    if image.isNull():
        sys.exit(f"missing render: {source} — run render_screenshots.py first")
    scaled = image.scaled(image.width() // 2, image.height() // 2,
                          Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    scaled.save(str(SITE / target), "PNG")
    print(f"{target:14} {scaled.width()}x{scaled.height()}  "
          f"{(SITE / target).stat().st_size // 1024} KB  <- {source}")
