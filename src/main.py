#!/usr/bin/env python3

import logging
import argparse
import shutil
import sys
from pathlib import Path

from logs import logger, setLoggingLevel, green, yellow, red, greenBack
from processing import load_and_merge_data, process_files
from git import clone_repository


# --- Configuration ---
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
LOG_LEVEL = logging.INFO

BANNER_ART = r"""

██╗███╗   ██╗     ██╗███████╗ ██████╗████████╗ ██████╗
██║████╗  ██║     ██║██╔════╝██╔════╝╚══██╔══╝██╔═══██╗
██║██╔██╗ ██║     ██║█████╗  ██║        ██║   ██║   ██║
██║██║╚██╗██║██   ██║██╔══╝  ██║        ██║   ██║   ██║
██║██║ ╚████║╚█████╔╝███████╗╚██████╗   ██║   ╚██████╔╝
╚═╝╚═╝  ╚═══╝ ╚════╝ ╚══════╝ ╚═════╝   ╚═╝    ╚═════╝

                                      __          ___           ____           _____
                                     / /  __ __  / _ \___ _  __/ __ \___  ___ / ___/______  __ _____
                                    / _ \/ // / / // / -_) |/ / /_/ / _ \(_-</ (_ / __/ _ \/ // / _ \
                                   /_.__/\_, / /____/\__/|___/\____/ .__/___/\___/_/  \___/\_,_/ .__/
                                        /___/                     /_/                         /_/

"""

def display_banner():
    """Prints the ASCII art banner."""
    print(BANNER_ART)
    print("-" * 105)

def print_section_header(title):
    """Prints a formatted section header."""
    print("=" * 105)
    print(f"=> {title.upper()}")
    print("=" * 105)

def cleanup_temp_files(temp_path):
    """Cleans up the temporary directory used for Git clones."""
    if temp_path.exists() and temp_path.is_dir():
        try:
            shutil.rmtree(temp_path)
            logger.info(green("Temporary files cleaned up successfully."))
        except Exception as e:
            logger.error(red(f"Error cleaning up temporary files: {e}"))
    else:
        logger.info(yellow("No temporary files to clean up."))


def main():
    """Main function to parse arguments and run the application."""
    display_banner()
    parser = argparse.ArgumentParser(
        description="Replaces values in files based on '# @param' comments and YAML data files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-s", "--source",
        type=str,
        choices=["local", "git"],
        default="local",
        help="Source of the files to process.",
    )
    parser.add_argument(
        "-r", "--repo-url",
        type=str,
        help="Git repository URL in HTTPS format (required if source is 'git').",
    )
    parser.add_argument(
        "-b", "--branch",
        type=str,
        help="Branch to clone from the repository (defaults to the default branch).",
    )
    parser.add_argument(
        "-i", "--input-dir",
        type=Path,
        help="Directory containing the files to process. Not required for API mode.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        help="Directory where processed files will be saved. Defaults to the input directory for in-place editing.",
    )
    parser.add_argument(
        "-d", "--data-files",
        type=Path,
        nargs='+',
        metavar='DATA_FILE',
        help="One or more paths to YAML data files. Values from later files override earlier ones. Not required for API mode."
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    parser.add_argument(
        "--api",
        action="store_true",
        help="Run as API server instead of CLI processing."
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="API server host (only used with --api)."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="API server port (only used with --api)."
    )

    args = parser.parse_args()

    # Handle API mode
    if args.api:
        from api import run_api_server
        log_level = logging.DEBUG if args.debug else LOG_LEVEL
        setLoggingLevel(log_level)
        run_api_server(host=args.host, port=args.port, debug=args.debug)
        return

    # Validate required arguments for CLI mode
    if not args.input_dir:
        parser.error("--input-dir is required for CLI mode")
    if not args.data_files:
        parser.error("--data-files is required for CLI mode")

    # If output directory is not specified, use the input directory for in-place editing
    if not args.output_dir:
        args.output_dir = args.input_dir
        logger.warning(yellow("Output directory not specified. Will perform edits in-place."))

    if args.source == "git" and not args.repo_url:
        parser.error("When using 'git' as source, --repo-url is required.")

    if args.input_dir == args.output_dir and args.source == "git":
        parser.error("In-place editing (when --output-dir is the same as --input-dir) is not allowed when source is 'git' to prevent modifying the temporary clone.")

    log_level = logging.DEBUG if args.debug else LOG_LEVEL
    setLoggingLevel(log_level)

    print(f"  Source: {args.source}")
    if args.source == "git":
        print(f"  Repository URL: {args.repo_url}")
        if args.branch:
            print(f"  Branch: {args.branch}")
    print(f"  Input directory: {args.input_dir}")
    print(f"  Output directory: {args.output_dir}")
    print("  Data files:")
    for file in args.data_files:
        print(f"    - {file}")
    print(f"  Debug mode: {'Enabled' if args.debug else 'Disabled'}")
    print("-" * 105)

    temp_clone_path = Path("temp/")

    try:
        if args.source == "git":
            print_section_header("Cloning Git Repository")
            clone_repository(
                repo_url=args.repo_url,
                clone_path=str(temp_clone_path),
                branch=args.branch
            )
            # The input dir is relative to the cloned repo
            input_dir = temp_clone_path / args.input_dir
        else:
            input_dir = args.input_dir

        # 1. Load and Merge Data
        print_section_header("Data files merging")
        values_data = load_and_merge_data(args.data_files)

        # 2. Process Files
        print_section_header("File processing")
        process_files(input_dir, args.output_dir, values_data)

        logger.info(greenBack("Processing finished successfully."))
        sys.exit(0)

    except (FileNotFoundError, ValueError, OSError, Exception) as e:
        logger.critical(red(f"Script terminated due to an error: {e}"), exc_info=True)
        sys.exit(1)

    finally:
        # Cleanup temporary files if they were created from a git source
        if args.source == "git":
            print_section_header("Cleaning up temporary files")
            cleanup_temp_files(temp_clone_path)


if __name__ == "__main__":
    main()
