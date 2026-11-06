import configparser
import importlib
import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from mig.mig_exceptions import NonEmptyDirectoryInitError


init_module = importlib.import_module("commands.init")


# -------------------------------------------------------------------
# Helpers and fixtures
# -------------------------------------------------------------------


def create_git_metadata(directory: Path) -> None:
    """Create ordinary Git metadata for filesystem-level unit tests."""
    git_dir = directory / ".git"
    git_dir.mkdir()

    (git_dir / "HEAD").write_text(
        "ref: refs/heads/main\n",
        encoding="utf-8",
    )
    (git_dir / "config").write_text(
        "[core]\n"
        "\trepositoryformatversion = 0\n"
        "\tbare = false\n",
        encoding="utf-8",
    )


def assert_metadata(directory: Path, workflow: str = "kanban") -> None:
    mig_dir = directory / ".mig"

    assert mig_dir.is_dir()

    config = configparser.ConfigParser()
    loaded = config.read(mig_dir / "config", encoding="utf-8")

    assert loaded
    assert config["repository"]["workflow"] == workflow

    raw_json = (mig_dir / "workflow.json").read_text(encoding="utf-8")

    assert json.loads(raw_json) == {
        "workflow": workflow,
        "issues": [],
    }
    assert raw_json.endswith("\n")


def snapshot(directory: Path) -> dict[str, bytes | None]:
    """Record regular files and directories for preservation assertions."""
    return {
        str(entry.relative_to(directory)): (
            None if entry.is_dir() else entry.read_bytes()
        )
        for entry in directory.rglob("*")
    }


def assert_no_staging(parent: Path) -> None:
    assert list(parent.glob("mig-init-*")) == []


@pytest.fixture(autouse=True)
def git_init_mock(monkeypatch):
    """Prevent real Git initialization in these unit tests."""
    mock = Mock(side_effect=create_git_metadata)
    monkeypatch.setattr(
        init_module,
        "initialize_git_repository",
        mock,
    )
    return mock


@pytest.fixture(autouse=True)
def stage_mock(monkeypatch):
    """Prevent real Git staging in these unit tests."""
    mock = Mock()
    monkeypatch.setattr(init_module, "stage_files", mock)
    return mock


@pytest.fixture
def existing_git_repo(tmp_path):
    target = tmp_path / "repo"
    target.mkdir()
    create_git_metadata(target)

    (target / "notes.txt").write_text(
        "Existing user content\n",
        encoding="utf-8",
    )
    return target


# -------------------------------------------------------------------
# Successful initialization
# -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("workflow", "expected"),
    [
        ("kanban", "kanban"),
        ("SCRUM", "scrum"),
        ("Waterfall", "waterfall"),
        ("custom", "custom"),
    ],
)
def test_initialize_missing_directory(
    tmp_path,
    git_init_mock,
    stage_mock,
    workflow,
    expected,
):
    target = tmp_path / "repo"

    result = init_module.init_repo(target, workflow)

    assert_metadata(target, expected)
    assert (target / ".git" / "HEAD").is_file()
    assert (target / ".git" / "config").is_file()

    assert result.directory == target.resolve()
    assert result.metadata_staged is False
    assert result.staging_error is None

    git_init_mock.assert_called_once()
    stage_mock.assert_not_called()
    assert_no_staging(tmp_path)


def test_initialize_nested_missing_directory(tmp_path):
    target = tmp_path / "parent" / "child" / "repo"

    result = init_module.init_repo(target, "kanban")

    assert_metadata(target)
    assert result.directory == target.resolve()
    assert_no_staging(target.parent)


def test_initialize_relative_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = init_module.init_repo("repo", "kanban")

    assert result.directory == tmp_path / "repo"
    assert_metadata(result.directory)


@pytest.mark.skipif(
    os.name == "nt",
    reason="This implementation rejects existing empty targets on Windows.",
)
def test_initialize_existing_empty_directory(tmp_path):
    target = tmp_path / "repo"
    target.mkdir()

    result = init_module.init_repo(target, "kanban")

    assert_metadata(target)
    assert (target / ".git").is_dir()
    assert result.staging_error is None
    assert_no_staging(tmp_path)


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows-specific restriction.",
)
def test_windows_rejects_existing_empty_directory(tmp_path):
    target = tmp_path / "repo"
    target.mkdir()

    with pytest.raises(RuntimeError, match="Windows"):
        init_module.init_repo(target, "kanban")

    assert target.is_dir()
    assert list(target.iterdir()) == []
    assert_no_staging(tmp_path)


def test_existing_git_is_preserved(
    existing_git_repo,
    git_init_mock,
    stage_mock,
):
    target = existing_git_repo
    before = snapshot(target)

    result = init_module.init_repo(target, "scrum", force=True)

    assert_metadata(target, "scrum")

    after = snapshot(target)
    for name, content in before.items():
        assert after[name] == content

    assert result.metadata_staged is False
    git_init_mock.assert_not_called()
    stage_mock.assert_not_called()
    assert_no_staging(target.parent)


