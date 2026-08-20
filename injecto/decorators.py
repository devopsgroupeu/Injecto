#!/usr/bin/env python3
"""The decorator grammar shared by template substitution and catalog extraction.

Both ``processing.py`` (which substitutes values into templates) and
``catalog.py`` (which extracts the wizard catalog from those same templates)
have to agree on what a decorator *is*. When they disagree the catalog
advertises a field that generation ignores, which is invisible until a customer
configures it and nothing happens. Keeping one set of regexes here makes that
class of drift structurally impossible rather than merely unlikely.

Grammar::

    # @param  <dot.path> [| key=value]...
    # @module <dot.path> [| key=value]...
    # @section <dot.path> begin
    # @section <dot.path> end

The path is always the first token and is matched by ``[\\w.-]+``, which stops
at the space before ``|``. That is why the attribute tail is transparently
ignored by the deployed substituter -- proven by the regression corpus in
``tests/test_processing.py`` (OP-203), which is what decouples catalog work
from lockstep deployment.
"""

import json
import re
from typing import Optional

# --- Grammar ---------------------------------------------------------------
# PARAM_RE, SECTION_BEGIN_RE and SECTION_END_RE are lifted verbatim from
# processing.py. Changing them changes substitution behaviour for every
# deployed template; the regression corpus is the guard.
PARAM_RE = re.compile(r'#\s*@param\s+([\w.-]+)')
SECTION_BEGIN_RE = re.compile(r'#\s*@section\s+([\w.-]+)\s+begin')
SECTION_END_RE = re.compile(r'#\s*@section\s+([\w.-]+)\s+end')
MODULE_RE = re.compile(r'#\s*@module\s+([\w.-]+)')

# Decorator lines must never be un-commented by @section toggling -- an
# un-commented decorator is code, not a marker. processing.py checks this
# against the *stripped* line, so the leading '#' is already gone.
DECORATOR_PREFIXES = ('@param', '@section', '@module')

# A value line: optional YAML list dash, a key, then ':' or '='.
VALUE_LINE_RE = re.compile(r'^(\s*(?:-\s+)?[\w.-]+\s*[:=])')


class DecoratorError(ValueError):
    """A decorator is present but malformed.

    Carries no file or line -- the caller knows those and attaches them, which
    keeps this module free of any notion of where templates live.
    """


def _split_attr_tail(line: str, match: re.Match) -> str:
    """Return the raw attribute tail that follows a decorator's path token."""
    return line[match.end():]


def parse_attrs(tail: str) -> dict:
    """Parse a ``| key=value | key=value`` tail into a dict.

    ``options`` is decoded as strict JSON because it carries structure the
    wizard renders; every other value is returned as a stripped string and
    interpreted by the extractor. An empty or whitespace-only tail is not an
    error -- a bare decorator is the common case.

    Raises DecoratorError on a segment that is not ``key=value``, on a
    duplicate key, or on ``options`` that is not valid JSON.
    """
    tail = tail.strip()
    if not tail:
        return {}

    if not tail.startswith('|'):
        raise DecoratorError(
            f"attributes must be introduced by '|', found {tail[:20]!r}"
        )

    attrs: dict = {}
    for segment in tail.split('|')[1:]:
        segment = segment.strip()
        if not segment:
            raise DecoratorError("empty attribute segment between '|' separators")

        key, sep, value = segment.partition('=')
        if not sep:
            raise DecoratorError(f"attribute {segment!r} is not key=value")

        key = key.strip()
        value = value.strip()
        if not key:
            raise DecoratorError(f"attribute {segment!r} has an empty key")
        if key in attrs:
            raise DecoratorError(f"duplicate attribute {key!r}")

        if key == 'options':
            try:
                attrs[key] = json.loads(value)
            except json.JSONDecodeError as exc:
                raise DecoratorError(
                    f"options must be valid JSON, got {value!r} ({exc.msg})"
                ) from exc
        else:
            attrs[key] = value

    return attrs


def parse_param(line: str) -> Optional[tuple]:
    """Parse a ``@param`` line into ``(path, attrs)``, or None if absent.

    Raises DecoratorError when the decorator is present but its attribute tail
    is malformed -- silently returning None there would drop a field from the
    catalog while substitution kept working on it.
    """
    match = PARAM_RE.search(line)
    if not match:
        return None
    return match.group(1), parse_attrs(_split_attr_tail(line, match))


def parse_module(line: str) -> Optional[tuple]:
    """Parse a ``@module`` line into ``(key, attrs)``, or None if absent."""
    match = MODULE_RE.search(line)
    if not match:
        return None
    return match.group(1), parse_attrs(_split_attr_tail(line, match))


def parse_section(line: str) -> Optional[tuple]:
    """Parse a ``@section`` marker into ``(path, 'begin'|'end')``, or None."""
    begin = SECTION_BEGIN_RE.search(line)
    if begin:
        return begin.group(1), 'begin'
    end = SECTION_END_RE.search(line)
    if end:
        return end.group(1), 'end'
    return None


def strip_attr_tail(line: str) -> str:
    """Remove a decorator's ``| key=value`` tail, leaving the rest of the line.

    The decorator lines are copied verbatim into the generated repository, so
    after the templates are enriched every customer would read our wizard
    metadata in their own tfvars. This removes the tail and nothing else.

    The line itself is deliberately kept. ``tests/gate.py`` locates each value
    in the generated tree by the line number it scanned from the template, so
    deleting decorator lines would shift every line after them. Keeping
    ``# @param <path>`` also documents which wizard field drives the value.

    Only a tail introduced by ``|`` is removed; anything else after the path is
    not attribute syntax and is left alone rather than silently discarded.
    """
    for regex in (PARAM_RE, MODULE_RE):
        match = regex.search(line)
        if not match:
            continue
        tail = line[match.end():]
        if not tail.lstrip().startswith('|'):
            return line
        return line[:match.end()] + ('\n' if line.endswith('\n') else '')
    return line
