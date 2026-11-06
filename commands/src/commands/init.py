from mig.mig_exceptions import NonEmptyDirectoryInitError

import configparser
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any



def init_repo(
    directory: str | Path,
    workflow: str,
    force: bool = False,
) -> None:
    """
    Initialize a MIG repository.

    The repository metadata is first created in a temporary staging directory.
    Nothing is copied into the target directory until all preparation steps,
    including Git initialization, succeed.

    :param directory: Directory in which to initialize the repository.
    :param workflow: Workflow type for the repository.
    :param force: Allow initialization inside a non-empty directory.

    :raises FileExistsError: If MIG is already initialized.
    :raises ValueError: If the workflow type is unsupported.
    :raises RuntimeError: If Git initialization fails.
    :raises OSError: If filesystem operations fail.
    :raises NonEmptyDirectoryInitError: If initializing MIG in a non-empty directory without --force.
    """

    supported_workflows = {
        "kanban",
        "scrum",
        "waterfall",
        "custom",
    }

    workflow = workflow.lower()

    if workflow not in supported_workflows:
        raise ValueError(
            f"Unsupported workflow '{workflow}'. "
            f"Expected one of: {', '.join(sorted(supported_workflows))}."
        )

    path = Path(directory).expanduser().resolve()

    mig_dir = path / ".mig"
    git_dir = path / ".git"

    if mig_dir.exists():
        raise FileExistsError(
            f"'{path}' is already a MIG repository."
        )

    git_already_initialized = (
            git_dir.is_dir()
            and (git_dir / "HEAD").is_file()
            and (git_dir / "config").is_file()
    )

    if git_dir.exists() and not git_already_initialized:
        raise RuntimeError(
            f"'{git_dir}' exists but does not appear to be a valid Git repository."
        )

    created_root = False
    committed_paths: list[Path] = []

    try:
        if not path.exists():
            path.mkdir(parents=True)
            created_root = True

        if not path.is_dir():
            raise NotADirectoryError(
                f"'{path}' is not a directory."
            )

        if any(path.iterdir()) and not force:
            raise NonEmptyDirectoryInitError(
                "Target directory is not empty. "
                "To initialize it, rerun the command with --force."
            )

        with tempfile.TemporaryDirectory(
            prefix="mig-init-",
            dir=path.parent,
        ) as temp:
            staging = Path(temp)

            staging_mig = staging / ".mig"
            staging_mig.mkdir()

            # ---------------------------------------------------------
            # 1. Write MIG config
            # ---------------------------------------------------------

            config = configparser.ConfigParser()

            config["repository"] = {
                "workflow": workflow,
            }

            config_path = staging_mig / "config"

            with config_path.open("w", encoding="utf-8") as file:
                config.write(file)

            # ---------------------------------------------------------
            # 2. Generate initial JSON
            # ---------------------------------------------------------

            workflow_data: dict[str, Any] = {
                "workflow": workflow,
                "issues": [],
            }

            workflow_json_path = staging_mig / "workflow.json"

            with workflow_json_path.open(
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    workflow_data,
                    file,
                    indent=4,
                    allow_nan=False,
                )

                file.write("\n")

            # ---------------------------------------------------------
            # 3. Initialize Git if necessary
            # ---------------------------------------------------------

            staging_git = staging / ".git"

            if not git_already_initialized:
                try:
                    subprocess.run(
                        ["git", "init", str(staging)],
                        check=True,
                        capture_output=True,
                        text=True,
                    )

                except FileNotFoundError as exc:
                    raise RuntimeError(
                        "Git is not installed or could not be found."
                    ) from exc

                except subprocess.CalledProcessError as exc:
                    error = exc.stderr.strip() or exc.stdout.strip()

                    raise RuntimeError(
                        f"Failed to initialize Git repository: {error}"
                    ) from exc

                if not staging_git.is_dir():
                    raise RuntimeError(
                        "Git initialization completed without creating '.git'."
                    )

            # ---------------------------------------------------------
            # 4. Commit prepared repository
            # ---------------------------------------------------------

            shutil.move(
                str(staging_mig),
                str(mig_dir),
            )
            committed_paths.append(mig_dir)

            if not git_already_initialized:
                shutil.move(
                    str(staging_git),
                    str(git_dir),
                )
                committed_paths.append(git_dir)

    except Exception:
        for created in reversed(committed_paths):
            if created.is_dir():
                shutil.rmtree(created, ignore_errors=True)

            elif created.exists():
                created.unlink(missing_ok=True)

        if created_root and path.exists():
            try:
                path.rmdir()
            except OSError:
                pass

        raise
