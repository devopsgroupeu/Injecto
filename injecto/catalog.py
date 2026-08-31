#!/usr/bin/env python3
"""Extract the wizard service catalog from decorated Terraform templates.

The catalog is what the frontend renders as the environment wizard. Deriving it
from the same decorators that drive substitution means a module added to the
templates repo appears in the wizard with no frontend or backend deploy -- the
whole point of OP-202.

Canonical source is ``templates/terraform/<provider>/terraform.auto.tfvars``:
every ``@param`` there is followed by the single-line HCL literal that supplies
its default, which is the only place both the value and its Terraform variable
name appear together.

Extraction never guesses. Where a literal cannot yield an unambiguous type
(``null``, ``[]``) the decorator must declare ``| valueType=...``; where a path
leaf does not follow one of the two naming conventions in use, the path must be
listed in the repo's ``catalog/legacy-paths.txt``. Both surface as errors that
fail ``--extract-catalog --strict`` rather than as a catalog that quietly
advertises a field the generator will not fill.

Vocabulary
----------
One word per concept, and the same word the frontend already uses -- so the
catalog drops into ``SERVICES_CONFIG`` with no translation layer. A mapping
layer is a place for the two vocabularies to drift apart, which is the class of
bug this whole epic exists to remove.

==============  ===========================================================
``name``        Field key, emitted on the field as well as being its map key
``displayName`` Human label, on both fields and services
``type``        The control that edits the value: text, dropdown, toggle
``valueType``   What the value *is*: string, number, boolean, list, map
``defaultValue``Value the templates ship
``options``     Choices for a dropdown
==============  ===========================================================

``type`` and ``valueType`` are genuinely two things: ``allowExplicitIndex`` is a
Terraform ``string`` edited by a toggle. They shared one word until the frontend
needed both, and one word for two concepts is how a dropdown ends up rendering a
boolean.
"""

import argparse
import json
import re
import sys
from pathlib import Path

from .decorators import (
    DecoratorError,
    parse_module,
    parse_param,
    parse_section,
)
from .processing import opens_multiline_value

SCHEMA_VERSION = 1

# Where the legacy-naming allowlist lives, relative to the templates repo root.
# Deliberately outside templates/ so it is never copied into a customer's
# generated repository, and inside the templates repo rather than Injecto so a
# new exception is a templates PR, not an Injecto release.
LEGACY_PATHS_FILE = Path('catalog') / 'legacy-paths.txt'

# A bare "@section services.vpc" predates the ".enabled" convention. Grandfathered
# because renaming it would change substitution for every deployed template.
BARE_SECTION_SERVICES = frozenset({'vpc'})

_NUMBER_RE = re.compile(r'^-?\d+(?:\.\d+)?$')
_QUOTED_BOOL_RE = re.compile(r'^"(?:true|false)"$', re.IGNORECASE)


def _camel_to_snake(name: str) -> str:
    return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()


def infer_type(literal: str):
    """Map a single-line HCL literal to ``(type, defaultValue)``.

    Raises DecoratorError when the literal is ambiguous, so the decorator has to
    say what it means. An empty list cannot reveal its element type and ``null``
    reveals nothing at all; a quoted boolean is almost always a mistake, and
    guessing either way produces a wizard control that writes the wrong shape.
    """
    literal = literal.strip()

    if literal == 'null':
        raise DecoratorError("literal is null; declare the type with | type=...")
    if literal == '[]':
        raise DecoratorError("empty list reveals no element type; declare | type=list")
    if _QUOTED_BOOL_RE.match(literal):
        raise DecoratorError(
            f"{literal} is a quoted boolean; write it unquoted or declare | type=string"
        )

    if literal in ('true', 'false'):
        return 'boolean', literal == 'true'
    if _NUMBER_RE.match(literal):
        return 'number', float(literal) if '.' in literal else int(literal)
    if literal.startswith('"'):
        try:
            return 'string', json.loads(literal)
        except json.JSONDecodeError:
            return 'string', literal.strip('"')
    if literal.startswith('['):
        return 'list', literal
    if literal.startswith('{'):
        return 'object', literal

    raise DecoratorError(f"cannot infer a type from {literal!r}; declare | type=...")


def load_legacy_paths(repo_root: Path) -> set:
    """Read the allowlist of ``@param`` paths exempt from the naming rules."""
    allowlist_file = repo_root / LEGACY_PATHS_FILE
    if not allowlist_file.is_file():
        return set()
    paths = set()
    for raw in allowlist_file.read_text().splitlines():
        entry = raw.split('#', 1)[0].strip()
        if entry:
            paths.add(entry)
    return paths


