"""Regression corpus for the @param / @section substitution engine.

Locks down the CURRENT behaviour of src/processing.py. Every test here must pass
against unmodified production code — this suite is the safety net that later
changes (OP-221 multi-line values, OP-204 catalog extractor) are checked against,
so it deliberately contains no fixes of its own.

The load-bearing case is the enriched-decorator one: the runtime module catalog
(OP-202) extends the grammar to `# @param <path> | key=value | ...`, and that
only works without a lockstep deploy if the deployed parser already ignores the
tail. That is asserted here rather than assumed.
"""

from pathlib import Path

import pytest

from processing import process_files


def run(tmp_path: Path, files: dict, data: dict) -> dict:
    """Process `files` through the engine and return the resulting output tree.

    Uses a separate output dir (the API path) rather than in-place editing, so an
    unmodified file is copied and still appears in the result.
    """
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


EKS_DATA = {"services": {"eks": {"kubernetesVersion": "1.32", "enabled": True}}}


# --- @param: enriched decorator grammar is inert (OP-202 precondition) ---


def test_enriched_param_tail_substitutes_identically_to_bare_param(tmp_path):
    """`# @param path | key=value ...` must substitute exactly like `# @param path`."""
    bare = '# @param services.eks.kubernetesVersion\ncluster_version = "1.29"\n'
    enriched = (
        "# @param services.eks.kubernetesVersion | type=dropdown"
        " | label=Kubernetes version | options=[1.31,1.32]\n"
        'cluster_version = "1.29"\n'
    )

    bare_out = run(tmp_path / "a", {"main.tf": bare}, EKS_DATA)["main.tf"]
    enriched_out = run(tmp_path / "b", {"main.tf": enriched}, EKS_DATA)["main.tf"]

    # The value line is byte-identical; only the decorator line differs, and it is
    # passed through untouched in both.
    assert bare_out.splitlines()[1] == enriched_out.splitlines()[1]
    assert bare_out.splitlines()[1] == 'cluster_version = "1.32"'
    assert enriched_out.splitlines()[0].endswith("options=[1.31,1.32]")


@pytest.mark.parametrize(
    "tail",
    [
        " | type=dropdown",
        " | label=Some human label",
        " | options=[a,b,c] | default=a",
        "|type=number|min=1|max=10",
    ],
)
def test_param_path_parsing_stops_at_the_enrichment_tail(tmp_path, tail):
    template = f"# @param services.eks.kubernetesVersion{tail}\nversion = \"old\"\n"
    out = run(tmp_path, {"main.tf": template}, EKS_DATA)["main.tf"]
    assert 'version = "1.32"' in out


# --- @param: substitution targeting ---


def test_param_substitutes_only_the_immediately_following_line(tmp_path):
    template = (
        "# @param services.eks.kubernetesVersion\n"
        'first = "old"\n'
        'second = "old"\n'
    )
    out = run(tmp_path, {"main.tf": template}, EKS_DATA)["main.tf"]
    assert 'first = "1.32"' in out
    assert 'second = "old"' in out


def test_param_does_not_substitute_a_commented_next_line(tmp_path):
    """Guards the processing.py skip: a commented value line is left alone."""
    template = '# @param services.eks.kubernetesVersion\n# version = "old"\n'
    out = run(tmp_path, {"main.tf": template}, EKS_DATA)["main.tf"]
    assert '# version = "old"' in out
    assert "1.32" not in out


def test_param_preserves_a_trailing_comment_on_the_value_line(tmp_path):
    template = (
        "# @param services.eks.kubernetesVersion\n"
        'version = "old"  # pinned by platform team\n'
    )
    out = run(tmp_path, {"main.tf": template}, EKS_DATA)["main.tf"]
    assert out.splitlines()[1] == 'version = "1.32"  # pinned by platform team'


def test_param_substitutes_the_yaml_key_form(tmp_path):
    template = "# @param services.eks.kubernetesVersion\nkubernetesVersion: old\n"
    out = run(tmp_path, {"values.yaml": template}, EKS_DATA)["values.yaml"]
    assert out.splitlines()[1] == 'kubernetesVersion: "1.32"'


def test_param_substitutes_a_yaml_list_item(tmp_path):
    template = "# @param services.eks.kubernetesVersion\n  - version: old\n"
    out = run(tmp_path, {"main.tf": template}, EKS_DATA)["main.tf"]
    assert out.splitlines()[1] == '  - version: "1.32"'


@pytest.mark.parametrize(
    "value,expected",
    [
        ("prod-cluster", '"prod-cluster"'),
        (True, "true"),
        (False, "false"),
        (3, "3"),
        (["a", "b"], '["a", "b"]'),
    ],
)
def test_param_value_formatting_by_type(tmp_path, value, expected):
    template = '# @param cfg.value\nsetting = "placeholder"\n'
    out = run(tmp_path, {"main.tf": template}, {"cfg": {"value": value}})["main.tf"]
    assert out.splitlines()[1] == f"setting = {expected}"


