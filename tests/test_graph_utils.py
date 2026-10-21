"""Tests de las piezas pequeñas del grafo: las que garantizan que las cifras son correctas.

La regla del proyecto es que las cifras salen del código, no del LLM. Estos tests
comprueban precisamente ese código: €/kg, duplicados, el más barato y el resumen.
"""
from agents.schemas import PlanProposal
from graph.schemas import CompetitorEntry
from graph.workflow import (_cheapest, _dedupe_competitors, _match_category,
                            _normalize_tasks, _price_summary)


def test_price_per_kg_se_calcula_y_no_lo_pide_al_llm():
    c = CompetitorEntry(brand="Salvaje", product="Adult", price_eur=24.99, size_kg=12)
    assert c.price_per_kg == 2.08
    # Sin tamaño no se puede comparar: queda vacío en lugar de inventarse
    assert CompetitorEntry(brand="X", product="Y", price_eur=10).price_per_kg is None
    # El campo calculado no aparece en el esquema que enviamos al LLM
    assert "price_per_kg" not in CompetitorEntry.model_json_schema()["properties"]


def test_duplicados_se_quedan_con_la_oferta_mas_barata():
    competitors = [
        {"brand": "Salvaje", "product": "Adult", "store": "Tiendanimal", "size_kg": 12, "price_per_kg": 2.08},
        {"brand": "salvaje ", "product": "adult", "store": "Idealo", "size_kg": 12, "price_per_kg": 2.12},
        {"brand": "Salvaje", "product": "Adult", "store": "Tiendanimal", "size_kg": 1.5, "price_per_kg": 3.99},
    ]
    result = _dedupe_competitors(competitors)
    assert len(result) == 2  # el saco de 1,5 kg es otro producto: no es duplicado
    assert {"Tiendanimal"} == {c["store"] for c in result if c["size_kg"] == 12}


def test_mas_barato_por_kg_ignora_productos_sin_precio():
    competitors = [{"brand": "A", "price_per_kg": 4.99}, {"brand": "B", "price_per_kg": None},
                   {"brand": "C", "price_per_kg": 2.08}]
    assert _cheapest(competitors)["brand"] == "C"
    assert _cheapest([{"brand": "A", "price_per_kg": None}]) is None


def test_categorias_del_llm_se_ajustan_al_hito():
    assert _match_category("investigación web", ["Investigación Web"]) == "Investigación Web"
    assert _match_category("Análisis de precios", ["Análisis Cuantitativo", "Análisis Visual"]) == "Análisis Cuantitativo"
    assert _match_category("Análisis Visual", ["Investigación Web"]) is None  # no es de este hito


def test_subtareas_fuera_del_hito_se_descartan():
    plan = PlanProposal.model_validate({"proposed_tasks": [
        {"task_id": "ST-01", "title": "Precios", "description": "x", "category": "investigación web"},
        {"task_id": "ST-02", "title": "Packaging", "description": "y", "category": "Análisis Visual"},
    ]})
    tasks = _normalize_tasks(plan, 1)
    assert [t["id"] for t in tasks] == ["H1-ST-01"]
    assert tasks[0]["agent"] == "market_researcher"


def test_resumen_de_precios_lo_escribe_el_codigo_con_formato_espanol():
    state = {
        "research": {"competitors": [{"brand": "Salvaje", "product": "Adult", "store": "Tiendanimal",
                                      "price_per_kg": 2.08}]},
        "validation": {"quantitative_summary": {"estadisticas": {"via": "mcp", "summary": {"precio_eur_kg": {
            "count": 4.0, "mean": 4.3725, "std": 1.5423, "min": 2.08, "50%": 4.99, "max": 5.43}}}}},
    }
    text = _price_summary(state)
    assert "4,37 €/kg" in text and "2,08 a 5,43" in text
    assert "Salvaje Adult (Tiendanimal) a 2,08 €/kg" in text
    assert "vía mcp" in text
