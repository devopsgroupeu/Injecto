"""TRIM_DECORATOR_ATTRS: keep wizard metadata out of the generated repo (OP-226).

Decorator lines are copied verbatim into the customer's repository. Once the
templates carry `label`, `description` and `options` (OP-206), that metadata
would ship to every customer. The switch removes the attribute tail and only
the tail.

The line must survive: tests/gate.py in openprime-infra-templates locates each
value in the generated tree by the line number it scanned from the template, so
deleting decorator lines would shift everything after them.
"""

from pathlib import Path

import pytest

from injecto import processing
from injecto.processing import process_files


@pytest.fixture
def trim(monkeypatch):
    """Turn the switch on; it is read at import time, so patch the module."""
    monkeypatch.setattr(processing, "TRIM_DECORATOR_ATTRS", True)


def run(tmp_path: Path, files: dict, data: dict) -> dict:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    for name, content in files.items():
        target = input_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    process_files(input_dir, output_dir, data)

    return {
        str(p.relative_to(output_dir)): p.read_text(encoding="utf-8")
        for p in output_dir.rglob("*")
        if p.is_file()
    }


ENRICHED = (
    "# @param services.eks.kubernetesVersion | valueType=string | displayName=Version\n"
    'kubernetes_version = "1.30"\n'
)
DATA = {"services": {"eks": {"kubernetesVersion": "1.32", "enabled": True}}}


def test_off_by_default_leaves_the_tail_alone(tmp_path):
    """The default must not change what production already emits."""
    assert processing.TRIM_DECORATOR_ATTRS is False
    out = run(tmp_path, {"a.tfvars": ENRICHED}, DATA)
    assert "| valueType=string | displayName=Version" in out["a.tfvars"]


def test_on_removes_the_tail_and_keeps_the_line(tmp_path, trim):
    out = run(tmp_path, {"a.tfvars": ENRICHED}, DATA)
    assert out["a.tfvars"] == (
        "# @param services.eks.kubernetesVersion\n"
        'kubernetes_version = "1.32"\n'
    )


def test_line_count_is_unchanged(tmp_path, trim):
    """gate.py addresses the output by template line number."""
    source = ENRICHED + "\n# @module services.rds | displayName=RDS\n" + 'rds_engine = "postgres"\n'
    out = run(tmp_path, {"a.tfvars": source}, DATA)
    assert len(out["a.tfvars"].splitlines()) == len(source.splitlines())


def test_a_file_whose_only_change_is_a_trim_is_still_written(tmp_path, trim):
    """The load-bearing case.

    processing.py copies a file verbatim when nothing modified it. A file with
    an enriched decorator but no resolvable value has no substitution and no
    section toggle, so unless the trim sets file_was_modified it takes the copy
    path and ships the tail regardless of the switch.
    """
    untouched = "# @param services.sqs.queueNames | valueType=list\nsqs_queue_names = []\n"
    out = run(tmp_path, {"a.tfvars": untouched}, {"services": {"eks": {"enabled": True}}})
    assert out["a.tfvars"] == "# @param services.sqs.queueNames\nsqs_queue_names = []\n"


def test_section_markers_are_untouched(tmp_path, trim):
    """The trim is for @param and @module only.

    The pipe on the begin marker is what makes this test load-bearing: without
    it the markers survive whether or not @section is in the trim, so the test
    would pass against an implementation that strips them.
    """
    source = (
        "# @section services.eks.enabled begin | note=keep\n"
        "eks_enabled = true\n"
        "# @section services.eks.enabled end\n"
    )
    out = run(tmp_path, {"a.tfvars": source}, DATA)
    assert "# @section services.eks.enabled begin | note=keep" in out["a.tfvars"]
    assert "# @section services.eks.enabled end" in out["a.tfvars"]


def test_trailing_text_that_is_not_an_attribute_tail_survives(tmp_path, trim):
    """Only a tail introduced by '|' is attribute syntax; prose is not ours to drop."""
    source = "# @param services.eks.kubernetesVersion see runbook\nkubernetes_version = \"1.30\"\n"
    out = run(tmp_path, {"a.tfvars": source}, DATA)
    assert "see runbook" in out["a.tfvars"]


def test_substituted_values_are_identical_with_and_without_the_switch(tmp_path, monkeypatch):
    """The switch must touch comments only, never a value."""
    monkeypatch.setattr(processing, "TRIM_DECORATOR_ATTRS", False)
    off = run(tmp_path / "off", {"a.tfvars": ENRICHED}, DATA)
    monkeypatch.setattr(processing, "TRIM_DECORATOR_ATTRS", True)
    on = run(tmp_path / "on", {"a.tfvars": ENRICHED}, DATA)

    def values(text):
        return [l for l in text.splitlines() if not l.lstrip().startswith("#")]

    assert values(off["a.tfvars"]) == values(on["a.tfvars"])
