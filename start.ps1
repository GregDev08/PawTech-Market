# Arranque de PawTech-Market en Windows (equivalente a start.sh).
# Uso, desde la raíz del proyecto:   .\start.ps1
# Sin gastar tokens de Groq:         .\start.ps1 -Fake
param([switch]$Fake)

if ($Fake) {
    $env:FAKE_LLM = "1"
    Write-Host "🧪 Modo simulado (FAKE_LLM=1): los agentes no llaman a Groq."
}

# Si quedó un servidor de una ejecución anterior en el puerto 8765, lo paro
Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

# Servidor WebSocket (el grafo de agentes) en su propia ventana, para ver sus mensajes
Write-Host "🌐 Arrancando el servidor WebSocket..."
Start-Process python -ArgumentList "ui/server.py"

# Espero a que el servidor escuche (importar CrewAI y LangGraph tarda unos segundos)
for ($i = 0; $i -lt 30; $i++) {
    if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) { break }
    Start-Sleep -Seconds 1
}

Write-Host "🖥️  Abriendo la interfaz..."
streamlit run ui/app.py