# --- @param: missing data path ---


def test_missing_param_path_retains_the_template_default_and_warns(tmp_path, caplog):
    """Unresolved @param is warning-only — the template default ships as-is.

    This is the failure mode that makes an unresolved @param unsafe (the customer
    silently gets OpenPrime's default) while an unresolved @section is safe.
    """
    template = '# @param services.eks.doesNotExist\nversion = "template-default"\n'
    with caplog.at_level("WARNING"):
        out = run(tmp_path, {"main.tf": template}, EKS_DATA)["main.tf"]

    assert 'version = "template-default"' in out
    assert any("services.eks.doesNotExist" in r.message for r in caplog.records)


def test_param_without_a_key_value_next_line_warns_and_changes_nothing(tmp_path):
    template = "# @param services.eks.kubernetesVersion\nresource \"aws_eks_cluster\" {\n"
    out = run(tmp_path, {"main.tf": template}, EKS_DATA)["main.tf"]
    assert out == template


# --- @section: toggling ---


def test_section_disabled_comments_out_its_body(tmp_path):
    template = (
        "# @section services.eks.karpenterEnabled begin\n"
        "karpenter_enabled = true\n"
        "# @section services.eks.karpenterEnabled end\n"
    )
    data = {"services": {"eks": {"karpenterEnabled": False}}}
    out = run(tmp_path, {"main.tf": template}, data)["main.tf"]
    assert "# karpenter_enabled = true" in out


def test_section_enabled_uncomments_its_body(tmp_path):
    template = (
        "# @section services.eks.karpenterEnabled begin\n"
        "# karpenter_enabled = true\n"
        "# @section services.eks.karpenterEnabled end\n"
    )
    data = {"services": {"eks": {"karpenterEnabled": True}}}
    out = run(tmp_path, {"main.tf": template}, data)["main.tf"]
    assert "karpenter_enabled = true" in out
    assert "# karpenter_enabled" not in out


def test_missing_section_path_is_treated_as_disabled(tmp_path):
    """Unresolved @section switches its block OFF — the safe direction."""
    template = (
        "# @section services.eks.doesNotExist begin\n"
        "dangerous = true\n"
        "# @section services.eks.doesNotExist end\n"
    )
    out = run(tmp_path, {"main.tf": template}, EKS_DATA)["main.tf"]
    assert "# dangerous = true" in out


def test_section_marker_lines_are_never_toggled(tmp_path):
    template = (
        "# @section services.eks.enabled begin\n"
        "enabled = true\n"
        "# @section services.eks.enabled end\n"
    )
    out = run(tmp_path, {"main.tf": template}, EKS_DATA)["main.tf"]
    lines = out.splitlines()
    assert lines[0] == "# @section services.eks.enabled begin"
    assert lines[2] == "# @section services.eks.enabled end"


def test_section_uncommenting_never_activates_a_param_or_section_directive(tmp_path):
    """Guards the un-comment exclusion list.

    Without it, enabling a section would strip the `#` from a nested `@param`
    decorator, turning it into a bare `@param ...` line in the customer's
    Terraform — syntactically invalid and no longer a directive.
    """
    template = (
        "# @section services.eks.enabled begin\n"
        "# @param services.eks.kubernetesVersion\n"
        '# version = "old"\n'
        "# @section services.eks.nested begin\n"
        "# @section services.eks.nested end\n"
        "# @section services.eks.enabled end\n"
    )
    out = run(tmp_path, {"main.tf": template}, EKS_DATA)["main.tf"]
    assert "# @param services.eks.kubernetesVersion" in out
    assert "\n@param" not in out
    assert "\n@section" not in out


def test_section_blank_lines_are_left_alone(tmp_path):
    template = (
        "# @section services.eks.karpenterEnabled begin\n"
        "karpenter = true\n"
        "\n"
        "# @section services.eks.karpenterEnabled end\n"
    )
    data = {"services": {"eks": {"karpenterEnabled": False}}}
    out = run(tmp_path, {"main.tf": template}, data)["main.tf"]
    assert out.splitlines()[2] == ""


# --- File handling ---


def test_unmodified_files_are_copied_to_the_output_tree(tmp_path):
    files = {
        "static.txt": "nothing to substitute here\n",
        "nested/main.tf": '# @param services.eks.kubernetesVersion\nv = "old"\n',
    }
    out = run(tmp_path, files, EKS_DATA)
    assert out["static.txt"] == "nothing to substitute here\n"
    assert 'v = "1.32"' in out["nested/main.tf"]
