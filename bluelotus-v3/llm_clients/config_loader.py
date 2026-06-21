from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


class ConfigError(RuntimeError):
    pass


def load_dotenv(path: str | Path | None = None) -> Path | None:
    env_path = Path(path) if path else _discover_env_file()
    if not env_path or not env_path.exists():
        return None
    for raw in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())
    return env_path


def project_root(explicit_root: str | Path | None = None) -> Path:
    load_dotenv(os.getenv("BLUELOTUS_ENV_FILE"))
    root_value = str(explicit_root or os.getenv("BLUELOTUS_PROJECT_ROOT") or "").strip()
    if root_value:
        return Path(root_value).expanduser().resolve()
    discovered = _discover_project_root()
    if discovered:
        os.environ.setdefault("BLUELOTUS_PROJECT_ROOT", str(discovered))
        load_dotenv(discovered / ".env")
        return discovered
    raise ConfigError("BLUELOTUS_PROJECT_ROOT is required.")


def env_required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment value: {name}")
    return value


def env_bool(name: str, default: bool | None = None) -> bool:
    value = os.getenv(name)
    if value is None:
        if default is None:
            raise ConfigError(f"Missing required boolean environment value: {name}")
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int | None = None) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        if default is None:
            raise ConfigError(f"Missing required integer environment value: {name}")
        return default
    return int(value)


def resolve_project_path(value: str | Path, root: Path | None = None) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return ((root or project_root()) / path).resolve()


def load_yaml_from_env(env_name: str) -> Dict[str, Any]:
    load_dotenv()
    path = resolve_project_path(env_required(env_name))
    if not path.exists():
        raise ConfigError(f"Configured file not found: {env_name}")
    data = load_yaml_text(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ConfigError(f"Configured file did not parse as a mapping: {env_name}")
    return data


def load_main_config() -> Dict[str, Any]:
    return load_yaml_from_env("BLUELOTUS_CONFIG_FILE")


def load_yaml_text(text: str) -> Any:
    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(text)
        return {} if parsed is None else parsed
    except ModuleNotFoundError:
        return parse_simple_yaml(text)
    except Exception:
        return parse_simple_yaml(text)


def write_text_to_output(filename: str, text: str) -> Path:
    out_dir = resolve_project_path(env_required("LLM_OUTPUT_DIR"))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    path.write_text(text, encoding="utf-8")
    return path


def append_log(filename: str, text: str) -> Path:
    log_dir = resolve_project_path(env_required("LLM_LOG_DIR"))
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / filename
    with path.open("a", encoding="utf-8") as fh:
        fh.write(text.rstrip() + "\n")
    return path


def parse_simple_yaml(text: str) -> Any:
    lines = _yaml_lines(text)
    if not lines:
        return {}
    value, index = _parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise ConfigError("YAML parse did not consume all lines.")
    return value


def _yaml_lines(text: str) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        out.append((indent, raw.strip()))
    return out


def _parse_block(lines: List[Tuple[int, str]], index: int, indent: int) -> Tuple[Any, int]:
    if lines[index][1].startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_dict(lines, index, indent)


def _parse_dict(lines: List[Tuple[int, str]], index: int, indent: int) -> Tuple[Dict[str, Any], int]:
    out: Dict[str, Any] = {}
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise ConfigError(f"Unexpected indentation near: {content}")
        if content.startswith("- ") or ":" not in content:
            break
        key, value = content.split(":", 1)
        key = key.strip()
        value = value.strip()
        index += 1
        if value:
            out[key] = _parse_scalar(value)
        elif index < len(lines) and lines[index][0] > current_indent:
            child, index = _parse_block(lines, index, lines[index][0])
            out[key] = child
        else:
            out[key] = {}
    return out, index


def _parse_list(lines: List[Tuple[int, str]], index: int, indent: int) -> Tuple[List[Any], int]:
    out: List[Any] = []
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise ConfigError(f"Unexpected list indentation near: {content}")
        if not content.startswith("- "):
            break
        value = content[2:].strip()
        index += 1
        if value and ":" in value:
            key, item_value = value.split(":", 1)
            item: Dict[str, Any] = {key.strip(): _parse_scalar(item_value.strip()) if item_value.strip() else {}}
            while index < len(lines) and lines[index][0] > current_indent:
                child_indent, child_content = lines[index]
                if child_indent <= current_indent or ":" not in child_content:
                    break
                child_key, child_value = child_content.split(":", 1)
                child_key = child_key.strip()
                child_value = child_value.strip()
                index += 1
                if child_value:
                    item[child_key] = _parse_scalar(child_value)
                elif index < len(lines) and lines[index][0] > child_indent:
                    child, index = _parse_block(lines, index, lines[index][0])
                    item[child_key] = child
                else:
                    item[child_key] = {}
            out.append(item)
        elif value:
            out.append(_parse_scalar(value))
        elif index < len(lines) and lines[index][0] > current_indent:
            child, index = _parse_block(lines, index, lines[index][0])
            out.append(child)
        else:
            out.append(None)
    return out, index


def _parse_scalar(value: str) -> Any:
    clean = value.strip().strip('"').strip("'")
    low = clean.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(clean)
    except ValueError:
        pass
    try:
        return float(clean)
    except ValueError:
        return clean


def _discover_env_file() -> Path | None:
    for candidate_root in _candidate_roots():
        candidate = candidate_root / ".env"
        if candidate.exists():
            return candidate
    return None


def _discover_project_root() -> Path | None:
    for candidate_root in _candidate_roots():
        if (candidate_root / ".env.template").exists() and (candidate_root / "config").exists():
            return candidate_root.resolve()
    return None


def _candidate_roots() -> Iterable[Path]:
    cwd = Path.cwd().resolve()
    yield cwd
    yield from cwd.parents
