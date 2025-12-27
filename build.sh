#!/usr/bin/env bash
# Script de build para Render

set -o errexit  # Salir si hay error

echo "🔧 Instalando dependencias..."
pip install -r requirements.txt

echo "📦 Recolectando archivos estáticos..."
python manage.py collectstatic --no-input

echo "ℹ️  Migraciones: se ejecutan en el Start Command (para asegurar DB disponible)."

echo "✅ Build completado exitosamente!"

