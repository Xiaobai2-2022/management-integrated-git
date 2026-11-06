from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import mig.cli as cli  # Use `import cli` if cli.py is a top-level module.
from mig.mig_exceptions import NonEmptyDirectoryInitError


@pytest.fixture
def logs(monkeypatch):
    """Capture logging calls without printing terminal output."""
    captured = {
        "success": [],
        "fail": [],
        "warning": [],
        "info": [],
    }

    for level, messages in captured.items():
        monkeypatch.setattr(
            cli,
            f"log_{level}",
            messages.append,
        )

    return captured


@pytest.fixture
def init_mock(monkeypatch, tmp_path):
    """Replace repository initialization with a successful stub."""
    mock = Mock(
        return_value=SimpleNamespace(
            directory=tmp_path / "repo",
            metadata_staged=False,
            staging_error=None,
        )
    )
    monkeypatch.setattr(cli, "init_repo", mock)
    return mock


def make_init_args(
    directory: str = ".",
    workflow: str = "kanban",
    force: bool = False,
    stage: bool = False,
) -> Namespace:
    return Namespace(
        command="init",
        directory=directory,
        workflow=workflow,
        force=force,
        stage=stage,
    )


# -------------------------------------------------------------------
# Argument parsing
# -------------------------------------------------------------------


def test_init_parser_defaults():
    args = cli.build_parser().parse_args(["init"])

    assert args.command == "init"
    assert args.directory == "."
    assert args.workflow == "kanban"
    assert args.force is False
    assert args.stage is False


def test_init_parser_accepts_all_options():
    args = cli.build_parser().parse_args(
        [
            "init",
            "/tmp/example-repo",
            "--workflow",
            "SCRUM",
            "--force",
            "--stage",
        ]
    )

    assert args.command == "init"
    assert args.directory == "/tmp/example-repo"
    assert args.workflow == "scrum"
    assert args.force is True
    assert args.stage is True


@pytest.mark.parametrize(
    "workflow",
    ["kanban", "waterfall", "scrum", "custom"],
)
def test_init_parser_accepts_supported_workflows(workflow):
    args = cli.build_parser().parse_args(
        ["init", "--workflow", workflow]
    )

    assert args.workflow == workflow


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["unknown"],
        ["init", "--workflow", "invalid"],
        ["init", "--unknown-option"],
        ["clone"],
    ],
)
def test_parser_rejects_invalid_arguments(arguments):
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(arguments)

    assert exc.value.code == 2


def test_clone_parser():
    args = cli.build_parser().parse_args(
        ["clone", "https://example.com/project.git"]
    )

    assert args.command == "clone"
    assert args.repository == "https://example.com/project.git"


def test_help_exits_successfully(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["--help"])

    assert exc.value.code == 0

    output = capsys.readouterr().out
    assert "init" in output
    assert "clone" in output


# -------------------------------------------------------------------
# Initialization handler
# -------------------------------------------------------------------


def test_handle_init_passes_default_options(init_mock, logs):
    exit_code = cli.handle_init(make_init_args())

    init_mock.assert_called_once_with(
        directory=".",
        workflow="kanban",
        force=False,
        stage=False,
    )

    assert exit_code == 0
    assert len(logs["success"]) == 1
    assert logs["warning"] == []
    assert logs["fail"] == []


def test_handle_init_passes_explicit_options(init_mock, logs):
    args = make_init_args(
        directory="project",
        workflow="scrum",
        force=True,
        stage=True,
    )
    init_mock.return_value.metadata_staged = True

    exit_code = cli.handle_init(args)

    init_mock.assert_called_once_with(
        directory="project",
        workflow="scrum",
        force=True,
        stage=True,
    )

    assert exit_code == 0
    assert any("scrum" in message for message in logs["success"])
    assert any(
        "Shared MIG metadata staged" in message
        for message in logs["success"]
    )
    assert any(
        "No commit was created" in message
        for message in logs["success"]
    )


def test_handle_init_logs_resolved_directory(init_mock, logs, tmp_path):
    resolved = tmp_path / "resolved-repository"
    init_mock.return_value.directory = resolved

    cli.handle_init(make_init_args(directory="relative-repository"))

    assert any(
        str(resolved) in message
        for message in logs["success"]
    )


def test_handle_init_without_stage_does_not_claim_staging(
    init_mock, logs
):
    exit_code = cli.handle_init(make_init_args())

    assert exit_code == 0
    assert not any(
        "metadata staged" in message
        for message in logs["success"]
    )


