from pathlib import Path

from mig.mig_exceptions import NonEmptyDirectoryInitError



def resolve_directory(directory: str | Path) -> Path:
    return Path(directory).expanduser().resolve()



def path_entry_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()



def require_directory(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"'{path}' does not exist.")

    if not path.is_dir():
        raise NotADirectoryError(f"'{path}' is not a directory.")



def is_directory_empty(path: Path) -> bool:
    require_directory(path)
    return next(path.iterdir(), None) is None



def require_empty_directory(path: Path) -> None:
    if not is_directory_empty(path):
        raise NonEmptyDirectoryInitError(
            "Target directory is not empty. "
            "To initialize it, rerun the command with --force."
        )
