import math
from typing import Any

import pandas as pd
from pydantic import (
    BaseModel,
    Field,
    FiniteFloat,
    field_validator,
    model_validator,
)


class NumericDataset(BaseModel):
    """Valida los datos numéricos que recibe la herramienta."""

    rows: list[dict[str, float]]

    @field_validator("rows")
    @classmethod
    def validate_rows(
        cls, rows: list[dict[str, float]]
    ) -> list[dict[str, float]]:
        if not rows:
            raise ValueError("El conjunto de datos no puede estar vacío.")

        expected_columns = set(rows[0])

        if not expected_columns:
            raise ValueError(
                "Cada fila debe contener al menos una columna numérica."
            )

        for row in rows:
            if set(row) != expected_columns:
                raise ValueError(
                    "Todas las filas deben tener las mismas columnas."
                )

            for column, value in row.items():
                if not math.isfinite(value):
                    raise ValueError(
                        f"El valor de '{column}' debe ser un número finito."
                    )

        return rows


class NumericAnalysisResult(BaseModel):
    """Valida la estructura de salida del análisis estadístico."""

    row_count: int = Field(gt=0)
    columns: list[str] = Field(min_length=1)
    summary: dict[str, dict[str, FiniteFloat | None]]

    @model_validator(mode="after")
    def validate_result(self) -> "NumericAnalysisResult":
        expected_metrics = {
            "count",
            "mean",
            "std",
            "min",
            "25%",
            "50%",
            "75%",
            "max",
        }

        if len(self.columns) != len(set(self.columns)):
            raise ValueError("La lista de columnas contiene duplicados.")

        if set(self.columns) != set(self.summary):
            raise ValueError(
                "Las columnas no coinciden con las del resumen estadístico."
            )

        for column, statistics in self.summary.items():
            if set(statistics) != expected_metrics:
                raise ValueError(
                    f"Las estadísticas de '{column}' no tienen "
                    "la estructura esperada."
                )

            if statistics["count"] != self.row_count:
                raise ValueError(
                    f"El recuento de '{column}' no coincide con row_count."
                )

            for metric, value in statistics.items():
                if value is None and metric != "std":
                    raise ValueError(
                        f"La estadística '{metric}' de '{column}' "
                        "no puede ser None."
                    )

            if statistics["std"] is None and self.row_count != 1:
                raise ValueError(
                    f"La desviación estándar de '{column}' "
                    "no debería ser None con varias filas."
                )

        return self


def analyze_numeric_data(rows: list[dict[str, float]]) -> dict[str, Any]:
    """Valida la entrada, calcula estadísticas y valida la respuesta."""

    dataset = NumericDataset.model_validate({"rows": rows})
    frame = pd.DataFrame(dataset.rows)

    raw_summary = frame.describe().to_dict()

    # Convertimos los valores de NumPy a float de Python.
    # Si alguna estadística no es finita, la representamos como None.
    summary: dict[str, dict[str, float | None]] = {}

    for column, statistics in raw_summary.items():
        summary[column] = {}

        for metric, value in statistics.items():
            number = float(value)

            summary[column][metric] = (
                number if math.isfinite(number) else None
            )

    # Validamos la respuesta antes de devolverla.
    validated_result = NumericAnalysisResult.model_validate(
        {
            "row_count": len(frame),
            "columns": list(frame.columns),
            "summary": summary,
        }
    )

    # Conservamos el formato de diccionario que utiliza el proyecto.
    return validated_result.model_dump()