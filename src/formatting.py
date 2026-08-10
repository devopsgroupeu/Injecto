"""Post-processing applied to a generated tree, shared by the CLI and the API.

Substitution rewrites single lines and does not preserve HCL alignment, so the
generated Terraform parses but is misformatted. The pipelines Injecto generates
run `terraform fmt -check` as their first job, so formatting here is what keeps
that first job green.
"""

import subprocess
from pathlib import Path

from logs import logger, green, yellow


def run_terraform_fmt(output_dir: Path):
    """Run terraform fmt on all Terraform directories in the output."""
    tf_dirs = set()
    for tf_file in output_dir.rglob("*.tf"):
        tf_dirs.add(tf_file.parent)

    for tf_dir in sorted(tf_dirs):
        try:
            result = subprocess.run(
                ["terraform", "fmt", "-recursive"],
                cwd=str(tf_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info(green(f"terraform fmt successful: {tf_dir.relative_to(output_dir)}"))
            else:
                logger.warning(yellow(f"terraform fmt failed in {tf_dir}: {result.stderr}"))
        except FileNotFoundError:
            logger.warning(yellow("terraform binary not found, skipping formatting"))
            break
        except subprocess.TimeoutExpired:
            logger.warning(yellow(f"terraform fmt timed out in {tf_dir}"))
