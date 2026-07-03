import subprocess
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", "scripts\\audit_v3_database_writes.ps1"],
        cwd=str(root),
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    print("PASS no hardcoded db config")


if __name__ == "__main__":
    main()
