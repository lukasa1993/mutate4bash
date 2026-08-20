from pathlib import Path

from mutate4bash.core import enumerate_mutations, run_mutations


def test_ignores_comments_and_strings(tmp_path: Path) -> None:
    source = tmp_path / "sample.sh"
    source.write_text("# true == false\ntext='true && false'\n[[ $x == yes ]] && true\n", encoding="utf-8")
    assert [item.original for item in enumerate_mutations(source, tmp_path)] == ["==", "&&", "true"]


def test_restores_source(tmp_path: Path) -> None:
    source = tmp_path / "sample.sh"
    original = "true\n"
    source.write_text(original, encoding="utf-8")
    mutation = enumerate_mutations(source, tmp_path)[0]
    result = run_mutations(tmp_path, [mutation], "false", 5)[0]
    assert result.status == "killed"
    assert source.read_text(encoding="utf-8") == original
