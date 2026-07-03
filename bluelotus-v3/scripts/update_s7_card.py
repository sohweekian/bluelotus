#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

script = Path(__file__).resolve().parent / "update_dashboard_widgets.py"
raise SystemExit(subprocess.call([sys.executable, str(script), "--restore", "--verify-public"]))
