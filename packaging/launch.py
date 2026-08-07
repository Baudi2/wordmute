"""PyInstaller entry point (relative imports need a real package)."""

import sys

from wordmute_app.main import main

sys.exit(main())
