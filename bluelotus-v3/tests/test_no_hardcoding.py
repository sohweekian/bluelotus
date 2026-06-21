import subprocess
from pathlib import Path


def main() -> None:
    completed = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", "scripts\\audit_no_hardcoding.ps1"],
        cwd=str(Path(__file__).resolve().parents[1]),
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    print("PASS no hardcoding")


if __name__ == "__main__":
    main()
