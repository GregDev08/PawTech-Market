"""Esquemasde la orquestación.

agents/schemas.py define lo que el usuario aprueba en cada hito.
Aquí definimos lo que pasa de un hito al siguiente.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class CompetitorEntry(BaseModel):
    """Un competidor encontrado en la investigación web."""
    name: str = Field(..., description="Marca o tienda competidora")
    product: str = Field(..., description="Producto o línea analizada")
    price_eur: Optional[float] = Field(
        None, description="Precio en euros si aparece en la fuente; null si no se conoce"
    )
    source: Optional[str] = Field(None, description="URL o referencia de donde sale el dato")


class ResearchFindings(BaseModel):
    """Resultado del Hito 1: lo que alimenta el análisis cuantitativo del Hito 2."""
    summary: str = Field(..., description="Síntesis de los hallazgos de la investigación web")
    competitors: List[CompetitorEntry] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list, description="Fuentes citadas")