#!/usr/bin/env python3

import argparse
import logging
import sys
from pathlib import Path
import yaml
from jinja2 import Environment, FileSystemLoader, exceptions
import copy
import json

from logs import logger, green, yellow, red

# --- Configuration ---
DEFAULT_TEMPLATE_SUFFIX = ".j2"


# --- Helper Functions ---
def deep_merge(target: dict, source: dict) -> dict:
    """
    Recursively merges source dictionary into target dictionary.
    If keys conflict, the value from the source dictionary takes precedence.
    Handles nested dictionaries. Modifies target in place.
    """
    for key, value in source.items():
        if isinstance(value, dict):
            # Get node or create one
            node = target.setdefault(key, {})
            if isinstance(node, dict):
                # Recurse for nested dictionaries
                deep_merge(node, value)
            else:
                # If target's value for the key isn't a dict, overwrite it
                # This handles cases where structure differs (e.g., dict overwriting a string)
                target[key] = copy.deepcopy(
                    value
                )  # Use deepcopy for nested dicts from source
        else:
            # Overwrite value in target with value from source
            target[key] = value  # Simple assignment works for non-dict values
    return target


# --- Core Functions ---
def load_and_merge_data(data_file_paths: list[Path]) -> dict:
    """Loads data from multiple YAML files and merges them. Last file wins."""
    merged_data = {}
    logger.info(
        f"Loading and merging data from files (in order): {[str(p) for p in data_file_paths]}"
    )

    for data_file_path in data_file_paths:
        logger.info(f"Attempting to load data from: {data_file_path}")
        if not data_file_path.is_file():
            logger.error(f"Data file not found: {data_file_path}")
            raise FileNotFoundError(f"Data file not found: {data_file_path}")

        try:
            with open(data_file_path, "r") as f:
                # Use safe_load which is recommended over load
                current_data = yaml.safe_load(f)

                # Handle empty YAML files gracefully (safe_load returns None)
                if current_data is None:
                    logger.warning(
                        yellow(f"Data file is empty, skipping merge: {data_file_path}")
                    )
                    continue  # Skip to the next file

                # Ensure the loaded data is a dictionary for merging
                if not isinstance(current_data, dict):
                    logger.error(
                        red(
                            f"Data file content is not a valid YAML dictionary (key-value map): {data_file_path}"
                        )
                    )
                    raise ValueError(
                        f"YAML content in {data_file_path} must be a dictionary"
                    )

                logger.debug(
                    f"Successfully loaded data from {data_file_path}, performing deep merge..."
                )
                # Perform the deep merge - modifies merged_data in place
                deep_merge(merged_data, current_data)
                logger.debug(f"Merge completed for {data_file_path}")

        except yaml.YAMLError as e:
            logger.error(
                red(
                    f"Error parsing YAML data file {data_file_path}: {e}", exc_info=True
                )
            )
            raise ValueError(f"Invalid YAML format in {data_file_path}") from e
        except IOError as e:
            logger.error(
                red(f"Error reading data file {data_file_path}: {e}", exc_info=True)
            )
            raise IOError(f"Could not read data file {data_file_path}") from e
        except Exception as e:
            logger.error(
                red(f"An unexpected error occurred loading {data_file_path}: {e}"),
                exc_info=True,
            )
            raise  # Re-raise unexpected errors

    logger.info(green("Finished loading and merging all data files."))
    # Optionally log the final merged data structure at DEBUG level for verification
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Final merged data:\n{json.dumps(merged_data, indent=2)}")
    return merged_data