def name_matches_convention(path: str, tf_var: str) -> bool:
    """True if the Terraform variable name follows either convention in use.

    Two are legal because both are already established across the templates:
    ``services.vpc.azCount -> az_count`` and the far more common prefixed form
    ``services.rds.engineVersion -> rds_engine_version``. Accepting only one
    would push 81% or 19% of today's catalog into the allowlist and leave the
    check enforcing nothing.
    """
    segments = path.split('.')
    leaf = _camel_to_snake(segments[-1])
    if tf_var == leaf:
        return True
    if len(segments) == 3 and segments[0] == 'services':
        return tf_var == f"{segments[1]}_{leaf}"
    return False


class _Collector:
    """Accumulates errors and warnings with the file:line that produced them."""

    def __init__(self):
        self.errors = []
        self.warnings = []

    def _add(self, bucket, code, message, file=None, line=None):
        bucket.append({'code': code, 'message': message, 'file': file, 'line': line})

    def error(self, code, message, file=None, line=None):
        self._add(self.errors, code, message, file, line)

    def warn(self, code, message, file=None, line=None):
        self._add(self.warnings, code, message, file, line)


def _collect_sections(provider_dir: Path) -> dict:
    """Map every ``@section`` path to the file:line of its begin marker."""
    sections = {}
    for path in sorted(provider_dir.rglob('*')):
        if not path.is_file():
            continue
        try:
            lines = path.read_text().splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, start=1):
            parsed = parse_section(line)
            if parsed and parsed[1] == 'begin':
                sections.setdefault(parsed[0], (path, number))
    return sections


def _synthesize_enabled(service_key: str, sections: dict, collector: _Collector) -> dict:
    """Build the ``enabled`` toggle, which no Terraform variable backs.

    Enablement is expressed by ``@section`` alone -- the module's whole resource
    block is commented out when it is off -- so the field has to be synthesized
    from the marker rather than read from a value line.
    """
    dotted = f"services.{service_key}.enabled"
    if dotted in sections:
        source = sections[dotted]
    elif service_key in BARE_SECTION_SERVICES and f"services.{service_key}" in sections:
        source = sections[f"services.{service_key}"]
        collector.warn(
            'LEGACY_BARE_SECTION',
            f"service '{service_key}' is gated by the pre-.enabled marker "
            f"'@section services.{service_key}'",
            file=str(source[0]), line=source[1],
        )
    else:
        return {}

    return {
        'enabled': {
            'name': 'enabled',
            'path': dotted,
            'tfVar': None,
            'valueType': 'boolean',
            'type': 'toggle',
            'defaultValue': False,
            'displayName': 'Enabled',
            'sectionGated': True,
            'file': str(source[0]),
            'line': source[1],
        }
    }


def _ensure_service(catalog, service_key, module_attrs, sections, collector, where, line):
    """Return the catalog entry for a service, creating it on first sight.

    Returns None when the service has no ``@section`` gating it, which is the one
    condition that makes a module genuinely unusable: without the marker nothing
    ever switches its resources on, so advertising it would be a lie.
    """
    service = catalog['services'].get(service_key)
    if service is not None:
        return service

    enabled = _synthesize_enabled(service_key, sections, collector)
    if not enabled:
        collector.error(
            'NO_SECTION',
            f"service '{service_key}' has @param entries but no "
            f"'@section services.{service_key}.enabled' marker gating it",
            file=where, line=line,
        )
        return None

    attrs = module_attrs.get(service_key, {})
    service = {
        'key': service_key,
        'displayName': attrs.get('displayName', service_key),
        'fields': enabled,
    }
    service.update({k: v for k, v in attrs.items() if k != 'displayName'})
    catalog['services'][service_key] = service
    return service


