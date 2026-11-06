import argparse

from utils.logger import log_success, log_fail, log_warning, log_info
from commands.init import init_repo
from mig.mig_exceptions import NonEmptyDirectoryInitError



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mig",
        description="Management Integrated Git CLI",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a new MIG repository.",
    )

    init_parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to initialize; defaults to the current directory.",
    )

    init_parser.add_argument(
        "--workflow",
        type=str.lower,
        choices=["kanban", "waterfall", "scrum", "custom"],
        default="kanban",
        help="Workflow to use; defaults to kanban.",
    )

    init_parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Allow initialization in a non-empty existing Git repository. "
            "Existing MIG metadata is never overwritten."
        ),
    )

    init_parser.add_argument(
        "--stage",
        action="store_true",
        help="Stage shared MIG metadata after initialization; do not commit.",
    )

    clone_parser = subparsers.add_parser(
        "clone",
        help="Clone an existing MIG-enabled repository.",
    )

    clone_parser.add_argument(
        "repository",
        help="Repository URL or path to clone.",
    )

    return parser



def handle_init(args: argparse.Namespace) -> int:
    log_info(
        f"Initializing MIG repository with workflow '{args.workflow}' "
        f"in '{args.directory}'."
    )

    try:
        result = init_repo(
            directory=args.directory,
            workflow=args.workflow,
            force=args.force,
            stage=args.stage,
        )

    except NonEmptyDirectoryInitError as exc:
        log_warning(str(exc))
        return 1

    except OSError as exc:
        log_fail(f"Filesystem error: {exc}")
        return 1

    except (ValueError, RuntimeError) as exc:
        log_fail(str(exc))
        return 1

    log_success(
        f"Initialized MIG repository with workflow '{args.workflow}' "
        f"in '{result.directory}'."
    )

    if result.staging_error is not None:
        log_warning(
            "MIG initialization succeeded, but metadata staging failed: "
            f"{result.staging_error}"
        )
        log_info(
            "From the repository root, run:\n"
            "  git add -- .mig/config .mig/workflow.json"
        )

        # Initialization succeeded, but the requested --stage step failed.
        return 1

    if result.metadata_staged:
        log_success("Shared MIG metadata staged. No commit was created.")

    return 0



def handle_clone(args: argparse.Namespace) -> int:
    log_warning(
        f"Cloning '{args.repository}' is not implemented yet."
    )
    return 1



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    match args.command:
        case "init":
            exit_code = handle_init(args)

        case "clone":
            exit_code = handle_clone(args)

        case _:
            parser.error(f"Unknown command: {args.command}")

    raise SystemExit(exit_code)



if __name__ == "__main__":
    main()
