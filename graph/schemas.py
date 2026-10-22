"""Esquemas propios de la orquestación (complementan agents/schemas.py).

agents/schemas.py define lo que el usuario aprueba en cada hito.
Aquí definimos lo que pasa de un hito al siguiente.
"""
from typing import List, Optional

from pydantic import BaseModel, Field, computed_field


class CompetitorEntry(BaseModel):
    """Un producto competidor encontrado en la investigación web."""
    brand: str = Field(..., description="Marca del producto (p. ej. 'Orijen', 'Salvaje'), NO la tienda")
    product: str = Field(..., description="Nombre concreto del producto")
    store: Optional[str] = Field(None, description="Tienda o comparador donde se vio el precio (p. ej. 'Tiendanimal')")
    price_eur: Optional[float] = Field(
        None, description="Precio total del producto en euros; null si no se conoce"
    )
    size_kg: Optional[float] = Field(
        None, description="Peso del saco/envase en kg (p. ej. 1.5, 7, 12); null si no se conoce"
    )
    source: Optional[str] = Field(None, description="URL de donde sale el dato")

    @computed_field
    @property
    def price_per_kg(self) -> Optional[float]:
        """€/kg calculado por nosotros: es lo que permite comparar marcas entre sí."""
        if self.price_eur and self.size_kg:
            return round(self.price_eur / self.size_kg, 2)
        return None


class ResearchFindings(BaseModel):
    """Resultado del Hito 1: lo que alimenta el análisis cuantitativo del Hito 2."""
    summary: str = Field(..., description="Síntesis cualitativa de los hallazgos (sin cálculos de €/kg)")
    competitors: List[CompetitorEntry] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list, description="Fuentes citadas")