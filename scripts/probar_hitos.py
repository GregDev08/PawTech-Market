"""Pruebo el flujo completo desde la terminal, haciendo yo de usuario: Hito 1 → 2 → 3.

Uso (desde la raíz del proyecto):  python scripts/probar_hitos.py
Sin gastar tokens:                 $env:FAKE_LLM="1"; python scripts/probar_hitos.py
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # para importar agents/ y graph/

from dotenv import load_dotenv
load_dotenv()

from langgraph.types import Command
from graph.workflow import build_graph


def run(graph, graph_input, config):
    """Ejecuto el grafo hasta la siguiente pausa e imprimo los eventos en vivo."""
    for mode, chunk in graph.stream(graph_input, config, stream_mode=["custom", "updates"]):
        if mode == "custom":  # lo que mandan los nodos con _emit()
            if chunk["event"] == "phase":
                print(f"\n▶ {chunk['message']}")
            elif chunk["event"] == "task":
                error = f" — {chunk['error']}" if chunk.get("error") else ""
                print(f"   {chunk['task_id']}: {chunk['status']} {chunk['progress']}%{error}")
    state = graph.get_state(config)
    return state.interrupts[0].value if state.interrupts else None  # la pausa, si la hay


def short(text, limit=600):
    """Recorto los textos largos de los agentes para que se lean en la terminal."""
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + " […]"


def show_research(r):
    """Resultado del Hito 1: productos con €/kg calculado por nosotros."""
    print(r["summary"] + "\n")
    for c in r["competitors"]:
        print(f"  - {c['brand']} | {c['product']} | {c.get('store')} | {c.get('price_eur')} € | "
              f"{c.get('size_kg')} kg | {c.get('price_per_kg')} €/kg")
    print(f"\nPrecios comparables (€/kg): {r['comparable_prices']} · duplicados quitados: {r['duplicates_removed']}")
    if r["cheapest"]:
        c = r["cheapest"]
        print(f"Más barato por kg (calculado): {c['brand']} {c['product']} en {c.get('store')} → {c['price_per_kg']} €/kg")


def show_validation(r):
    """Resultado del Hito 2: estadísticas de la herramienta MCP + lo que interpretan los agentes."""
    stats = r["quantitative_summary"]["estadisticas"]
    if "summary" in stats:
        s = stats["summary"]["precio_eur_kg"]
        print(f"Estadísticas €/kg (vía {stats['via']}) con {stats['row_count']} precios:")
        print(f"  media {s['mean']:.2f} · mínimo {s['min']:.2f} · máximo {s['max']:.2f} · "
              f"desviación {s['std'] if s['std'] is None else round(s['std'], 2)}")
    else:
        print(f"Estadísticas: {stats.get('aviso')}")
    print(f"\nInterpretación cuantitativa:\n{short(r['quantitative_summary']['interpretacion'])}")
    print(f"\nHallazgos visuales:\n{short(r['visual_findings'])}")


def show_report(r):
    """Resultado del Hito 3: el informe y el veredicto del revisor crítico."""
    rep = r["report"]
    print(f"{rep['title']}\n")
    print(f"Resumen ejecutivo:\n{short(rep['executive_summary'], 400)}\n")
    print(f"Distribución de precios (escrita por el código):\n{rep['price_distribution_summary']}\n")
    print("Recomendaciones:")
    for rec in rep["recommendations"]:
        print(f"  - {short(rec, 200)}")
    print(f"\nFuentes: {len(rep['sources'])} · Veredicto del revisor: {r['audit_verdict']}")
    print("Si apruebas, autorizas la exportación del informe a outputs/.")


def main():
    query = input("¿Qué estudio quieres? (Enter = pienso premium para perros en España): ").strip() \
        or "Estudio de mercado de pienso premium para perros en España"
    graph = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}  # un "hilo" = un estudio

    pause = run(graph, {"query": query, "hito": 1, "attempts": {1: 1, 2: 1, 3: 1}}, config)
    while pause:
        if pause["type"] == "approve_subtasks":
            print(f"\n⏸  HITO {pause['hito']} — subtareas propuestas:")
            for i, t in enumerate(pause["tasks"], 1):
                print(f"  [{i}] ({t['category']}) {t['title']}\n      {t['description']}")
            sel = input("\nNúmeros a aprobar, separados por comas: ")
            ids = [pause["tasks"][int(x) - 1]["id"] for x in sel.split(",")
                   if x.strip().isdigit() and 0 < int(x) <= len(pause["tasks"])]
            if not ids:
                print("⚠️  No has marcado ninguna: el grafo volverá a preguntar.")
            pause = run(graph, Command(resume={"approved_ids": ids}), config)
            continue

        # review_hito
        hito, r = pause["hito"], pause["result"]
        print(f"\n⏸  HITO {hito} — intento {pause['attempt']} de {pause['max_attempts']}\n")
        {"research": show_research, "validation": show_validation, "report": show_report}[r["kind"]](r)
        for t in r["subtasks"]:
            if t["status"] == "failed":
                print(f"  ✗ {t['id']} falló: {t['error']}")
        if not pause["can_redo"]:
            print("⚠️  Límite de intentos alcanzado: solo se puede aprobar.")

        if input("\n¿Aprobar (a) o rehacer (r)? ").strip().lower().startswith("r"):
            feedback = input("Comentario para rehacer: ")
            pause = run(graph, Command(resume={"decision": "redo", "feedback": feedback}), config)
        else:
            print(f"\n✅ Hito {hito} aprobado." + (f" Pasamos al Hito {hito + 1}." if hito < 3 else ""))
            pause = run(graph, Command(resume={"decision": "approve"}), config)

    # Sin más pausas: el grafo ha llegado al final (finalize ya exportó el informe)
    final = graph.get_state(config).values.get("final") or {}
    print("\n🏁 Estudio terminado. Informe exportado en:")
    for path in final.get("files", []):
        print(f"   {path}")


if __name__ == "__main__":
    main()