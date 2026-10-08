import audit


def records(*branches: str | None) -> list[audit.Record]:
    """Records oldest first, one per branch name given (None: a detached HEAD)."""
    return [
        audit.Record(commit=f"c{i}", tree=f"t{i}", branch=branch, head=f"h{i}")
        for i, branch in enumerate(branches)
    ]


def commits(history: list[audit.Record]) -> list[str]:
    return [record.commit for record in history]


def test_one_branch_is_its_own_history() -> None:
    ledger = records("feat", "feat", "feat", "feat", "feat")

    assert commits(audit.effective_history(ledger)) == ["c0", "c1", "c2", "c3", "c4"]


def test_a_branch_created_mid_work_includes_the_line_it_came_from() -> None:
    ledger = records("main", "main", "feat", "feat")

    assert commits(audit.effective_history(ledger)) == ["c0", "c1", "c2", "c3"]


def test_a_visit_to_another_branch_and_back_is_skipped() -> None:
    ledger = records("feat", "feat", "other", "other", "feat")

    assert commits(audit.effective_history(ledger)) == ["c0", "c1", "c4"]


def test_a_rename_keeps_one_continuous_line() -> None:
    ledger = records("feat", "feat", "feature", "feature")

    assert commits(audit.effective_history(ledger)) == ["c0", "c1", "c2", "c3"]


def test_detached_records_of_a_rebase_are_skipped() -> None:
    ledger = records("feat", "feat", None, None, "feat")

    assert commits(audit.effective_history(ledger)) == ["c0", "c1", "c4"]


def test_a_branch_with_no_record_stands_at_the_newest_and_has_the_line_it_came_from() -> None:
    # `git checkout -b feat` with the tree unchanged adds no record (FR-002).
    ledger = records("main", "main")

    assert commits(audit.effective_history(ledger)) == ["c0", "c1"]


def test_a_branch_switched_to_without_a_tree_change_takes_the_line_of_the_newest_record() -> None:
    # feat2 moved to feat's state (a fast-forward), then checked out: no record. Its work now is
    # feat's line, which came from feat2's own record.
    ledger = records("feat2", "feat", "feat")

    assert commits(audit.effective_history(ledger)) == ["c0", "c1", "c2"]
