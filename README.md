# PawTech-Market

![PawTech-Market Banner](assets/pawtech_readme_banner.png)

## Objetivo

PawTech-Market es un proyecto de investigación de mercado para productos y
nutrición inteligente para mascotas. El equipo está preparando la estructura
inicial de un sistema multi-agente con CrewAI, LangGraph y MCP. La interfaz de
usuario se desarrollará en una etapa posterior.

> **Estado actual:** el flujo multi-agente funciona de extremo a extremo: agentes
> CrewAI, orquestación LangGraph en 3 hitos con Human-in-the-Loop, análisis
> cuantitativo vía MCP e interfaz Streamlit conectada en vivo por WebSocket.

## Estructura inicial

```text
agents/       Agentes CrewAI
graph/        Estado y orquestación LangGraph
tools/        Herramientas compartidas y esquemas Pydantic
mcp_servers/  Servidores y clientes MCP
ui/           Interfaz de usuario (desarrollo posterior)
tests/        Pruebas con pytest
assets/       Recursos visuales del proyecto
```

## Equipo y responsabilidades

| Persona | Rol | Responsabilidad inicial |
| --- | --- | --- |
| Vanesa | Persona 1 — Crew Lead IA | Diseñar los agentes, sus tareas y la colaboración con CrewAI. |
| Adri | Persona 2 — LangGraph Lead | Definir el estado compartido y la orquestación del flujo con LangGraph. |
| Luis | Persona 3 — MCP Lead | Diseñar e implementar servidores/clientes MCP y herramientas integradas. |
| Josema | Persona 4 — Frontend Lead | Desarrollar la futura interfaz de usuario y conectarla con el flujo del sistema. |
| Joselillo | Persona 5 — QA & Ops Lead | Preparar el setup, estructura, dependencias, pruebas iniciales y controles de calidad. |

Las responsabilidades concretas y los contratos entre componentes se acordarán
en equipo antes de implementar los flujos de extremo a extremo.

## Alcance del setup inicial

El primer commit de Persona 5 (QA & Ops) prepara únicamente la base compartida:
carpetas rastreables, dependencias iniciales, plantilla de variables de entorno,
reglas de exclusión, README y una prueba de humo. No incluye implementación de
agentes, orquestación, servidores MCP ni interfaz; cada responsable incorporará
esas piezas en los siguientes cambios coordinados.

## Preparar el entorno

Se recomienda Python 3.10 o superior. Desde la raíz del repositorio:

```bash
python -m venv .venv
```

Activa el entorno virtual:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Instala las dependencias base:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Crea `.env` a partir de `.env.example` y configura las claves que tengas
autorización para usar. Nunca subas `.env` ni credenciales al repositorio.

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

```bash
# macOS / Linux
cp .env.example .env
```

## Ejecutar el sistema

1. Crea el `.env` (ver arriba) con tu `GROQ_API_KEY`.
2. Arranca el servidor WebSocket y la interfaz:

```powershell
# Windows
.\start.ps1            # con Groq
.\start.ps1 -Fake      # modo simulado, sin gastar tokens
```

```bash
# macOS / Linux
./start.sh
FAKE_LLM=1 ./start.sh   # modo simulado
```

O a mano, en dos terminales: `python ui/server.py` y `streamlit run ui/app.py`.

Para recorrer el flujo sin interfaz, haciendo tú de usuario en la terminal:

```bash
python scripts/probar_hitos.py
```

### Cómo funciona el flujo

Cada hito sigue el mismo ciclo, con dos pausas Human-in-the-Loop:

```text
planificar ──► aprobar subtareas ──► ejecutar ──► revisar resultado
                  (pausa)                            (pausa)
                                                      ├─ rehacer (con comentario, máx. 3 intentos)
                                                      └─ aprobar → siguiente hito
```

| Hito | Agentes | Resultado |
| --- | --- | --- |
| 1. Planificación e investigación | Investigador (búsqueda web de Groq) | Productos con precio, tamaño y €/kg |
| 2. Validación cuantitativa y visual | Analista de datos + analista visual | Estadísticas €/kg vía la herramienta MCP |
| 3. Informe y automatización | Redactor estratégico + revisor crítico | Informe auditado, exportado a `outputs/` |

Las cifras (€/kg, estadísticas, resumen de precios) las calcula el código, no el
LLM, y el informe incluye un registro de las decisiones humanas de cada pausa.

### Modo simulado

Con `FAKE_LLM=1` los agentes devuelven respuestas de ejemplo (`graph/fake_llm.py`)
sin llamar a Groq: sirve para desarrollar la interfaz, hacer demos y lanzar los
tests. El plan gratuito de Groq tiene un límite diario de tokens por modelo.

## Pruebas

```bash
pytest
```

Los tests del grafo corren en modo simulado: no necesitan `.env` ni gastan tokens.
Cubren los esquemas y cálculos, los 3 hitos, las pausas HITL, el límite de
intentos, la sesión de la interfaz y la conexión con el servidor MCP.

## Flujo Git

- `main`: rama estable; no realizar commits directamente.
- `develop`: integración del trabajo del equipo.
- `feature/<descripcion-corta>`: ramas de trabajo creadas desde `develop`.
- Integrar cambios mediante Pull Requests hacia `develop`, con descripción,
  pruebas relevantes y al menos una revisión de otro integrante.
- Mantener los cambios enfocados y no incluir secretos, entornos virtuales,
  cachés ni datos locales.
