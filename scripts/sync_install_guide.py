"""Copy docs/INSTALL_GUIDE.md into the landing page's embedded copy.

docs/index.html carries the whole guide inside
<script type="text/plain" id="ai-guide"> so the page can show it and
offer "copy for the AI assistant" — the two must never drift. The only
difference is the installer file name, which the page templates as
{{INSTALLER}} and fills in from the latest release.

    python scripts/sync_install_guide.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "docs" / "INSTALL_GUIDE.md"
PAGE = ROOT / "docs" / "index.html"
OPEN_TAG = '<script type="text/plain" id="ai-guide">'

guide = GUIDE.read_text(encoding="utf-8")
guide = re.sub(r"WordMute-Setup-[\d.]+\.exe", "{{INSTALLER}}", guide)

page = PAGE.read_text(encoding="utf-8")
start = page.find(OPEN_TAG)
if start < 0:
    sys.exit(f"{OPEN_TAG} not found in {PAGE}")
body = start + len(OPEN_TAG)
end = page.find("</script>", body)
if end < 0:
    sys.exit("unterminated ai-guide block")

updated = page[:body] + "\n" + guide.strip() + "\n" + page[end:]
if updated == page:
    print("already in sync")
else:
    PAGE.write_text(updated, encoding="utf-8")
    print(f"embedded guide updated ({len(guide.splitlines())} lines)")
