import pytest
from pydantic import ValidationError

from tools.python_analysis import analyze_numeric_data


def test_analyze_numeric_data_returns_descriptive_statistics():
    result = analyze_numeric_data(
        [{"ventas": 10}, {"ventas": 20}, {"ventas": 30}]
    )

    assert result["row_count"] == 3
    assert result["columns"] == ["ventas"]
    assert result["summary"]["ventas"]["mean"] == 20.0


def test_analyze_numeric_data_rejects_empty_rows():
    with pytest.raises(ValidationError):
        analyze_numeric_data([])


def test_analyze_numeric_data_rejects_inconsistent_columns():
    with pytest.raises(ValidationError):
        analyze_numeric_data([{"ventas": 10}, {"coste": 20}])
