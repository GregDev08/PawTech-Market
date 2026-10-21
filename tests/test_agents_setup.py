import sys
from pathlib import Path

# Añadir la raíz del proyecto al sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

def test_imports_and_instantiation():
    print("--- 🔍 INICIANDO PRUEBA LOCAL DE LA CAPA AGÉNTICA ---")
    
    # 1. Probar importación de esquemas Pydantic
    try:
        from agents.schemas import PlanProposal, SubTaskProposal, MarketReportSchema
        print("✅ Esquemas Pydantic importados correctamente.")
        
        subtask = SubTaskProposal(
            task_id="ST-01",
            title="Análisis de Competidores Directos",
            description="Investigar precios y productos en Kiwoko y Tiendanimal",
            category="Investigación Web"
        )
        plan = PlanProposal(
            niche="Nutrición Holística para Mascotas",
            proposed_tasks=[subtask]
        )
        print(f"   -> Ejemplo de Hito 1 generado: {plan.proposed_tasks[0].title}")
    except Exception as e:
        print(f"❌ Error al importar/validar esquemas Pydantic: {e}")
        return

    # 2. Probar instanciación de los 5 agentes de CrewAI
    try:
        from agents.crew_agents import (
            get_market_researcher,
            get_data_analyst,
            get_visual_analyst,
            get_strategic_writer,
            get_critical_reviewer
        )
        
        researcher = get_market_researcher()
        analyst = get_data_analyst()
        visual = get_visual_analyst()
        writer = get_strategic_writer()
        reviewer = get_critical_reviewer()
        
        # Extraer nombres de herramientas de forma segura
        analyst_tools = [getattr(t, 'name', str(t)) for t in (analyst.tools or [])]
        
        print("✅ Los 5 agentes fueron creados e instanciados con éxito desde agents.yaml:")
        print(f"   1. {researcher.role}")
        print(f"   2. {analyst.role} (Herramientas asignadas: {analyst_tools})")
        print(f"   3. {visual.role}")
        print(f"   4. {writer.role}")
        print(f"   5. {reviewer.role}")
    except Exception as e:
        print(f"❌ Error al instanciar los agentes: {e}")
        return

    print("\n🎉 ¡TODAS LAS PRUEBAS LOCALES PASARON CON ÉXITO! El módulo 'agents' está impecable.")

if __name__ == "__main__":
    test_imports_and_instantiation()