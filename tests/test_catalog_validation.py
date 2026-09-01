#!/usr/bin/env python3
r"""Field validation patterns carried from the templates into the catalog.

Why this exists. The static wizard config declared
``validation: {pattern: /^(\d{1,3}\.){3}\d{1,3}\/\d{1,2}$/}`` on
``services.vpc.cidr``; the catalog carried nothing. Hydrating from the catalog
therefore DROPPED the only check on a VPC network range -- and it landed in the
same window as openprime-app-backend 1.15.0 removing its own CIDR validator, so
after the cutover nothing would have validated it at any layer.

Neither gate could see it: ``catalog-parity.js`` compared service keys, field
keys, types and defaults, and never ``validation``.
"""

import re

from injecto.catalog import extract_catalog
from injecto.decorators import DecoratorError, parse_attrs
from tests.test_catalog import build_templates, codes

import pytest

CIDR = r'^(\d{1,3}\.){3}\d{1,3}/\d{1,2}$'

VPC_TF = """\
# @section services.vpc.enabled begin
module "vpc" {
  cidr = var.vpc_cidr
}
# @section services.vpc.enabled end
"""


def tfvars(attrs: str = '') -> str:
    return (
        '# @module services.vpc | displayName=VPC\n'
        f'# @param services.vpc.cidr | displayName=CIDR Block{attrs}\n'
        'vpc_cidr = "10.0.0.0/16"\n'
    )


def cidr_field(tmp_path, attrs=''):
    catalog = extract_catalog(build_templates(tmp_path, tfvars(attrs), VPC_TF), 'aws')
    assert catalog['errors'] == [], catalog['errors']
    return catalog['services']['vpc']['fields']['cidr']


def test_pattern_is_emitted_nested_where_the_wizard_reads_it(tmp_path):
    # The frontend compiles `validation.pattern` to a RegExp. Emitting a flat
    # `pattern` instead would need a mapping layer in the app, and a translation
    # between what the catalog says and what the wizard reads is precisely where
    # the two drift apart.
    field = cidr_field(tmp_path, f' | pattern={CIDR}')
    assert field['validation'] == {'pattern': CIDR}
    # and not left lying around flat as well
    assert 'pattern' not in field


def test_the_emitted_pattern_matches_the_template_default(tmp_path):
    # A pattern that rejects the template's own default would reject every
    # environment that never touches the field.
    field = cidr_field(tmp_path, f' | pattern={CIDR}')
    assert re.match(field['validation']['pattern'], field['defaultValue'])


def test_the_pattern_rejects_what_it_is_meant_to_reject(tmp_path):
    # Control for the test above: a pattern that matched everything would pass
    # it and validate nothing.
    field = cidr_field(tmp_path, f' | pattern={CIDR}')
    assert not re.match(field['validation']['pattern'], 'not-a-cidr')


def test_a_field_without_a_pattern_carries_no_validation_key(tmp_path):
    # Absence must stay absence: emitting `validation: {}` would send the
    # frontend's `raw.validation?.pattern` check into undefined territory.
    field = cidr_field(tmp_path)
    assert 'validation' not in field


def test_an_uncompilable_pattern_fails_extraction(tmp_path):
    # Caught here on purpose. The frontend's compilePattern swallows a bad
    # pattern and renders the field with NO validation, so the browser would
    # ship an unvalidated field while every gate stayed green.
    catalog = extract_catalog(
        build_templates(tmp_path, tfvars(' | pattern=^(unclosed'), VPC_TF), 'aws'
    )
    assert 'BAD_PATTERN' in codes(catalog)


def test_an_empty_pattern_is_rejected_rather_than_emitted(tmp_path):
    catalog = extract_catalog(
        build_templates(tmp_path, tfvars(' | pattern='), VPC_TF), 'aws'
    )
    assert 'EMPTY_PATTERN' in codes(catalog)


def test_a_pipe_in_a_value_fails_loudly_and_says_why():
    # Attribute values are split on a bare '|', so regex alternation breaks the
    # decorator. It FAILS rather than silently truncating, which is the
    # behaviour we want -- but the default message ("'beta)$' is not key=value")
    # sends the author hunting a typo that does not exist.
    with pytest.raises(DecoratorError) as exc:
        parse_attrs('| pattern=^(alpha|beta)$')
    assert 'splits the decorator' in str(exc.value)


def test_options_json_still_parses_alongside_a_pattern():
    # `options` remains the one JSON-decoded attribute; adding `pattern` must
    # not disturb it.
    attrs = parse_attrs(
        '| type=dropdown | options=[{"value":"a","label":"A"}] | pattern=^a$'
    )
    assert attrs['options'] == [{'value': 'a', 'label': 'A'}]
    assert attrs['pattern'] == '^a$'
