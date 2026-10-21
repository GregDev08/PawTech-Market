"""Prueba del Hito 1 desde la terminal: tú haces de usuario.

Uso (desde la raíz del proyecto):  python scripts/probar_hito1.py
"""
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # para importar agents/ y graph/

from dotenv import load_dotenv
load_dotenv()

from langgraph.types import Command
from graph.workflow import build_graph


def run(graph, graph_input, config):
    """Ejecuta el grafo hasta la siguiente pausa, mostrando los eventos en vivo."""
    for mode, chunk in graph.stream(graph_input, config, stream_mode=["custom", "updates"]):
        if mode == "custom":  # lo que envían los nodos con _emit()
            if chunk["event"] == "phase":
                print(f"\n▶ {chunk['message']}")
            elif chunk["event"] == "task":
                error = f" — {chunk['error']}" if chunk.get("error") else ""
                print(f"   {chunk['task_id']}: {chunk['status']} {chunk['progress']}%{error}")
    state = graph.get_state(config)
    return state.interrupts[0].value if state.interrupts else None  # la pausa, si la hay


def main():
    query = input("¿Qué estudio quieres? (Enter = pienso premium para perros en España): ").strip() \
        or "Estudio de mercado de pienso premium para perros en España"
    graph = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}  # un "hilo" = un estudio

    pause = run(graph, {"query": query, "hito": 1, "attempts": {1: 1}}, config)
    while pause:
        if pause["type"] == "approve_subtasks":
            print(f"\n⏸  HITO {pause['hito']} — subtareas propuestas:")
            for i, t in enumerate(pause["tasks"], 1):
                print(f"  [{i}] {t['title']}\n      {t['description']}")
            sel = input("\nNúmeros a aprobar, separados por comas (consejo: 1 o 2 para ahorrar tokens): ")
            ids = [pause["tasks"][int(x) - 1]["id"] for x in sel.split(",")
                   if x.strip().isdigit() and 0 < int(x) <= len(pause["tasks"])]
            if not ids:
                print("⚠️  No has marcado ninguna: el grafo volverá a preguntar.")
            pause = run(graph, Command(resume={"approved_ids": ids}), config)

        else:  # review_hito
            r = pause["result"]
            print(f"\n⏸  HITO {pause['hito']} — intento {pause['attempt']} de {pause['max_attempts']}"
                  f"\n{r['summary']}\n")
            for c in r["competitors"]:
                print(f"  - {c['name']} | {c['product']} | {c.get('price_eur')} € | "
                      f"{c.get('size_kg')} kg | {c.get('price_per_kg')} €/kg | {c.get('source')}")
            print(f"\nPrecios comparables (€/kg): {r['comparable_prices']}")
            for t in r["subtasks"]:
                if t["status"] == "failed":
                    print(f"  ✗ {t['id']} falló: {t['error']}")
            if not pause["can_redo"]:
                print("⚠️  Límite de intentos alcanzado: solo se puede aprobar.")

            if input("\n¿Aprobar (a) o rehacer (r)? ").strip().lower().startswith("r"):
                feedback = input("Comentario para rehacer: ")
                pause = run(graph, Command(resume={"decision": "redo", "feedback": feedback}), config)
            else:
                print("\n✅ Hito 1 aprobado. Esto es lo que recibirá el Hito 2:")
                print(json.dumps(graph.get_state(config).values["research"], ensure_ascii=False, indent=2))
                return


if __name__ == "__main__":
    main()