def process_templates(input_dir: Path, output_dir: Path, template_data: dict):
    """Finds, renders, and writes Jinja templates."""
    logger.info(f"Starting template processing...")
    logger.info(f"Input directory: {input_dir.resolve()}")
    logger.info(f"Output directory: {output_dir.resolve()}")

    # --- Input Validation ---
    if not input_dir.is_dir():
        logger.error(
            red(f"Input directory does not exist or is not a directory: {input_dir}")
        )
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    # --- Prepare Output Directory ---
    try:
        logger.debug(f"Ensuring output directory exists: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory ensured: {output_dir}")
    except OSError as e:
        logger.error(
            red(f"Could not create output directory {output_dir}: {e}"), exc_info=True
        )
        raise OSError(f"Failed to create output directory {output_dir}") from e

    # --- Setup Jinja Environment ---
    # Use FileSystemLoader pointing to the input directory
    env = Environment(
        loader=FileSystemLoader(str(input_dir)),
        trim_blocks=True,  # Good practice for Terraform files
        lstrip_blocks=True,  # Good practice for Terraform files
        keep_trailing_newline=True,  # Often desired for config files
    )
    logger.debug("Jinja2 Environment initialized.")

    # --- Find and Process Templates ---
    template_files_found = 0
    templates_processed_successfully = 0
    templates_skipped = 0

    # Iterate through files matching the suffix in the input directory
    for template_path in input_dir.glob(f"**/*{DEFAULT_TEMPLATE_SUFFIX}"):
        if template_path.is_file():
            template_files_found += 1
            relative_path = template_path.relative_to(input_dir)
            output_filename = relative_path.with_suffix("")  # Remove the suffix
            output_path = output_dir / output_filename

            logger.info(
                f"Processing template: {relative_path} -> {output_path.relative_to(output_dir)}"
            )

            # Ensure subdirectory exists in output
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.error(
                    red(
                        f"Could not create subdirectory {output_path.parent} for {output_filename}: {e}"
                    ),
                    exc_info=True,
                )
                continue  # Skip this file

            try:
                # Load template using its path relative to the input_dir
                template = env.get_template(str(relative_path))

                # Render the template with the provided data
                rendered_content = template.render(template_data)

                if not rendered_content.strip():
                    logger.warning(
                        yellow(
                            f"Rendered content for {relative_path} is empty. Skipping file."
                        )
                    )
                    templates_skipped += 1
                    continue

                # Write the rendered content to the output file
                with open(output_path, "w") as f_out:
                    f_out.write(rendered_content)

                logger.debug(f"Successfully rendered and wrote {output_path}")
                templates_processed_successfully += 1

            except exceptions.TemplateNotFound:
                logger.error(
                    red(
                        f"Template not found by Jinja (check path/permissions): {relative_path}"
                    )
                )
            except exceptions.TemplateSyntaxError as e:
                logger.error(
                    red(
                        f"Syntax error in template {relative_path} at line {e.lineno}: {e.message}"
                    ),
                    exc_info=True,
                )
            except exceptions.UndefinedError as e:
                logger.error(
                    red(
                        f"Undefined variable used in template {relative_path}: {e.message}"
                    ),
                    exc_info=True,
                )
            except IOError as e:
                logger.error(
                    red(
                        f"Could not write output file {output_path}: {e}", exc_info=True
                    )
                )
            except (
                Exception
            ) as e:  # Catch any other unexpected errors during rendering/writing
                logger.error(
                    red(
                        f"An unexpected error occurred processing {relative_path}: {e}"
                    ),
                    exc_info=True,
                )

    logger.info(
        green(
            f"Template processing finished. Found {template_files_found} files matching '*{DEFAULT_TEMPLATE_SUFFIX}'."
        )
    )
    if template_files_found > 0:
        logger.info(
            green(
                f"Successfully processed {templates_processed_successfully} templates."
            )
        )
        logger.info(green(f"Skipped {templates_skipped} templates."))
        if (
            templates_processed_successfully + templates_skipped
        ) < template_files_found:
            logger.warning(yellow(
                f"{template_files_found - templates_processed_successfully} templates failed to process."
            ))
    else:
        logger.warning(
            yellow(
                f"No template files matching '*{DEFAULT_TEMPLATE_SUFFIX}' found in {input_dir}."
            )
        )


def process_non_template_files(input_dir: Path, output_dir: Path):
    """Finds and copy other files."""
    logger.info(f"Starting copying non-template files ...")
    logger.info(f"Input directory: {input_dir.resolve()}")
    logger.info(f"Output directory: {output_dir.resolve()}")

    # --- Input Validation ---
    if not input_dir.is_dir():
        logger.error(
            red(f"Input directory does not exist or is not a directory: {input_dir}")
        )
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    # --- Prepare Output Directory ---
    try:
        logger.debug(f"Ensuring output directory exists: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory ensured: {output_dir}")
    except OSError as e:
        logger.error(
            red(f"Could not create output directory {output_dir}: {e}"), exc_info=True
        )
        raise OSError(f"Failed to create output directory {output_dir}") from e

    # --- Find and Copy Non-template Files ---
    files_found = 0
    files_copied = 0

    non_template_files = set(input_dir.glob("**/*")) - set(
        input_dir.glob(f"**/*{DEFAULT_TEMPLATE_SUFFIX}")
    )

    # Iterate through non-template files
    for file_path in non_template_files:
        if file_path.is_file():
            files_found += 1
            relative_path = file_path.relative_to(input_dir)
            output_path = output_dir / relative_path

            logger.info(
                f"Copying file: {relative_path} -> {output_path.relative_to(output_dir)}"
            )

            # Ensure subdirectory exists in output
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.error(
                    red(
                        f"Could not create subdirectory {output_path.parent} for {relative_path}: {e}"
                    ),
                    exc_info=True,
                )
                continue

            try:
                # Copy the file to the output directory
                with open(file_path, "rb") as f_in, open(output_path, "wb") as f_out:
                    f_out.write(f_in.read())

                logger.debug(f"Successfully copied {output_path}")
                files_copied += 1
            except IOError as e:
                logger.error(
                    red(f"Could not copy file {file_path} to {output_path}: {e}"),
                    exc_info=True,
                )
            except Exception as e:  # Catch any other unexpected errors during copying
                logger.error(
                    red(f"An unexpected error occurred copying {file_path}: {e}"),
                    exc_info=True,
                )

    logger.info(
        green(
            f"File copying finished. Found {files_found} files not matching '*{DEFAULT_TEMPLATE_SUFFIX}'."
        )
    )
    if files_found > 0:
        logger.info(green(f"Successfully copied {files_copied} files."))
        if files_copied < files_found:
            logger.warning(f"{files_found - files_copied} files failed to copy.")
    else:
        logger.warning(yellow(f"No non-template files found in {input_dir}."))
