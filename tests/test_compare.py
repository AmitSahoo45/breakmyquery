from bmq.compare import diff, equal
from bmq.db import Result


def test_bag_comparison_preserves_duplicate_multiplicity_and_ignores_row_order():
    expected = Result(["name"], [("Ravi",), ("Asha",), ("Ravi",)])
    assert equal(expected, Result(["other_alias"], [("Ravi",), ("Ravi",), ("Asha",)]))
    assert not equal(expected, Result(["name"], [("Ravi",), ("Asha",)]))


def test_ordered_comparison_detects_reordering():
    expected = Result(["n"], [(1,), (2,)])
    actual = Result(["n"], [(2,), (1,)])
    assert not equal(expected, actual, order_matters=True)


def test_normalization_rounds_floats_without_coercing_strings_or_nulls():
    expected = Result(["a", "b", "c", "d"], [(1, 2.1234561, None, "1")])
    assert equal(expected, Result(["w", "x", "y", "z"], [(1.0, 2.1234562, None, "1")]))
    assert not equal(expected, Result(["w", "x", "y", "z"], [(1, 2.1234561, "", 1)]))


def test_column_count_mismatch_is_detected_even_for_empty_results():
    expected = Result(["one"], [])
    actual = Result(["one", "two"], [])
    assert not equal(expected, actual)
    assert diff(expected, actual).column_count_mismatch


def test_diff_reports_missing_and_extra_rows_with_multiplicity():
    result = diff(Result(["n"], [(1,), (1,), (1,), (2,)]), Result(["n"], [(1,), (3,), (3,)]))
    assert not result.column_count_mismatch
    assert result.missing == [(1,), (1,), (2,)]
    assert result.extra == [(3,), (3,)]


def test_diff_uses_same_numeric_normalization_as_equality():
    result = diff(Result(["n"], [(1.1234561,)]), Result(["n"], [(1.1234562,)]))
    assert result.missing == []
    assert result.extra == []
