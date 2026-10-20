import math
from typing import Any

import pandas as pd
from pydantic import BaseModel, field_validator


class NumericDataset(BaseModel):
    rows: list[dict[str, float]]

    @field_validator("rows")
    @classmethod
    def validate_rows(cls, rows: list[dict[str, float]]) -> list[dict[str, float]]:
        if not rows:
            raise ValueError("El conjunto de datos no puede estar vacío.")

        expected_columns = set(rows[0])
        if not expected_columns:
            raise ValueError("Cada fila debe contener al menos una columna numérica.")

        for row in rows:
            if set(row) != expected_columns:
                raise ValueError("Todas las filas deben tener las mismas columnas.")

            for column, value in row.items():
                if not math.isfinite(value):
                    raise ValueError(
                        f"El valor de '{column}' debe ser un número finito."
                    )

        return rows


def analyze_numeric_data(rows: list[dict[str, float]]) -> dict[str, Any]:
    """Calcula estadísticas descriptivas de filas con datos numéricos."""
    dataset = NumericDataset.model_validate({"rows": rows})
    frame = pd.DataFrame(dataset.rows)
    summary = frame.describe().to_dict()

    return {
        "row_count": len(frame),
        "columns": list(frame.columns),
        "summary": summary,
    }
