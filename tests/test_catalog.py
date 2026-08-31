#!/usr/bin/env python3
"""Catalog extraction, its grammar, and the drift guard between the two.

The load-bearing test here is test_every_catalog_field_substitutes: it runs the
real substituter over every field the extractor advertises and asserts the value
lands in the output. A catalog that claims a field generation ignores is the one
failure this whole feature cannot tolerate, because it is invisible until a
customer configures that field and nothing happens.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from injecto.catalog import (
    LEGACY_PATHS_FILE,
    SCHEMA_VERSION,
    extract_catalog,
    infer_type,
    name_matches_convention,
    run_cli,
)
from injecto.decorators import DecoratorError, parse_attrs, parse_module, parse_param
from injecto.processing import process_files

REPO_ROOT = Path(__file__).resolve().parents[1]


# --- Fixtures ---------------------------------------------------------------

MINIMAL_TFVARS = """\
# @param region
region = "eu-west-1"

# @param services.eks.kubernetesVersion
eks_kubernetes_version = "1.33"
# @param services.eks.desiredSize
eks_desired_size = 2
# @param services.eks.publicAccess
eks_public_access = false
"""

MINIMAL_TF = """\
# @section services.eks.enabled begin
module "eks" {
  version = var.eks_kubernetes_version
}
# @section services.eks.enabled end
"""


def build_templates(root: Path, tfvars: str, tf: str = MINIMAL_TF, provider: str = 'aws') -> Path:
    """Lay out the minimum tree extract_catalog expects."""
    provider_dir = root / 'templates' / 'terraform' / provider
    provider_dir.mkdir(parents=True, exist_ok=True)
    (provider_dir / 'terraform.auto.tfvars').write_text(tfvars)
    (provider_dir / 'main.tf').write_text(tf)
    return root


def codes(catalog) -> list:
    return [error['code'] for error in catalog['errors']]


# --- Grammar ----------------------------------------------------------------

def test_bare_decorator_has_no_attrs():
    assert parse_param('# @param services.eks.desiredSize') == ('services.eks.desiredSize', {})


def test_attrs_are_pipe_delimited_key_values():
    path, attrs = parse_param('# @param services.eks.size | type=dropdown | displayName=Node size')
    assert path == 'services.eks.size'
    assert attrs == {'type': 'dropdown', 'displayName': 'Node size'}


def test_options_is_decoded_as_json():
    _, attrs = parse_param('# @param a.b.c | options=["t3.small", "t3.large"]')
    assert attrs['options'] == ['t3.small', 't3.large']


def test_path_stops_at_the_attribute_tail():
    """The tail must not leak into the path -- this is what keeps it inert for
    the deployed substituter, and it is the premise every later catalog task
    rests on (OP-203)."""
    path, _ = parse_param('# @param services.eks.size | type=dropdown')
    assert path == 'services.eks.size'


def test_module_decorator_parses_like_param():
    assert parse_module('# @module services.eks | displayName=Kubernetes') == (
        'services.eks', {'displayName': 'Kubernetes'},
    )


@pytest.mark.parametrize('tail, fragment', [
    ('type=dropdown', "must be introduced by '|'"),
    ('| dropdown', 'is not key=value'),
    ('| type=a | type=b', 'duplicate attribute'),
    ('| options=[not json]', 'must be valid JSON'),
    ('| type=a || displayName=b', 'empty attribute segment'),
])
def test_malformed_attrs_raise(tail, fragment):
    with pytest.raises(DecoratorError) as excinfo:
        parse_attrs(tail)
    assert fragment in str(excinfo.value)


def test_malformed_attrs_on_a_param_raise_rather_than_drop_the_field():
    """Returning None here would drop the field from the catalog while
    substitution kept working on it -- silent divergence, the exact thing this
    module exists to prevent."""
    with pytest.raises(DecoratorError):
        parse_param('# @param services.eks.size | notkeyvalue')


# --- Type inference ---------------------------------------------------------

@pytest.mark.parametrize('literal, expected', [
    ('true', ('boolean', True)),
    ('false', ('boolean', False)),
    ('2', ('number', 2)),
    ('-1.5', ('number', -1.5)),
    ('"eu-west-1"', ('string', 'eu-west-1')),
    # Structured literals come back as values, not as their own source text:
    # an array control handed the string "[]" opens on a typo.
    ('["t4g.large"]', ('list', ['t4g.large'])),
    ('[1, 2]', ('list', [1, 2])),
])
def test_unambiguous_literals_infer(literal, expected):
    assert infer_type(literal) == expected


@pytest.mark.parametrize('literal, fragment', [
    ('null', 'literal is null'),
    ('[]', 'empty list reveals no element type'),
    ('"true"', 'quoted boolean'),
    # An HCL map is not JSON. Rewriting one into the other with a regex would be
    # a second, wronger parser, so the decorator declares the default instead.
    ('{ one = {} }', 'HCL maps are not JSON'),
])
def test_ambiguous_literals_refuse(literal, fragment):
    with pytest.raises(DecoratorError) as excinfo:
        infer_type(literal)
    assert fragment in str(excinfo.value)


def test_nested_sections_become_toggles(tmp_path):
    """A @section under a service is a switch the wizard has to be able to show.

    services.eks.karpenterEnabled gates an entire node provisioner. Before this,
    the catalog carried no field for it, so a wizard hydrated from the catalog
    would have dropped the toggle without anything failing.
    """
    tfvars = (
        '# @module services.eks | displayName=Kubernetes\n'
        + MINIMAL_TFVARS
        + '# @section services.eks.karpenterEnabled begin\n'
        + 'karpenter_enabled = true\n'
        + '# @section services.eks.karpenterEnabled end\n'
    )
    catalog = extract_catalog(build_templates(tmp_path, tfvars))
    fields = catalog['services']['eks']['fields']

    assert 'karpenterEnabled' in fields
    toggle = fields['karpenterEnabled']
    assert toggle['type'] == 'toggle'
    assert toggle['valueType'] == 'boolean'
    assert toggle['defaultValue'] is False
    assert toggle['sectionGated'] is True


def test_helm_chart_sections_are_left_to_helm_charts_config(tmp_path):
    """Only direct children become toggles.

    services.eks.helmCharts.certManager.enabled sits a level deeper and belongs
    to helmChartsConfig (OP-200), not to the service catalog. Pulling it in here
    would put the same switch in two places.
    """
    tfvars = (
        '# @module services.eks | displayName=Kubernetes\n'
        + MINIMAL_TFVARS
        + '# @section services.eks.helmCharts.certManager.enabled begin\n'
        + 'cert_manager = true\n'
        + '# @section services.eks.helmCharts.certManager.enabled end\n'
    )
    catalog = extract_catalog(build_templates(tmp_path, tfvars))
    fields = catalog['services']['eks']['fields']

    assert not [k for k in fields if 'certManager' in k or 'helmCharts' in k]


# --- Naming conventions -----------------------------------------------------

@pytest.mark.parametrize('path, tf_var', [
    ('services.vpc.azCount', 'az_count'),                      # convention A
    ('services.rds.engineVersion', 'rds_engine_version'),      # convention B
    ('services.vpc.cidr', 'vpc_cidr'),                         # B, single-word leaf
])
def test_both_conventions_accepted(path, tf_var):
    assert name_matches_convention(path, tf_var)


@pytest.mark.parametrize('path, tf_var', [
    ('services.rds.backupRetention', 'rds_backup_retention_period'),
    ('services.sqs.createDeadLetterQueue', 'sqs_create_dlq'),
])
def test_renamed_leaves_are_rejected(path, tf_var):
    assert not name_matches_convention(path, tf_var)


# --- Extraction -------------------------------------------------------------

def test_minimal_tree_extracts_cleanly(tmp_path):
    catalog = extract_catalog(build_templates(tmp_path, MINIMAL_TFVARS))

    assert catalog['errors'] == []
    assert catalog['schemaVersion'] == SCHEMA_VERSION
    assert catalog['provider'] == 'aws'
    assert set(catalog['global']['fields']) == {'region'}
    assert set(catalog['services']) == {'eks'}

    field = catalog['services']['eks']['fields']['kubernetesVersion']
    assert field['tfVar'] == 'eks_kubernetes_version'
    assert field['valueType'] == 'string'
    assert field['defaultValue'] == '1.33'


def test_enabled_is_synthesized_first(tmp_path):
    """No Terraform variable backs enablement -- it is @section-driven -- and the
    wizard renders the toggle above the fields it gates."""
    catalog = extract_catalog(build_templates(tmp_path, MINIMAL_TFVARS))
    fields = catalog['services']['eks']['fields']

    assert next(iter(fields)) == 'enabled'
    assert fields['enabled']['sectionGated'] is True
    assert fields['enabled']['tfVar'] is None


def test_module_decorator_enriches_the_service(tmp_path):
    tfvars = '# @module services.eks | displayName=Kubernetes | icon=k8s\n' + MINIMAL_TFVARS
    catalog = extract_catalog(build_templates(tmp_path, tfvars))

    assert catalog['services']['eks']['displayName'] == 'Kubernetes'
    assert catalog['services']['eks']['icon'] == 'k8s'


def test_service_without_a_module_decorator_falls_back_to_its_key(tmp_path):
    """Extraction must work before OP-206 decorates anything, or the catalog is
    useless until every module is annotated."""
    catalog = extract_catalog(build_templates(tmp_path, MINIMAL_TFVARS))
    assert catalog['services']['eks']['displayName'] == 'eks'


# --- Strict-mode error cases ------------------------------------------------

def test_unknown_type_is_an_error(tmp_path):
    tfvars = '# @param services.eks.tags\neks_tags = []\n'
    assert 'UNKNOWN_TYPE' in codes(extract_catalog(build_templates(tmp_path, tfvars)))


def test_declared_type_overrides_refusal(tmp_path):
    tfvars = '# @param services.eks.tags | valueType=list\neks_tags = []\n'
    catalog = extract_catalog(build_templates(tmp_path, tfvars))

    assert catalog['errors'] == []
    assert catalog['services']['eks']['fields']['tags']['valueType'] == 'list'


def test_invalid_options_json_is_an_error(tmp_path):
    tfvars = '# @param services.eks.size | options=[oops\neks_size = "m"\n'
    assert 'BAD_PARAM_ATTRS' in codes(extract_catalog(build_templates(tmp_path, tfvars)))


def test_multiline_value_is_an_error(tmp_path):
    """Substitution rewrites exactly the line after the decorator, so a value
    that opens a block would be replaced and the rest orphaned (OP-221)."""
    tfvars = '# @param services.eks.groups\neks_groups = {\n  one = {}\n}\n'
    assert 'MULTILINE_VALUE' in codes(extract_catalog(build_templates(tmp_path, tfvars)))


def test_multiline_value_can_be_excluded(tmp_path):
    tfvars = '# @param services.eks.groups | exclude=true\neks_groups = {\n  one = {}\n}\n'
    catalog = extract_catalog(build_templates(tmp_path, tfvars))

    assert catalog['errors'] == []
    assert 'groups' not in catalog['services']['eks']['fields']


def test_name_mismatch_is_an_error(tmp_path):
    tfvars = '# @param services.eks.desiredSize\neks_totally_different = 2\n'
    assert 'NAME_MISMATCH' in codes(extract_catalog(build_templates(tmp_path, tfvars)))


def test_legacy_allowlist_exempts_a_path(tmp_path):
    tfvars = '# @param services.eks.desiredSize\neks_totally_different = 2\n'
    root = build_templates(tmp_path, tfvars)
    allowlist = root / LEGACY_PATHS_FILE
    allowlist.parent.mkdir(parents=True, exist_ok=True)
    allowlist.write_text('# grandfathered\nservices.eks.desiredSize\n')

    catalog = extract_catalog(root)
    assert catalog['errors'] == []
    assert catalog['services']['eks']['fields']['desiredSize']['tfVar'] == 'eks_totally_different'


def test_param_without_a_section_is_an_error(tmp_path):
    """Without the marker nothing ever switches the module's resources on, so
    advertising it in the wizard would be a lie."""
    catalog = extract_catalog(build_templates(tmp_path, MINIMAL_TFVARS, tf='# no markers\n'))
    assert 'NO_SECTION' in codes(catalog)
    assert catalog['services'] == {}


def test_bare_vpc_section_is_grandfathered_with_a_warning(tmp_path):
    tfvars = '# @param services.vpc.azCount\naz_count = 2\n'
    tf = '# @section services.vpc begin\nmodule "vpc" {}\n# @section services.vpc end\n'
    catalog = extract_catalog(build_templates(tmp_path, tfvars, tf=tf))

    assert catalog['errors'] == []
    assert 'vpc' in catalog['services']
    assert [w['code'] for w in catalog['warnings']] == ['LEGACY_BARE_SECTION']


def test_bad_path_shape_is_an_error(tmp_path):
    tfvars = '# @param services.eks.nested.tooDeep\neks_nested_too_deep = 1\n'
    assert 'BAD_PATH' in codes(extract_catalog(build_templates(tmp_path, tfvars)))


def test_missing_value_line_is_an_error(tmp_path):
    tfvars = '# @param services.eks.desiredSize\n# a comment, not an assignment\n'
    assert 'NO_VALUE_LINE' in codes(extract_catalog(build_templates(tmp_path, tfvars)))


def test_a_broken_field_does_not_delete_its_service(tmp_path):
    """A service whose only @param is malformed must still appear with its
    enabled toggle. Dropping it silently removes a whole module from the wizard
    while the run still reports a catalog."""
    tfvars = '# @param services.eks.tags\neks_tags = []\n'
    catalog = extract_catalog(build_templates(tmp_path, tfvars))

    assert 'eks' in catalog['services']
    assert list(catalog['services']['eks']['fields']) == ['enabled']
    assert 'UNKNOWN_TYPE' in codes(catalog)


def test_missing_tfvars_reports_rather_than_raises(tmp_path):
    (tmp_path / 'templates' / 'terraform' / 'aws').mkdir(parents=True)
    assert 'NO_TFVARS' in codes(extract_catalog(tmp_path))


# --- The drift guard --------------------------------------------------------

def test_every_catalog_field_substitutes(tmp_path):
    """Every field the catalog advertises must provably reach the output.

    This is the permanent guard against the extractor and the substituter
    drifting apart: a field the wizard offers but generation ignores fails here
    rather than in a customer's environment.
    """
    root = build_templates(tmp_path / 'src', MINIMAL_TFVARS)
    catalog = extract_catalog(root)
    assert catalog['errors'] == []

    advertised = [
        field
        for service in catalog['services'].values()
        for field in service['fields'].values()
        if not field.get('sectionGated')
    ]
    advertised += list(catalog['global']['fields'].values())
    assert advertised, 'nothing to check -- the fixture stopped exercising the guard'

    for index, field in enumerate(advertised):
        sentinel = f'SENTINEL{index}'
        data = {}
        cursor = data
        segments = field['path'].split('.')
        for segment in segments[:-1]:
            cursor = cursor.setdefault(segment, {})
        cursor[segments[-1]] = sentinel

        out_dir = tmp_path / f'out{index}'
        process_files(root / 'templates' / 'terraform' / 'aws', out_dir, data)
        rendered = (out_dir / 'terraform.auto.tfvars').read_text()

        assert f'"{sentinel}"' in rendered, (
            f"catalog advertises {field['path']} ({field['tfVar']}) but the "
            f"substituter did not write it"
        )


def test_enabled_toggle_actually_gates_its_section(tmp_path):
    """The synthesized toggle is only honest if switching it off comments the
    module out -- it has no tfVar to prove itself with."""
    root = build_templates(tmp_path / 'src', MINIMAL_TFVARS)
    source = root / 'templates' / 'terraform' / 'aws'

    process_files(source, tmp_path / 'on', {'services': {'eks': {'enabled': True}}})
    process_files(source, tmp_path / 'off', {'services': {'eks': {'enabled': False}}})

    assert 'module "eks"' in (tmp_path / 'on' / 'main.tf').read_text()
    assert '# module "eks"' in (tmp_path / 'off' / 'main.tf').read_text()


# --- @module inertness in generation ----------------------------------------

def test_module_decorator_leaves_generated_output_untouched(tmp_path):
    source = tmp_path / 'src'
    build_templates(source, MINIMAL_TFVARS)
    process_files(source / 'templates' / 'terraform' / 'aws', tmp_path / 'without', {})

    build_templates(source, '# @module services.eks | displayName=Kubernetes\n' + MINIMAL_TFVARS)
    process_files(source / 'templates' / 'terraform' / 'aws', tmp_path / 'with', {})

    without = (tmp_path / 'without' / 'terraform.auto.tfvars').read_text()
    with_module = (tmp_path / 'with' / 'terraform.auto.tfvars').read_text()
    assert with_module == '# @module services.eks | displayName=Kubernetes\n' + without


def test_module_inside_a_disabled_section_is_not_uncommented(tmp_path):
    """The un-comment exclusion at processing.py must cover @module, or toggling
    a section on turns the decorator into Terraform code."""
    source = tmp_path / 'src'
    tf = (
        '# @section services.eks.enabled begin\n'
        '# @module services.eks | displayName=Kubernetes\n'
        '# module "eks" {}\n'
        '# @section services.eks.enabled end\n'
    )
    build_templates(source, MINIMAL_TFVARS, tf=tf)
    process_files(
        source / 'templates' / 'terraform' / 'aws',
        tmp_path / 'out',
        {'services': {'eks': {'enabled': True}}},
    )

    rendered = (tmp_path / 'out' / 'main.tf').read_text()
    assert '# @module services.eks | displayName=Kubernetes' in rendered
    assert 'module "eks" {}' in rendered


# --- Golden file ------------------------------------------------------------

def test_golden_catalog_matches(tmp_path):
    """Guards the output shape against accidental change.

    The fixture is a verbatim slice of the production aws templates rather than
    the whole file: it exercises both naming conventions and every inferred
    type, without coupling this suite to every edit in the templates repo.
    """
    fixture = Path(__file__).parent / 'fixtures' / 'catalog'
    catalog = extract_catalog(fixture)
    expected = json.loads((Path(__file__).parent / 'fixtures' / 'catalog-golden.json').read_text())

    # Absolute paths differ per checkout; the shape and values are what matter.
    for service in catalog['services'].values():
        for field in service['fields'].values():
            field.pop('file', None)
    for field in catalog['global']['fields'].values():
        field.pop('file', None)

    assert catalog['errors'] == []
    assert catalog['services'] == expected['services']
    assert catalog['global'] == expected['global']


# --- CLI --------------------------------------------------------------------

def test_cli_exits_zero_on_a_clean_tree(tmp_path, capsys):
    assert run_cli([str(build_templates(tmp_path, MINIMAL_TFVARS)), '--strict']) == 0
    assert json.loads(capsys.readouterr().out)['schemaVersion'] == SCHEMA_VERSION


def test_cli_exits_non_zero_on_errors_under_strict(tmp_path, capsys):
    root = build_templates(tmp_path, '# @param services.eks.tags\neks_tags = []\n')
    assert run_cli([str(root), '--strict']) == 1
    assert 'UNKNOWN_TYPE' in capsys.readouterr().err


def test_cli_reports_errors_but_succeeds_without_strict(tmp_path, capsys):
    root = build_templates(tmp_path, '# @param services.eks.tags\neks_tags = []\n')
    assert run_cli([str(root)]) == 0
    assert 'UNKNOWN_TYPE' in capsys.readouterr().err


def test_cli_writes_to_a_file(tmp_path):
    root = build_templates(tmp_path, MINIMAL_TFVARS)
    destination = tmp_path / 'catalog.json'
    assert run_cli([str(root), '--output', str(destination)]) == 0
    assert json.loads(destination.read_text())['services']['eks']['key'] == 'eks'


def test_extract_catalog_is_reachable_as_a_module(tmp_path):
    """OP-205's CI gate invokes this as a subprocess, so the entry point has to
    work from a clean interpreter, not just from an in-process import."""
    root = build_templates(tmp_path, MINIMAL_TFVARS)
    result = subprocess.run(
        [sys.executable, '-m', 'injecto.main', '--extract-catalog', str(root), '--strict'],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['schemaVersion'] == SCHEMA_VERSION
