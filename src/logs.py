#!/usr/bin/env python3

import logging
import sys
from colorama import init, Fore, Back

# --- Initialize colorama ---
init(autoreset=True)

# --- Configuration ---
LOG_FORMAT = "%(asctime)s - %(levelname)-8s - %(message)s"
LOG_LEVEL = logging.INFO  # Change to logging.DEBUG for more verbose output

# --- Logging Setup ---
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT, stream=sys.stdout)
file_handler = logging.FileHandler("injecto.log")
file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
logging.getLogger().addHandler(file_handler)

logger = logging.getLogger(__name__)  # Use __name__ for logger identification


def setLoggingLevel(level: int):
    """Set the logging level."""
    logger.setLevel(level)
    for handler in logger.handlers:
        handler.setLevel(level)
    level_name = logging.getLevelName(level)
    logger.info(f"Logging level set to {level_name}")


def green(message: str):
    """Prints a message in green color."""
    return Fore.GREEN + message


def yellow(message: str):
    """Prints a message in yellow color."""
    return Fore.YELLOW + message


def red(message: str):
    """Prints a message in red color."""
    return Fore.RED + message

def greenBack(message: str):
    """Prints a message in magenta color."""
    return Back.GREEN + message + Back.RESET
