#!/usr/bin/env python3

import subprocess
import os

from logs import logger, green, yellow, red


def clone_repository(repo_url, clone_path, branch=None, username=None, pat=None):
    """
    Clones a Git repository from a given URL.

    Args:
        repo_url (str): The URL of the repository to clone.
        clone_path (str): The local path where the repository will be cloned.
        branch (str, optional): The specific branch to clone. Defaults to None.
        username (str, optional): The username for authentication for private repositories. Defaults to None.
        pat (str, optional): The Personal Access Token for authentication for private repositories. Defaults to None.

    Returns:
        bool: True if the repository was cloned successfully, False otherwise.
    """
    # Create the parent directory if it doesn't exist
    logger.info(
        f"Create the parent directory {os.path.dirname(clone_path)} if it doesn't exist"
    )
    os.makedirs(os.path.dirname(clone_path), exist_ok=True)

    # Check if the clone path already exists and is not empty
    if os.path.exists(clone_path) and os.listdir(clone_path):
        logger.error(red(f"The directory '{clone_path}' is not empty."))
        return False

    # Handle private repository authentication by modifying the URL
    if username and pat:
        # We need to format the URL to include the credentials.
        # This assumes the URL starts with "https://"
        if repo_url.startswith("https://"):
            protocol_end = len("https://")
            base_url = repo_url[protocol_end:]
            authenticated_url = f"https://{username}:{pat}@{base_url}"
        else:
            # Handle other protocols if necessary, but this is the most common.
            logger.error(red("Authentication requires an 'https' URL."))
            return False
    else:
        authenticated_url = repo_url

    # Construct the git clone command
    command = ["git", "clone"]

    if branch:
        command.extend(["--branch", branch])

    command.extend([authenticated_url, clone_path])

    logger.info(f"Executing command: {' '.join(command)}")

    try:
        # Run the command
        subprocess.run(command, check=True, capture_output=True, text=True)
        logger.info(green("Repository cloned successfully!"))
        return True
    except subprocess.CalledProcessError as e:
        logger.error(red(f"Error cloning repository: {e}"))
        return False
    except FileNotFoundError:
        logger.error(
            red(
                "'git' command not found. Please ensure Git is installed and in your system's PATH."
            )
        )
        return False


# --- Example Usage ---

# Example 1: Cloning a public repository
# print("--- Cloning a public repository ---")
# public_repo_url = "https://github.com/devopsgroupeu/openprime-infra-templates.git"
# public_clone_path = "cloned_repos/git_public"
# clone_repository(public_repo_url, public_clone_path)
# print("-" * 30)

# Example 2: Cloning a public repository with a specific branch
# print("\n--- Cloning a public repository with a specific branch ---")
# branch_to_clone = "OPE-89-prepare-repository"
# branch_clone_path = "cloned_repos/git_branch"
# clone_repository(public_repo_url, branch_clone_path, branch=branch_to_clone)
# print("-" * 30)

# Example 3: Cloning a private repository (replace with your own details)
# Note: You should be careful with storing credentials in plain text.
# Consider using environment variables or a more secure method in a real application.
# private_repo_url = "https://github.com/your-username/your-private-repo.git"
# your_username = "your-username"
# your_pat = "your-personal-access-token"
# private_clone_path = "cloned_repos/private_repo"
# print("\n--- Cloning a private repository ---")
# clone_repository(private_repo_url, private_clone_path, username=your_username, pat=your_pat)
