#!/usr/bin/env python3

import logging
from pathlib import Path
import yaml
import json
import re
import copy
import shutil

from logs import logger, green, yellow, red

# --- Helper Functions ---

def deep_merge(target: dict, source: dict) -> dict:
    """
    Recursively merges the source dictionary into the target dictionary.
    Modifies the target dictionary in place.
    """
    for key, value in source.items():
        if isinstance(value, dict):
            node = target.setdefault(key, {})
            if isinstance(node, dict):
                deep_merge(node, value)
            else:
                target[key] = copy.deepcopy(value)
        else:
            target[key] = value
    return target

def get_value_by_path(data: dict, path: str):
    """
    Navigates a nested dictionary using a dot-separated path (e.g., 'eks.name').
    Returns the value or None if the path is not found.
    """
    keys = path.split('.')
    value = data
    try:
        for key in keys:
            value = value[key]
        return value
    except (KeyError, TypeError, AttributeError):
        logger.warning(yellow(f"Path '{path}' not found in the data values."))
        return None

def format_value_for_file(value):
    """
    Formats a Python value into a string suitable for writing to a config file.
    - Strings are wrapped in double quotes.
    - Booleans are converted to lowercase 'true'/'false'.
    - Lists and dicts are converted to JSON format with double quotes.
    - Numbers and other types are converted to their string representation.
    """
    if isinstance(value, str):
        # Avoid double-quoting if already quoted
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            return value
        return f'"{value}"'
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value)

# --- Core Functions ---

def load_and_merge_data(data_file_paths: list[Path]) -> dict:
    """
    Loads data from one or more YAML files and merges them.
    Values from later files in the list will override earlier ones.
    """
    merged_data = {}
    logger.info(f"Loading and merging data from files: {[str(p) for p in data_file_paths]}")

    for data_file_path in data_file_paths:
        if not data_file_path.is_file():
            raise FileNotFoundError(f"Data file not found: {data_file_path}")
        try:
            with open(data_file_path, "r", encoding='utf-8') as f:
                current_data = yaml.safe_load(f)
                if current_data:
                    if not isinstance(current_data, dict):
                        raise ValueError(f"YAML content in {data_file_path} must be a dictionary.")
                    deep_merge(merged_data, current_data)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML format in {data_file_path}") from e

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Final merged data:\n{json.dumps(merged_data, indent=2)}")
    return merged_data

def process_files(input_dir: Path, output_dir: Path, data: dict):
    """
    Processes all files in the input directory, performs replacements based on
    '@section' and '@param' comments, and saves results to the output directory.
    """
    logger.info("Starting file processing...")
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    if input_dir != output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    total_files_modified = 0
    total_replacements = 0
    total_section_toggles = 0

    for file_path in input_dir.rglob("*"):
        if not file_path.is_file():
            continue

        relative_path = file_path.relative_to(input_dir)
        output_path = output_dir / relative_path

        if input_dir != output_dir:
            output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Processing file: {relative_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            file_was_modified = False

            # --- Pass 1: Handle @section commenting/uncommenting ---
            section_modified_lines = list(lines)
            active_sections = []  # Stack for handling nested sections

            for i, line in enumerate(lines):
                section_begin_match = re.search(r'#\s*@section\s+([\w.-]+)\s+begin', line)
                section_end_match = re.search(r'#\s*@section\s+([\w.-]+)\s+end', line)
                is_marker_line = section_begin_match or section_end_match

                # Apply transformation based on the current section state
                if active_sections and not is_marker_line:
                    section_to_apply = active_sections[-1]
                    should_be_commented = section_to_apply['should_be_commented']
                    is_commented = line.lstrip().startswith('#')
                    is_blank = not line.strip()

                    if should_be_commented and not is_commented and not is_blank:
                        indent = re.match(r'^(\s*)', line).group(1)
                        section_modified_lines[i] = f"{indent}# {line.lstrip()}"
                        if section_modified_lines[i] != line:
                            file_was_modified = True
                            total_section_toggles += 1
                    elif not should_be_commented and is_commented:
                        uncommented_line = re.sub(r'#\s?', '', line, 1).lstrip()
                        if not uncommented_line.startswith('@param') and not uncommented_line.startswith('@section'):
                            section_modified_lines[i] = re.sub(r'#\s?', '', line, 1)
                            if section_modified_lines[i] != line:
                                file_was_modified = True
                                total_section_toggles += 1

                if section_begin_match:
                    yaml_path = section_begin_match.group(1)
                    value = get_value_by_path(data, yaml_path)
                    active_sections.append({'key': yaml_path, 'should_be_commented': value is False})
                elif section_end_match:
                    if active_sections and active_sections[-1]['key'] == section_end_match.group(1):
                        active_sections.pop()
                    else:
                        logger.warning(yellow(f"Mismatched @section end tag '{section_end_match.group(1)}' in {relative_path} on line {i+1}"))

            # --- Pass 2: Handle @param replacements ---
            final_lines = list(section_modified_lines)
            for i, line in enumerate(section_modified_lines):
                param_match = re.search(r'#\s*@param\s+([\w.-]+)', line)
                if param_match and (i + 1) < len(section_modified_lines):
                    yaml_path = param_match.group(1)
                    value_from_yaml = get_value_by_path(data, yaml_path)
                    if value_from_yaml is not None:
                        original_next_line = section_modified_lines[i + 1]
                        # Don't perform replacement on a commented-out line
                        if original_next_line.lstrip().startswith('#'):
                            continue

                        line_structure_match = re.match(r'^(\s*(?:-\s+)?[\w.-]+\s*[:=])', original_next_line)
                        if line_structure_match:
                            line_prefix = line_structure_match.group(1).rstrip()
                            formatted_new_value = format_value_for_file(value_from_yaml)
                            original_value_part = original_next_line[len(line_structure_match.group(1)):]
                            trailing_comment_match = re.search(r'(\s*#.*)', original_value_part)
                            trailing_comment = trailing_comment_match.group(1) if trailing_comment_match else ''
                            new_line = f"{line_prefix} {formatted_new_value}{trailing_comment}\n"

                            if final_lines[i + 1] != new_line:
                                final_lines[i + 1] = new_line
                                file_was_modified = True
                                total_replacements += 1
                        else:
                            logger.warning(yellow(f"  - Found @param for '{yaml_path}' but couldn't find a 'key=value' or 'key: value' pattern on the next line in {relative_path}"))

            # --- Write Output ---
            if file_was_modified:
                total_files_modified += 1
                logger.info(green(f"  -> Writing modified file: {relative_path}"))
                with open(output_path, 'w', encoding='utf-8') as f_out:
                    f_out.writelines(final_lines)
            elif file_path != output_path:
                logger.debug(f"  -> Copying unmodified file: {relative_path}")
                shutil.copy2(file_path, output_path)
            else:
                logger.debug(f"  -> Skipping unmodified file (in-place edit): {relative_path}")

        except Exception as e:
            logger.error(red(f"An unexpected error occurred processing {relative_path}: {e}"), exc_info=True)

    logger.info(green(f"File processing finished. Modified {total_files_modified} files with {total_replacements} value replacements and {total_section_toggles} section line toggles."))
