"""Generation must fail loudly rather than hand over a silently incomplete tree.

Before OP-214 a file that threw during processing was logged and then simply
absent from the output, while the run reported success — the customer received
infrastructure with pieces missing and a green result.
"""

from pathlib import Path

import pytest

import injecto.processing as processing
from injecto.processing import GenerationError, process_files


def build(tmp_path, files):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    for name, content in files.items():
        target = input_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return input_dir, tmp_path / "out"


@pytest.fixture
def exploding_on(monkeypatch):
    """Make processing of one named file raise, leaving the others untouched."""

    def _apply(target_name):
        real = processing.format_value_for_file

        def fake(value):
            import inspect

            for frame in inspect.stack():
                rel = frame.frame.f_locals.get("relative_path")
                if rel is not None and str(rel) == target_name:
                    raise RuntimeError("simulated per-file failure")
            return real(value)

        monkeypatch.setattr(processing, "format_value_for_file", fake)

    return _apply


DATA = {"a": {"b": "NEW"}}
TEMPLATE = '# @param a.b\nx = "old"\n'


def test_a_file_that_fails_to_process_raises_instead_of_vanishing(tmp_path, exploding_on):
    exploding_on("bad.tf")
    input_dir, output_dir = build(tmp_path, {"good.tf": TEMPLATE, "bad.tf": TEMPLATE})

    with pytest.raises(GenerationError) as excinfo:
        process_files(input_dir, output_dir, DATA)

    assert excinfo.value.code == "FILES_FAILED"
    assert any("bad.tf" in d for d in excinfo.value.details)
    # The good file still processed — one bad file must not hide the others.
    assert (output_dir / "good.tf").exists()
    # And the failure is visible rather than inferred from a missing file.
    assert not (output_dir / "bad.tf").exists()


def test_every_failing_file_is_reported_not_just_the_first(tmp_path, monkeypatch):
    real = processing.format_value_for_file

    def always_boom(value):
        raise RuntimeError("simulated per-file failure")

    monkeypatch.setattr(processing, "format_value_for_file", always_boom)
    input_dir, output_dir = build(tmp_path, {"a.tf": TEMPLATE, "b.tf": TEMPLATE})

    with pytest.raises(GenerationError) as excinfo:
        process_files(input_dir, output_dir, DATA)

    assert len(excinfo.value.details) == 2
    monkeypatch.setattr(processing, "format_value_for_file", real)


def test_output_missing_a_file_raises_a_count_mismatch(tmp_path, monkeypatch):
    """Catches a drop that happens without an exception being raised."""
    input_dir, output_dir = build(tmp_path, {"a.tf": TEMPLATE, "b.txt": "static\n"})

    real_copy = processing.shutil.copy2

    def skip_static(src, dst, *args, **kwargs):
        if Path(src).name == "b.txt":
            return dst  # pretend it was copied
        return real_copy(src, dst, *args, **kwargs)

    monkeypatch.setattr(processing.shutil, "copy2", skip_static)

    with pytest.raises(GenerationError) as excinfo:
        process_files(input_dir, output_dir, DATA)

    assert excinfo.value.code == "FILE_COUNT_MISMATCH"
    assert "2 files in, 1 files out" in excinfo.value.details[0]


def test_a_clean_run_still_succeeds_and_keeps_every_file(tmp_path):
    """The guard must be inert for a normal generation."""
    files = {"a.tf": TEMPLATE, "nested/b.tf": TEMPLATE, "static.txt": "unchanged\n"}
    input_dir, output_dir = build(tmp_path, files)

    process_files(input_dir, output_dir, DATA)

    produced = sorted(str(p.relative_to(output_dir)) for p in output_dir.rglob("*") if p.is_file())
    assert produced == ["a.tf", "nested/b.tf", "static.txt"]
    assert 'x = "NEW"' in (output_dir / "a.tf").read_text()


def test_generation_error_is_a_valueerror_for_existing_callers():
    err = GenerationError("CODE", "message", ["detail"])
    assert isinstance(err, ValueError)
    assert err.code == "CODE"
    assert err.details == ["detail"]
    assert "detail" in str(err)
