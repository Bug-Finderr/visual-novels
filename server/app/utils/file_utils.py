import shutil
from pathlib import Path


def ensure_dir(path: str | Path) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def write_file(path: str | Path, data: bytes) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def remove_dir(path: str | Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def file_exists(path: str | Path) -> bool:
    return Path(path).exists()
