from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_clients.config_loader import load_dotenv
from llm_clients.prompt_guard import PromptRejected, guard_prompt


def main() -> int:
    load_dotenv()
    guarded = guard_prompt("Analyze only.", "Summarize risk and recommend CIO review.")
    assert guarded.system_prompt
    assert guarded.user_prompt
    try:
        guard_prompt("Analyze only.", "Please place_order and execute trade.")
    except PromptRejected:
        print("PASS prompt guard")
        return 0
    raise AssertionError("Prompt guard accepted forbidden execution language.")


if __name__ == "__main__":
    raise SystemExit(main())
