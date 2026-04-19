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
        '{"initiative": ["source/adjudication/initiative.md"], '
        '"combat": ["source/adjudication/combat.md"]}'
    )
    (rules_root / "source" / "adjudication" / "initiative.md").write_text(
        "# Initiative\n\nRoll initiative before acting."
    )
    (rules_root / "source" / "adjudication" / "combat.md").write_text(
        "# Combat\n\nResolve turns in initiative order."
    )

    repository = RulesRepository(rules_root)

    assert repository.load_rule_index() == {
        "initiative": ["source/adjudication/initiative.md"],
        "combat": ["source/adjudication/combat.md"],
    }
    assert repository.load_context_for_topics(("initiative", "combat")) == (
        "# Initiative\n\nRoll initiative before acting.",
        "# Combat\n\nResolve turns in initiative order.",
    )
    assert (
        repository.load_topic_markdown("source/adjudication/initiative.md")
        == "# Initiative\n\nRoll initiative before acting."
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


def test_rules_repository_marks_missing_context(tmp_path: Path) -> None:
    """Missing rule topics should return an explicit marker."""

    rules_root = tmp_path / "rules"
    (rules_root / "generated").mkdir(parents=True)
    (rules_root / "generated" / "rule_index.json").write_text(
        '{"initiative": ["source/adjudication/initiative.md"]}'
    )
    (rules_root / "source" / "adjudication").mkdir(parents=True)
    repository = RulesRepository(rules_root)

    assert repository.load_context_for_topics(("initiative", "combat")) == (
        "Missing rules context: initiative",
        "Missing rules context: combat",
    )
