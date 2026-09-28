from utils.logger import log_success, log_fail, log_warning, log_info

from commands.init import init_repo

from mig.mig_exceptions import NonEmptyDirectoryInitError

import argparse



def main() -> None:

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
        help="Directory to initialize, default is current working directory.",
    )

    init_parser.add_argument(
        "--workflow",
        type=str.lower,
        choices=["kanban", "waterfall", "scrum", "custom"],
        default="kanban",
        help="Initialize a new MIG repository with selected workflow.",
    )

    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Initialize a MIG repository even if the target directory is not empty.",
    )

    clone_parser = subparsers.add_parser(
        "clone",
        help="Clone an existing MIG-enabled repository.",
    )

    clone_parser.add_argument(
        "repository",
        help="Repository URL or path to clone.",
    )

    args = parser.parse_args()

    match args.command:

        case "init":

            log_info(
                f"Initializing MIG repository with workflow: '{args.workflow}' in directory: '{args.directory}'"
            )

            if args.force:
                log_warning(f"Proceeding regardless if the target directory is empty: '{args.directory}'")

            try:

                init_repo(directory=args.directory, workflow=args.workflow, force=args.force)

                log_success(f"Successfully initialized MIG repository with workflow: {args.workflow}")

            except NonEmptyDirectoryInitError as e:
                log_warning(f"{e}")

            except OSError as e:
                log_fail(f"Filesystem error: {e}")

            except Exception as e:
                log_fail(f"{e}")

        case "clone":
            log_info(
                f"Cloning new MIG repository: {args.repository}"
            )

        case _:
            log_fail("Unknown command")
