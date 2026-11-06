from pathlib import Path

from utils.path_checks import path_entry_exists



SUPPORTED_WORKFLOWS = frozenset({
    "kanban",
    "scrum",
    "waterfall",
    "custom",
})



SHARED_METADATA_PATHS = (
    ".mig/config",
    ".mig/workflow.json",
)





def validate_workflow(workflow: str) -> str:
    normalized = workflow.lower()

    if normalized not in SUPPORTED_WORKFLOWS:
        expected = ", ".join(sorted(SUPPORTED_WORKFLOWS))
        raise ValueError(
            f"Unsupported workflow '{normalized}'. "
            f"Expected one of: {expected}."
        )

    return normalized



def is_mig_repository(path: Path) -> bool:
    mig_dir = path / ".mig"

    return (
        mig_dir.is_dir()
        and (mig_dir / "config").is_file()
        and (mig_dir / "workflow.json").is_file()
    )



def require_mig_repository(path: Path) -> None:
    if not is_mig_repository(path):
        raise RuntimeError(
            f"'{path}' does not contain the expected MIG repository metadata."
        )



def require_mig_not_initialized(path: Path) -> None:
    if path_entry_exists(path / ".mig"):
        raise FileExistsError(
            f"'{path}' already contains a '.mig' entry."
        )
