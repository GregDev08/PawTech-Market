"""Tests de graph/mcp_client.py: la conexión del Hito 2 con la herramienta de Luis."""
from graph import mcp_client


def test_estadisticas_por_mcp_con_el_servidor_de_luis():
    """Arranca de verdad mcp_servers/pawtech_server.py y le pide las estadísticas."""
    rows = [{"precio_eur_kg": v} for v in (4.99, 2.08, 4.99, 5.43)]
    result = mcp_client.analyze_numeric_data(rows)
    assert result["via"] == "mcp"
    s = result["summary"]["precio_eur_kg"]
    assert s["min"] == 2.08 and s["max"] == 5.43 and round(s["mean"], 2) == 4.37


def test_si_mcp_falla_usa_la_funcion_local(monkeypatch):
    """Si el servidor no arranca, el estudio no se cae: calcula en local y lo indica."""
    monkeypatch.setattr(mcp_client, "SERVER_PATH", mcp_client.SERVER_PATH.with_name("no_existe.py"))
    result = mcp_client.analyze_numeric_data([{"precio_eur_kg": 2.0}, {"precio_eur_kg": 4.0}])
    assert result["via"].startswith("python_local")
    assert result["summary"]["precio_eur_kg"]["mean"] == 3.0


def test_nan_se_convierte_en_none_para_el_json():
    """Con un solo precio pandas da desviación NaN, que rompería el JSON de la interfaz."""
    result = mcp_client.analyze_numeric_data([{"precio_eur_kg": 2.0}])
    assert result["summary"]["precio_eur_kg"]["std"] is None
