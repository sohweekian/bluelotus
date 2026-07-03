from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_clients.config_loader import env_required, load_dotenv, project_root, resolve_project_path


def main() -> int:
    load_dotenv()
    root = project_root()
    output_dir = resolve_project_path(env_required("LLM_OUTPUT_DIR"))
    protected = os.getenv("BLUELOTUS_PROTECTED_ROOT", "").strip()
    if protected:
        protected_path = Path(protected).expanduser().resolve()
        assert not root.is_relative_to(protected_path), "Project root points inside protected production root."
        assert not output_dir.is_relative_to(protected_path), "LLM output directory points inside protected production root."
    output_dir.mkdir(parents=True, exist_ok=True)
    probe = output_dir / "no_v2_write_probe.txt"
    probe.write_text("ok", encoding="utf-8")
    assert probe.exists()
    print("PASS no protected production write target")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