# -------------------------------------------------------------------
# Validation and rejected targets
# -------------------------------------------------------------------


def test_invalid_workflow_does_not_create_directories(
    tmp_path,
    git_init_mock,
    stage_mock,
):
    target = tmp_path / "missing-parent" / "repo"

    with pytest.raises(ValueError, match="Unsupported workflow"):
        init_module.init_repo(target, "invalid")

    assert not target.parent.exists()
    git_init_mock.assert_not_called()
    stage_mock.assert_not_called()


def test_target_file_is_preserved(tmp_path):
    target = tmp_path / "repo"
    target.write_text("Keep me", encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        init_module.init_repo(target, "kanban")

    assert target.read_text(encoding="utf-8") == "Keep me"
    assert_no_staging(tmp_path)


@pytest.mark.parametrize("force", [False, True])
def test_existing_mig_is_never_overwritten(tmp_path, force):
    target = tmp_path / "repo"
    mig_dir = target / ".mig"
    mig_dir.mkdir(parents=True)
    (mig_dir / "keep.txt").write_text("Keep me", encoding="utf-8")
    before = snapshot(target)

    with pytest.raises(FileExistsError):
        init_module.init_repo(target, "kanban", force=force)

    assert snapshot(target) == before
    assert_no_staging(tmp_path)


def test_existing_mig_file_is_rejected(tmp_path):
    target = tmp_path / "repo"
    target.mkdir()
    (target / ".mig").write_text("Keep me", encoding="utf-8")

    with pytest.raises(FileExistsError):
        init_module.init_repo(target, "kanban", force=True)

    assert (target / ".mig").read_text(encoding="utf-8") == "Keep me"


@pytest.mark.parametrize("git_entry_type", ["directory", "file"])
def test_unsupported_git_metadata_is_preserved(tmp_path, git_entry_type):
    target = tmp_path / "repo"
    target.mkdir()
    git_entry = target / ".git"

    if git_entry_type == "directory":
        git_entry.mkdir()
        (git_entry / "HEAD").write_text("incomplete", encoding="utf-8")
    else:
        git_entry.write_text("gitdir: /some/worktree", encoding="utf-8")

    before = snapshot(target)

    with pytest.raises(RuntimeError):
        init_module.init_repo(target, "kanban", force=True)

    assert snapshot(target) == before


@pytest.mark.parametrize("force", [False, True])
def test_nonempty_target_without_git_is_preserved(tmp_path, force):
    target = tmp_path / "repo"
    target.mkdir()
    (target / "notes.txt").write_text("Keep me", encoding="utf-8")
    before = snapshot(target)

    expected_error = (
        RuntimeError if force else NonEmptyDirectoryInitError
    )

    with pytest.raises(expected_error):
        init_module.init_repo(target, "kanban", force=force)

    assert snapshot(target) == before
    assert_no_staging(tmp_path)


def test_existing_git_requires_force(existing_git_repo, git_init_mock):
    before = snapshot(existing_git_repo)

    with pytest.raises(NonEmptyDirectoryInitError):
        init_module.init_repo(existing_git_repo, "kanban")

    assert snapshot(existing_git_repo) == before
    git_init_mock.assert_not_called()


# -------------------------------------------------------------------
# Preparation and publication failures
# -------------------------------------------------------------------


@pytest.mark.parametrize("existing_target", [False, True])
def test_git_failure_leaves_target_unchanged(
    tmp_path,
    git_init_mock,
    stage_mock,
    existing_target,
):
    target = tmp_path / "repo"
    if existing_target:
        target.mkdir()

    def fail_after_partial_git_init(directory):
        create_git_metadata(directory)
        raise RuntimeError("Injected Git failure")

    git_init_mock.side_effect = fail_after_partial_git_init

    with pytest.raises(RuntimeError, match="Injected Git failure"):
        init_module.init_repo(target, "kanban", stage=True)

    if existing_target:
        assert target.is_dir()
        assert list(target.iterdir()) == []
    else:
        assert not target.exists()

    stage_mock.assert_not_called()
    assert_no_staging(tmp_path)


@pytest.mark.parametrize("existing_git", [False, True])
def test_metadata_write_failure_preserves_target(
    tmp_path,
    monkeypatch,
    stage_mock,
    existing_git,
):
    target = tmp_path / "repo"

    if existing_git:
        target.mkdir()
        create_git_metadata(target)

    before = snapshot(target) if existing_git else None

    def fail_after_partial_write(mig_dir, workflow):
        mig_dir.mkdir()
        (mig_dir / "config").write_text("partial", encoding="utf-8")
        raise OSError("Injected write failure")

    monkeypatch.setattr(
        init_module,
        "_write_initial_metadata",
        fail_after_partial_write,
    )

    with pytest.raises(OSError, match="Injected write failure"):
        init_module.init_repo(
            target,
            "kanban",
            force=existing_git,
            stage=True,
        )

    if existing_git:
        assert snapshot(target) == before
    else:
        assert not target.exists()

    stage_mock.assert_not_called()
    assert_no_staging(tmp_path)


@pytest.mark.parametrize("existing_git", [False, True])
def test_rename_failure_preserves_target(
    tmp_path,
    monkeypatch,
    stage_mock,
    existing_git,
):
    target = tmp_path / "repo"

    if existing_git:
        target.mkdir()
        create_git_metadata(target)

    before = snapshot(target) if existing_git else None

    def failing_rename(source, destination):
        raise OSError("Injected rename failure")

    monkeypatch.setattr(init_module.os, "rename", failing_rename)

    with pytest.raises(OSError, match="Injected rename failure"):
        init_module.init_repo(
            target,
            "kanban",
            force=existing_git,
            stage=True,
        )

    if existing_git:
        assert snapshot(target) == before
    else:
        assert not target.exists()

    stage_mock.assert_not_called()
    assert_no_staging(tmp_path)


# -------------------------------------------------------------------
# Atomic publication boundaries
# -------------------------------------------------------------------


def test_new_repository_is_published_in_one_rename(tmp_path, monkeypatch):
    target = tmp_path / "repo"
    real_rename = os.rename
    publications = []

    def checked_rename(source, destination):
        source = Path(source)
        destination = Path(destination)

        assert destination == target
        assert not target.exists()

        # Everything is prepared before publication.
        assert_metadata(source)
        assert (source / ".git" / "HEAD").is_file()

        real_rename(source, destination)
        publications.append(destination)

        # Both directories are present after the same operation.
        assert_metadata(target)
        assert (target / ".git" / "HEAD").is_file()

    monkeypatch.setattr(init_module.os, "rename", checked_rename)

    init_module.init_repo(target, "kanban")

    assert publications == [target]
    assert_no_staging(tmp_path)


def test_existing_git_publishes_only_mig(
    existing_git_repo,
    monkeypatch,
    git_init_mock,
):
    target = existing_git_repo
    git_before = snapshot(target / ".git")
    real_rename = os.rename
    publications = []

    def checked_rename(source, destination):
        source = Path(source)
        destination = Path(destination)

        assert destination == target / ".mig"
        assert not destination.exists()
        assert source.name == ".mig"
        assert (source / "config").is_file()
        assert (source / "workflow.json").is_file()

        real_rename(source, destination)
        publications.append(destination)

    monkeypatch.setattr(init_module.os, "rename", checked_rename)

    init_module.init_repo(target, "kanban", force=True)

    assert publications == [target / ".mig"]
    assert_metadata(target)
    assert snapshot(target / ".git") == git_before
    git_init_mock.assert_not_called()


# -------------------------------------------------------------------
# Optional metadata staging
# -------------------------------------------------------------------


def test_staging_is_disabled_by_default(tmp_path, stage_mock):
    target = tmp_path / "repo"

    result = init_module.init_repo(target, "kanban")

    stage_mock.assert_not_called()
    assert result.metadata_staged is False
    assert result.staging_error is None


@pytest.mark.parametrize("existing_git", [False, True])
def test_stage_runs_after_publication(
    tmp_path,
    stage_mock,
    existing_git,
):
    target = tmp_path / "repo"

    if existing_git:
        target.mkdir()
        create_git_metadata(target)

    def verify_published_repository(repository, paths):
        assert repository == target
        assert_metadata(repository)
        assert (repository / ".git" / "HEAD").is_file()
        assert tuple(paths) == (
            ".mig/config",
            ".mig/workflow.json",
        )

    stage_mock.side_effect = verify_published_repository

    result = init_module.init_repo(
        target,
        "kanban",
        force=existing_git,
        stage=True,
    )

    stage_mock.assert_called_once()
    assert result.metadata_staged is True
    assert result.staging_error is None
    assert_no_staging(tmp_path)


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("Git index is locked"),
        OSError("Unable to execute Git"),
    ],
)
def test_staging_failure_does_not_undo_initialization(
    tmp_path,
    stage_mock,
    error,
):
    target = tmp_path / "repo"
    stage_mock.side_effect = error

    result = init_module.init_repo(target, "kanban", stage=True)

    assert_metadata(target)
    assert (target / ".git" / "HEAD").is_file()

    assert result.directory == target
    assert result.metadata_staged is False
    assert result.staging_error == str(error)

    stage_mock.assert_called_once()
    assert_no_staging(tmp_path)


def test_unexpected_staging_error_propagates_without_rollback(
    tmp_path,
    stage_mock,
):
    target = tmp_path / "repo"
    stage_mock.side_effect = TypeError("Programming error")

    with pytest.raises(TypeError, match="Programming error"):
        init_module.init_repo(target, "kanban", stage=True)

    # Initialization already succeeded before staging began.
    assert_metadata(target)
    assert (target / ".git").is_dir()
    assert_no_staging(tmp_path)
