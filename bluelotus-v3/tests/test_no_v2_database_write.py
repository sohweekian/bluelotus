import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.v3_db_config import load_v3_db_config, load_v3_db_settings
from llm_clients.config_loader import env_required


def main() -> None:
    cfg = load_v3_db_config()
    settings = load_v3_db_settings()
    protected = env_required(settings["database"]["protected_database_env"])
    assert cfg.database.lower() != protected.lower()
    print("PASS no v2 database write")


if __name__ == "__main__":
    main()