def test_staging_failure_reports_partial_success(init_mock, logs):
    init_mock.return_value.staging_error = "Git index is locked"

    exit_code = cli.handle_init(make_init_args(stage=True))

    assert exit_code == 1

    # Initialization is still reported as successful.
    assert any(
        "Initialized MIG repository" in message
        for message in logs["success"]
    )

    assert any(
        "Git index is locked" in message
        for message in logs["warning"]
    )
    assert any(
        "git add -- .mig/config .mig/workflow.json" in message
        for message in logs["info"]
    )

    # No retry or false claim of successful staging.
    init_mock.assert_called_once()
    assert not any(
        "Shared MIG metadata staged" in message
        for message in logs["success"]
    )
    assert logs["fail"] == []


def test_nonempty_directory_logs_warning(init_mock, logs):
    init_mock.side_effect = NonEmptyDirectoryInitError(
        "Target directory is not empty."
    )

    exit_code = cli.handle_init(make_init_args())

    assert exit_code == 1
    assert logs["warning"] == ["Target directory is not empty."]
    assert logs["success"] == []
    assert logs["fail"] == []


@pytest.mark.parametrize(
    "error",
    [
        OSError("Disk error"),
        PermissionError("Permission denied"),
        FileExistsError("MIG metadata already exists"),
        NotADirectoryError("Target is a file"),
    ],
)
def test_filesystem_errors_are_reported(error, init_mock, logs):
    init_mock.side_effect = error

    exit_code = cli.handle_init(make_init_args())

    assert exit_code == 1
    assert logs["fail"] == [f"Filesystem error: {error}"]
    assert logs["success"] == []


@pytest.mark.parametrize(
    "error",
    [
        ValueError("Unsupported workflow"),
        RuntimeError("Git initialization failed"),
    ],
)
def test_expected_errors_are_reported(error, init_mock, logs):
    init_mock.side_effect = error

    exit_code = cli.handle_init(make_init_args())

    assert exit_code == 1
    assert logs["fail"] == [str(error)]
    assert logs["success"] == []


def test_unexpected_programming_errors_propagate(init_mock, logs):
    init_mock.side_effect = TypeError("Unexpected programming error")

    with pytest.raises(TypeError, match="Unexpected programming error"):
        cli.handle_init(make_init_args())

    assert logs["success"] == []


# -------------------------------------------------------------------
# Clone handler
# -------------------------------------------------------------------


def test_clone_reports_not_implemented(logs):
    args = Namespace(
        command="clone",
        repository="https://example.com/project.git",
    )

    exit_code = cli.handle_clone(args)

    assert exit_code == 1
    assert any(
        "not implemented" in message
        and args.repository in message
        for message in logs["warning"]
    )
    assert logs["success"] == []


# -------------------------------------------------------------------
# CLI entry point
# -------------------------------------------------------------------


def test_main_init_success(monkeypatch, init_mock, logs):
    monkeypatch.setattr(
        "sys.argv",
        ["mig", "init", "project", "--workflow", "SCRUM", "--force"],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 0
    init_mock.assert_called_once_with(
        directory="project",
        workflow="scrum",
        force=True,
        stage=False,
    )


def test_main_init_with_stage(monkeypatch, init_mock, logs):
    init_mock.return_value.metadata_staged = True
    monkeypatch.setattr(
        "sys.argv",
        ["mig", "init", "project", "--stage"],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 0
    assert init_mock.call_args.kwargs["stage"] is True


def test_main_initialization_failure(monkeypatch, init_mock, logs):
    init_mock.side_effect = RuntimeError("Git initialization failed")
    monkeypatch.setattr("sys.argv", ["mig", "init"])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1
    assert logs["success"] == []


def test_main_staging_failure(monkeypatch, init_mock, logs):
    init_mock.return_value.staging_error = "Git index is locked"
    monkeypatch.setattr(
        "sys.argv",
        ["mig", "init", "--stage"],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1
    assert any(
        "Initialized MIG repository" in message
        for message in logs["success"]
    )


def test_main_clone(monkeypatch, init_mock, logs):
    monkeypatch.setattr(
        "sys.argv",
        ["mig", "clone", "https://example.com/project.git"],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1
    init_mock.assert_not_called()


def test_main_invalid_arguments_do_not_initialize(
    monkeypatch, init_mock, logs
):
    monkeypatch.setattr(
        "sys.argv",
        ["mig", "init", "--workflow", "invalid"],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    init_mock.assert_not_called()
