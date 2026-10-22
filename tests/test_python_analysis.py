import pytest
from pydantic import ValidationError

from tools.python_analysis import (
    NumericAnalysisResult,
    analyze_numeric_data,
)


def test_analyze_numeric_data_returns_descriptive_statistics():
    """Comprueba que el análisis devuelve estadísticas correctas
    y que la respuesta cumple el esquema Pydantic.
    """
    result = analyze_numeric_data(
        [{"ventas": 10}, {"ventas": 20}, {"ventas": 30}]
    )

    assert result["row_count"] == 3
    assert result["columns"] == ["ventas"]
    assert result["summary"]["ventas"]["mean"] == 20.0

    # Validamos la estructura completa de la respuesta.
    validated = NumericAnalysisResult.model_validate(result)

    assert validated.row_count == 3
    assert validated.columns == ["ventas"]


def test_analyze_numeric_data_rejects_empty_rows():
    """La herramienta debe rechazar conjuntos de datos vacíos."""
    with pytest.raises(ValidationError):
        analyze_numeric_data([])


def test_analyze_numeric_data_rejects_inconsistent_columns():
    """Todas las filas deben tener las mismas columnas."""
    with pytest.raises(ValidationError):
        analyze_numeric_data(
            [{"ventas": 10}, {"coste": 20}]
        )


def test_output_schema_rejects_missing_statistic():
    """La respuesta debe incluir todas las estadísticas esperadas."""
    invalid_result = {
        "row_count": 3,
        "columns": ["ventas"],
        "summary": {
            "ventas": {
                "count": 3,
                "mean": 20,
                "std": 10,
                "min": 10,
                "25%": 15,
                "50%": 20,
                "75%": 25,
                # Falta la estadística "max".
            }
        },
    }

    with pytest.raises(ValidationError):
        NumericAnalysisResult.model_validate(invalid_result)


def test_desviacion_estandar_indefinida_se_devuelve_como_none():
    """Con una sola fila, la desviación estándar debe ser None."""
    result = analyze_numeric_data([{"ventas": 10}])

    assert result["row_count"] == 1
    assert result["columns"] == ["ventas"]
    assert result["summary"]["ventas"]["std"] is None

    # La respuesta sigue cumpliendo el esquema de salida.
    validated = NumericAnalysisResult.model_validate(result)
    assert validated.row_count == 1