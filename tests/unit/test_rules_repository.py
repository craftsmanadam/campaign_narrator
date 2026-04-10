"""Unit tests for the rules repository."""

from pathlib import Path

from campaignnarrator.repositories.rules_repository import RulesRepository


def test_rules_repository_loads_rule_index_and_topic_markdown(
    tmp_path: Path,
) -> None:
    """Rules repositories should be root-configurable and file-backed."""

    rules_root = tmp_path / "rules"
    (rules_root / "generated").mkdir(parents=True)
    (rules_root / "source" / "adjudication").mkdir(parents=True)
    (rules_root / "generated" / "rule_index.json").write_text(
        '{"stealth": ["stealth.md", "checks.md"]}'
    )
    (rules_root / "source" / "adjudication" / "core_resolution.md").write_text(
        "# Core Resolution\n\nFollow the rules."
    )

    repository = RulesRepository(rules_root)

    assert repository.load_rule_index() == {"stealth": ["stealth.md", "checks.md"]}
    assert (
        repository.load_topic_markdown("source/adjudication/core_resolution.md")
        == "# Core Resolution\n\nFollow the rules."
    )


def test_rules_repository_rejects_paths_outside_root(tmp_path: Path) -> None:
    """Rules topics must not escape the configured root."""

    rules_root = tmp_path / "rules"
    (rules_root / "generated").mkdir(parents=True)
    (tmp_path / "escape.md").write_text("outside")
    repository = RulesRepository(rules_root)

    for path in [Path("/etc/passwd"), "../outside.md", "source/../../escape.md"]:
        try:
            repository.load_topic_markdown(path)
        except ValueError:
            continue
        raise AssertionError
