import subprocess
from pathlib import Path
from collections.abc import Iterable

from utils.path_checks import path_entry_exists



def has_git_metadata(path: Path) -> bool:
    git_dir = path / ".git"

    return (
        git_dir.is_dir()
        and (git_dir / "HEAD").is_file()
        and (git_dir / "config").is_file()
    )



def require_supported_git_state(path: Path) -> None:
    git_dir = path / ".git"

    if path_entry_exists(git_dir) and not has_git_metadata(path):
        raise RuntimeError(
            f"'{git_dir}' exists but does not have the supported "
            "Git metadata structure."
        )



def run_git(
    *arguments: str,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )

    except FileNotFoundError as exc:
        if cwd is not None and not cwd.is_dir():
            raise RuntimeError(
                f"Git working directory '{cwd}' is unavailable."
            ) from exc

        raise RuntimeError(
            "Git is not installed or could not be found."
        ) from exc

    except subprocess.CalledProcessError as exc:
        error = (
            (exc.stderr or "").strip()
            or (exc.stdout or "").strip()
            or f"Exit status {exc.returncode}."
        )

        raise RuntimeError(f"Git command failed: {error}") from exc



def initialize_git_repository(path: Path) -> None:
    run_git("init", str(path))

    if not has_git_metadata(path):
        raise RuntimeError(
            "Git initialization completed without creating "
            "the expected '.git' metadata."
        )



def stage_files(
    repository: Path,
    paths: Iterable[str | Path],
) -> None:
    pathspecs = [str(path) for path in paths]

    if not pathspecs:
        return

    run_git(
        "add",
        "--",
        *pathspecs,
        cwd=repository,
    )
