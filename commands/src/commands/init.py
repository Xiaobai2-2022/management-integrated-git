import configparser
import json
import os
import tempfile
from pathlib import Path

from utils.git import (
    has_git_metadata,
    initialize_git_repository,
    require_supported_git_state,
    stage_files,
)
from utils.path_checks import (
    is_directory_empty,
    path_entry_exists,
    require_directory,
    require_empty_directory,
    resolve_directory,
)
from utils.repo_checks import (
    require_mig_not_initialized,
    validate_workflow,
    SHARED_METADATA_PATHS,
)

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InitResult:
    directory: Path
    metadata_staged: bool = False
    staging_error: str | None = None




def _write_initial_metadata(mig_dir: Path, workflow: str) -> None:
    mig_dir.mkdir()

    config = configparser.ConfigParser()
    config["repository"] = {"workflow": workflow}

    with (mig_dir / "config").open("w", encoding="utf-8") as file:
        config.write(file)

    workflow_data = {
        "workflow": workflow,
        "issues": [],
    }

    with (mig_dir / "workflow.json").open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(
            workflow_data,
            file,
            indent=4,
            allow_nan=False,
        )
        file.write("\n")



def _initialize_repository(
    directory: str | Path,
    workflow: str,
    force: bool = False,
) -> None:
    """
    Initialize MIG by publishing prepared metadata with one rename.

    Supported targets:
    - A missing directory.
    - An existing empty directory.
    - An existing ordinary Git repository, with force=True.

    A non-empty directory without Git is unsupported because adding
    both .git and .mig cannot be published with one atomic rename.

    Atomicity concerns visibility of repository metadata, not
    durability across power loss.

    Concurrent changes to the target directory are unsupported.
    """
    workflow = validate_workflow(workflow)
    path = resolve_directory(directory)

    target_exists = path_entry_exists(path)

    if target_exists:
        require_directory(path)

    require_mig_not_initialized(path)
    require_supported_git_state(path)

    git_exists = has_git_metadata(path)
    target_is_empty = (
        is_directory_empty(path) if target_exists else True
    )

    if target_exists and not target_is_empty:
        if not force:
            require_empty_directory(path)

        if not git_exists:
            raise RuntimeError(
                "Cannot atomically initialize MIG in a non-empty "
                "directory without Git. Initialize Git there first, "
                "then rerun MIG initialization with --force."
            )

    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix="mig-init-",
        dir=path.parent,
    ) as temp:
        staging = Path(temp)

        if git_exists:
            staged_mig = staging / ".mig"

            _write_initial_metadata(staged_mig, workflow)

            require_directory(path)
            require_supported_git_state(path)

            if not has_git_metadata(path):
                raise RuntimeError(
                    "Git metadata disappeared during initialization."
                )

            require_mig_not_initialized(path)

            os.rename(staged_mig, path / ".mig")
            return

        staged_repo = staging / "repository"
        staged_repo.mkdir()

        _write_initial_metadata(
            staged_repo / ".mig",
            workflow,
        )
        initialize_git_repository(staged_repo)

        if path_entry_exists(path):
            require_directory(path)
            require_mig_not_initialized(path)
            require_supported_git_state(path)
            require_empty_directory(path)

            if os.name == "nt":
                raise RuntimeError(
                    "Atomic initialization into an existing empty "
                    "directory is unsupported on Windows by this "
                    "implementation. Remove the empty directory "
                    "and rerun initialization."
                )

        os.rename(staged_repo, path)



def init_repo(
    directory: str | Path,
    workflow: str,
    force: bool = False,
    *,
    stage: bool = False,
) -> InitResult:
    """
    Atomically initialize MIG, then optionally stage shared metadata.

    Initialization failures raise an exception.

    Staging failures are returned in InitResult.staging_error.
    They do not undo successful initialization.

    No commit is created.
    """
    path = resolve_directory(directory)

    _initialize_repository(
        directory=path,
        workflow=workflow,
        force=force,
    )

    if not stage:
        return InitResult(directory=path)

    try:
        stage_files(path, SHARED_METADATA_PATHS)
    except (RuntimeError, OSError) as exc:
        return InitResult(
            directory=path,
            staging_error=str(exc),
        )

    return InitResult(
        directory=path,
        metadata_staged=True,
    )
