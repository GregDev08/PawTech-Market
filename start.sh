#!/bin/bash

# Navegar a la carpeta del proyecto
cd ui

echo "🧹 Limpiando procesos anteriores en el puerto 8765..."
fuser -k 8765/tcp 2>/dev/null || true
pkill -f "server.py" 2>/dev/null || true

# Iniciar el servidor WebSocket en segundo plano
python server.py &

# Esperar un momento para asegurarse de que el servidor WebSocket esté listo
sleep 2

# Iniciar la aplicación Streamlit
streamlit run app.py