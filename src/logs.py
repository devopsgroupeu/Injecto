#!/usr/bin/env python3
"""Structured JSON logging for Injecto.

Emits one JSON object per log line on stdout, using a schema shared across the
OpenPrime services ({timestamp, level, service, message, requestId}) so Loki can
parse and correlate logs from every service the same way.
"""

import contextvars
import json
import logging
import re
import sys

SERVICE = "injecto"

# Correlation id propagated from the caller via the X-Request-ID header (set by the
# API middleware). Included in every log line emitted while handling that request.
request_id_var = contextvars.ContextVar("request_id", default=None)

# Defence-in-depth: mask user:pass@ credentials in any logged string.
_URL_CREDENTIALS_RE = re.compile(r"://[^/\s:@]+:[^/\s@]+@")


def _mask(text: str) -> str:
    return _URL_CREDENTIALS_RE.sub("://***:***@", text)


# Normalise Python level names to the backend's vocabulary (info/warn/error/debug).
_LEVEL_MAP = {"WARNING": "warn", "CRITICAL": "error"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
            "level": _LEVEL_MAP.get(record.levelname, record.levelname.lower()),
            "service": SERVICE,
            "message": _mask(record.getMessage()),
        }
        request_id = request_id_var.get()
        if request_id:
            entry["requestId"] = request_id
        if record.exc_info:
            entry["stack"] = self.formatException(record.exc_info)
        return json.dumps(entry)


# Configure the root logger with a single JSON handler on stdout (collected by Loki
# in Kubernetes). No file handler — matches the backend's console-only approach.
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(JsonFormatter())
_root = logging.getLogger()
_root.handlers.clear()
_root.addHandler(_handler)
_root.setLevel(logging.INFO)

logger = logging.getLogger(SERVICE)


def setLoggingLevel(level: int):
    """Set the logging level on the root logger and its handlers."""
    root = logging.getLogger()
    root.setLevel(level)
    for handler in root.handlers:
        handler.setLevel(level)
    logger.info(f"Logging level set to {logging.getLevelName(level)}")


# Colour helpers are now no-ops: structured JSON must stay plain so Loki can parse
# it. Kept as pass-throughs so existing call sites (logger.info(green("..."))) work.
def green(message: str) -> str:
    return message


def yellow(message: str) -> str:
    return message


def red(message: str) -> str:
    return message


def greenBack(message: str) -> str:
    return message