def extract_catalog(repo_root, provider: str = 'aws') -> dict:
    """Extract the schemaVersion-1 catalog for one provider.

    Returns the document with ``errors`` and ``warnings`` populated; the caller
    decides whether errors are fatal. Callers that need a guarantee should check
    ``errors`` rather than trusting a non-empty ``services``.
    """
    repo_root = Path(repo_root)
    provider_dir = repo_root / 'templates' / 'terraform' / provider
    collector = _Collector()

    catalog = {
        'schemaVersion': SCHEMA_VERSION,
        'provider': provider,
        'global': {'fields': {}},
        'services': {},
        'warnings': collector.warnings,
        'errors': collector.errors,
    }

    tfvars = provider_dir / 'terraform.auto.tfvars'
    if not tfvars.is_file():
        collector.error(
            'NO_TFVARS',
            f"canonical source {tfvars} not found",
            file=str(tfvars),
        )
        return catalog

    legacy_paths = load_legacy_paths(repo_root)
    sections = _collect_sections(provider_dir)
    lines = tfvars.read_text().splitlines()
    where = str(tfvars)

    module_attrs = {}
    for number, line in enumerate(lines, start=1):
        try:
            parsed = parse_module(line)
        except DecoratorError as exc:
            collector.error('BAD_MODULE_ATTRS', str(exc), file=where, line=number)
            continue
        if parsed:
            module_attrs[parsed[0].split('.')[-1]] = parsed[1]

    for index, line in enumerate(lines):
        number = index + 1
        try:
            parsed = parse_param(line)
        except DecoratorError as exc:
            collector.error('BAD_PARAM_ATTRS', str(exc), file=where, line=number)
            continue
        if not parsed:
            continue

        path, attrs = parsed
        segments = path.split('.')
        is_global = len(segments) == 1
        if not is_global and not (len(segments) == 3 and segments[0] == 'services'):
            collector.error(
                'BAD_PATH',
                f"'{path}' is neither a bare global nor services.<key>.<leaf>",
                file=where, line=number,
            )
            continue

        # Register the service before validating the field. A service whose only
        # @param is malformed must still appear in the catalog with its enabled
        # toggle -- dropping it here would silently delete a whole module from
        # the wizard and report a catalog anyway.
        service = None
        if not is_global:
            service = _ensure_service(
                catalog, segments[1], module_attrs, sections, collector, where, number
            )
            if service is None:
                continue

        if index + 1 >= len(lines):
            collector.error(
                'NO_VALUE_LINE', f"@param '{path}' is the last line of the file",
                file=where, line=number,
            )
            continue

        value_line = lines[index + 1]
        assignment = re.match(r'^\s*([\w.-]+)\s*=\s*(.*)$', value_line)
        if not assignment:
            collector.error(
                'NO_VALUE_LINE',
                f"line after @param '{path}' is not a Terraform assignment",
                file=where, line=number + 1,
            )
            continue

        tf_var, literal = assignment.group(1), assignment.group(2)

        if opens_multiline_value(literal) and attrs.get('exclude') != 'true':
            collector.error(
                'MULTILINE_VALUE',
                f"'{tf_var}' opens a multi-line literal; substitution refuses these "
                f"(add | exclude=true to keep it out of the catalog)",
                file=where, line=number + 1,
            )
            continue
        if attrs.get('exclude') == 'true':
            continue

        if not is_global and path not in legacy_paths:
            if not name_matches_convention(path, tf_var):
                collector.error(
                    'NAME_MISMATCH',
                    f"'{path}' does not map to '{tf_var}' under either naming "
                    f"convention; rename it or list it in {LEGACY_PATHS_FILE}",
                    file=where, line=number,
                )
                continue

        # `valueType` is what the value *is* (string, number, list); `type` is the
        # control that edits it (text, dropdown, toggle). They were one word until
        # the frontend needed both, and one word for two concepts is how a
        # dropdown ends up rendering a boolean.
        declared_type = attrs.get('valueType')
        if declared_type:
            value_type = declared_type
            default_value = attrs.get('default', literal)
        else:
            try:
                value_type, default_value = infer_type(literal)
            except DecoratorError as exc:
                collector.error('UNKNOWN_TYPE', f"'{path}': {exc}", file=where, line=number + 1)
                continue

        field = {
            # The frontend reads `name` off the field itself, not off the key it
            # is stored under, so emit both rather than making every consumer
            # thread the key through.
            'name': segments[2] if not is_global else path,
            'path': path,
            'tfVar': tf_var,
            'valueType': value_type,
            'defaultValue': default_value,
            'file': where,
            'line': number,
        }
        for key, value in attrs.items():
            if key not in ('valueType', 'default', 'exclude'):
                field[key] = value

        if is_global:
            catalog['global']['fields'][path] = field
        else:
            service['fields'][segments[2]] = field

    return catalog


def run_cli(argv=None) -> int:
    """Entry point for ``--extract-catalog``; returns the process exit code."""
    parser = argparse.ArgumentParser(prog='injecto --extract-catalog')
    parser.add_argument('repo_root', type=Path, help='Templates repository root.')
    parser.add_argument('--provider', default='aws', help='Provider directory to scan.')
    parser.add_argument('--strict', action='store_true', help='Exit non-zero on errors.')
    parser.add_argument('--output', type=Path, help='Write JSON here instead of stdout.')
    args = parser.parse_args(argv)

    catalog = extract_catalog(args.repo_root, args.provider)
    rendered = json.dumps(catalog, indent=2, sort_keys=True)

    if args.output:
        args.output.write_text(rendered + '\n')
    else:
        print(rendered)

    for problem in catalog['errors']:
        location = f"{problem['file']}:{problem['line']}" if problem['line'] else problem['file']
        print(f"error: {location}: [{problem['code']}] {problem['message']}", file=sys.stderr)

    if args.strict and catalog['errors']:
        print(f"\n{len(catalog['errors'])} error(s); catalog rejected.", file=sys.stderr)
        return 1
    return 0
