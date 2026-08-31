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

from injecto.processing import deep_merge, format_value_for_file, process_files


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
        " | displayName=Kubernetes version | options=[1.31,1.32]\n"
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
        " | displayName=Some human label",
        " | options=[a,b,c] | default=a",
        "|valueType=number|min=1|max=10",
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


# --- Multi-line values (OP-221) ---

MULTILINE_TEMPLATE = (
    "# @param services.eks.defaultNodeGroupIamAdditionalPolicies\n"
    "default_node_group_iam_additional_policies = {\n"
    '  AmazonEBSCSIDriverPolicy = "arn:aws:iam::aws:policy/EBS"\n'
    "}\n"
)


def test_supplying_a_multiline_value_raises_instead_of_corrupting(tmp_path):
    """The whole point: never emit a half-rewritten block with exit 0.

    Before this guard, substituting here produced
    `... = {"CiGate": "arn:..."}` followed by the orphaned map body and its
    closing brace — terraform that fails to parse, with no warning.
    """
    data = {
        "services": {
            "eks": {"defaultNodeGroupIamAdditionalPolicies": {"CiGate": "arn:aws:iam::aws:policy/RO"}}
        }
    }
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    (input_dir / "terraform.auto.tfvars").write_text(MULTILINE_TEMPLATE, encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        process_files(input_dir, output_dir, data)

    message = str(excinfo.value)
    assert "terraform.auto.tfvars:2" in message
    assert "services.eks.defaultNodeGroupIamAdditionalPolicies" in message

    # And the block was left intact rather than half-rewritten.
    written = (output_dir / "terraform.auto.tfvars").read_text(encoding="utf-8")
    assert written == MULTILINE_TEMPLATE


def test_unsupplied_multiline_param_is_untouched_and_does_not_raise(tmp_path):
    """Proves the guard is inert for the templates as they ship today.

    Nothing in prepareInjectoData sends this path, so production generation must
    behave exactly as before — the guard only fires once someone supplies a value.
    """
    out = run(tmp_path, {"terraform.auto.tfvars": MULTILINE_TEMPLATE}, EKS_DATA)
    assert out["terraform.auto.tfvars"] == MULTILINE_TEMPLATE


def test_single_line_bracketed_value_still_substitutes(tmp_path):
    """A balanced map/list on one line is not multi-line and must still work."""
    template = "# @param cfg.tags\ntags = {}\n"
    data = {"cfg": {"tags": {"Name": "prod"}}}
    out = run(tmp_path, {"main.tf": template}, data)["main.tf"]
    assert out.splitlines()[1] == 'tags = {"Name": "prod"}'


def test_bracket_inside_a_quoted_default_does_not_trigger_the_guard(tmp_path):
    """String literals are blanked before counting, so a quoted `{` is not an opener."""
    template = '# @param cfg.pattern\npattern = "{"\n'
    out = run(tmp_path, {"main.tf": template}, {"cfg": {"pattern": "[a-z]+"}})["main.tf"]
    assert out.splitlines()[1] == 'pattern = "[a-z]+"'


def test_bracket_inside_a_trailing_comment_does_not_trigger_the_guard(tmp_path):
    template = '# @param cfg.value\nvalue = "old"  # see runbook section {3}\n'
    out = run(tmp_path, {"main.tf": template}, {"cfg": {"value": "new"}})["main.tf"]
    assert out.splitlines()[1] == 'value = "new"  # see runbook section {3}'


def test_every_offending_site_is_reported_not_just_the_first(tmp_path):
    files = {"a.tfvars": MULTILINE_TEMPLATE, "b.tfvars": MULTILINE_TEMPLATE}
    data = {"services": {"eks": {"defaultNodeGroupIamAdditionalPolicies": {"x": "y"}}}}
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    for name, content in files.items():
        (input_dir / name).write_text(content, encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        process_files(input_dir, tmp_path / "out", data)

    assert "a.tfvars:2" in str(excinfo.value)
    assert "b.tfvars:2" in str(excinfo.value)


# --- @section nesting and mismatched markers (OP-192) ---


def test_nested_sections_apply_the_innermost_condition(tmp_path):
    template = (
        "# @section services.eks.enabled begin\n"
        "outer = true\n"
        "# @section services.eks.karpenterEnabled begin\n"
        "inner = true\n"
        "# @section services.eks.karpenterEnabled end\n"
        "after_inner = true\n"
        "# @section services.eks.enabled end\n"
    )
    data = {"services": {"eks": {"enabled": True, "karpenterEnabled": False}}}
    out = run(tmp_path, {"main.tf": template}, data)["main.tf"]
    lines = out.splitlines()
    assert lines[1] == "outer = true"
    assert lines[3] == "# inner = true"
    # Popping the inner section restores the outer one's condition.
    assert lines[5] == "after_inner = true"


def test_mismatched_section_end_warns_and_leaves_the_stack_alone(tmp_path, caplog):
    template = (
        "# @section services.eks.karpenterEnabled begin\n"
        "body = true\n"
        "# @section services.eks.somethingElse end\n"
    )
    data = {"services": {"eks": {"karpenterEnabled": False}}}
    with caplog.at_level("WARNING"):
        out = run(tmp_path, {"main.tf": template}, data)["main.tf"]

    assert any("Mismatched" in r.message for r in caplog.records)
    # The unclosed section stays active, so its body is still commented.
    assert "# body = true" in out


# --- format_value_for_file (OP-192) ---


@pytest.mark.parametrize(
    "value,expected",
    [
        ("plain", '"plain"'),
        ("", '""'),
        ("a:b", '"a:b"'),
        ('"already"', '"already"'),  # pre-quoted values pass through untouched
        ("'single'", "'single'"),
        (True, "true"),
        (False, "false"),
        (0, "0"),
        (3.5, "3.5"),
        (None, "None"),
        ([1, "a"], '[1, "a"]'),
        ({"k": "v"}, '{"k": "v"}'),
    ],
)
def test_format_value_for_file(value, expected):
    assert format_value_for_file(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ('say "hi"', '"say \\"hi\\""'),
        ("with\\backslash", '"with\\\\backslash"'),
        ("multi\nline", '"multi\\nline"'),
        ("tab\there", '"tab\\there"'),
    ],
)
def test_format_value_for_file_escapes_dangerous_characters(value, expected):
    """Fixed under OP-175 — these used to emit broken output.

    The naive `f'"{value}"'` form left an embedded quote unescaped (invalid HCL),
    a backslash unescaped (invalid escape), and a newline literal — which split
    the value across two lines, the same corruption class as OP-221 arriving from
    the value side instead of the template side.
    """
    assert format_value_for_file(value) == expected


def test_escaping_does_not_change_any_value_that_already_worked():
    """The fix must be byte-identical wherever the old form was already correct."""
    for value in ["plain", "", "a:b", "1.32", "my-cluster", "eu-west-1",
                  "arn:aws:iam::aws:policy/ReadOnlyAccess"]:
        assert format_value_for_file(value) == f'"{value}"'


def test_a_quoted_value_still_survives_the_round_trip_into_a_file(tmp_path):
    """End-to-end: an embedded quote must land as valid, single-line HCL."""
    template = '# @param cfg.description\ndescription = "old"\n'
    out = run(tmp_path, {"main.tf": template}, {"cfg": {"description": 'say "hi"'}})["main.tf"]
    assert out.splitlines()[1] == 'description = "say \\"hi\\""'
    assert len(out.splitlines()) == 2  # the value did not break the line


# --- deep_merge (OP-192) ---


def test_deep_merge_merges_nested_dicts_and_keeps_untouched_keys():
    target = {"a": {"b": 1}, "keep": 1}
    assert deep_merge(target, {"a": {"c": 2}}) == {"a": {"b": 1, "c": 2}, "keep": 1}


def test_deep_merge_later_source_wins_on_scalar_conflict():
    assert deep_merge({"x": 1}, {"x": 2}) == {"x": 2}


def test_deep_merge_replaces_a_scalar_with_a_dict():
    assert deep_merge({"x": 5}, {"x": {"now": "dict"}}) == {"x": {"now": "dict"}}


def test_deep_merge_replaces_lists_wholesale_rather_than_concatenating():
    """Tier files override list values; they do not append to them."""
    assert deep_merge({"list": [1, 2]}, {"list": [3]}) == {"list": [3]}


def test_deep_merge_mutates_the_target_in_place():
    target = {"a": 1}
    result = deep_merge(target, {"b": 2})
    assert result is target
    assert target == {"a": 1, "b": 2}


def test_deep_merge_deep_copies_dicts_that_replace_a_scalar():
    """Guards against a later mutation of the source leaking into the target."""
    source_branch = {"nested": {"v": 1}}
    target = deep_merge({"x": 5}, {"x": source_branch})
    source_branch["nested"]["v"] = 999
    assert target["x"]["nested"]["v"] == 1


# --- File handling ---


def test_unmodified_files_are_copied_to_the_output_tree(tmp_path):
    files = {
        "static.txt": "nothing to substitute here\n",
        "nested/main.tf": '# @param services.eks.kubernetesVersion\nv = "old"\n',
    }
    out = run(tmp_path, files, EKS_DATA)
    assert out["static.txt"] == "nothing to substitute here\n"
    assert 'v = "1.32"' in out["nested/main.tf"]
