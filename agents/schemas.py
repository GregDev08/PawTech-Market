from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# ==========================================
# HITO 1: PLANIFICACIÓN Y SUBTAREAS APROBABLES
# ==========================================
class SubTaskProposal(BaseModel):
    """Subtarea individual generada por el planificador para aprobación en el Frontend."""
    task_id: str = Field(..., description="ID de la subtarea, ej: ST-01")
    title: str = Field(..., description="Título de la subtarea")
    description: str = Field(..., description="Explicación detallada del objetivo")
    category: str = Field(..., description="Categoría: 'Investigación Web', 'Análisis Cuantitativo' o 'Análisis Visual'")

class PlanProposal(BaseModel):
    """Respuesta del agente con la propuesta de desglose para el Hito 1 (HITL)."""
    niche: str = Field(default="Alimentos holísticos y gadgets tecnológicos para mascotas", description="Nicho analizado")
    proposed_tasks: List[SubTaskProposal] = Field(..., description="Lista de subtareas seleccionables mediante checkboxes")

# ==========================================
# HITO 2: VALIDACIÓN CUANTITATIVA Y VISUAL
# ==========================================
class IntermediateValidation(BaseModel):
    """Consolidado de hallazgos para validación previa a la redacción (Hito 2 HITL)."""
    quantitative_summary: Dict[str, Any] = Field(..., description="Resumen estadístico del análisis MCP/Python")
    visual_findings: str = Field(..., description="Conclusiones extraídas de imágenes/packaging")
    sources_found: List[str] = Field(..., description="Enlaces y fuentes cualitativas identificadas")

# ==========================================
# HITO 3: INFORME FINAL Y AUTOMATIZACIÓN
# ==========================================
class MarketReportSchema(BaseModel):
    """Estructura final del informe entregado tras el Hito 3 de aprobación humana."""
    title: str = Field(..., description="Título del estudio de mercado")
    executive_summary: str = Field(..., description="Resumen ejecutivo del proyecto")
    competitor_analysis: str = Field(..., description="Análisis cualitativo de competidores")
    price_distribution_summary: str = Field(..., description="Resumen cuantitativo de rangos de precio")
    visual_insights: str = Field(..., description="Conclusiones del análisis visual/packaging")
    recommendations: List[str] = Field(..., description="Recomendaciones estratégicas finales")
    sources: List[str] = Field(..., description="Lista explícita de fuentes citadas")