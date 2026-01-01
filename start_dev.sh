#!/bin/bash

# Script de inicio para desarrollo con todos los servicios

echo "🚀 Iniciando servicios de desarrollo..."

# Colores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Verificar que Redis está corriendo
echo -e "${YELLOW}Verificando Redis...${NC}"
if redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Redis está corriendo${NC}"
else
    echo -e "${YELLOW}⚠ Redis no está corriendo. Intentando iniciar...${NC}"
    
    # Intentar iniciar Redis según el sistema operativo
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        brew services start redis
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        sudo systemctl start redis
    else
        echo "Por favor inicia Redis manualmente"
        exit 1
    fi
    
    sleep 2
    
    if redis-cli ping > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Redis iniciado correctamente${NC}"
    else
        echo "❌ No se pudo iniciar Redis. Inicialo manualmente."
        exit 1
    fi
fi

# Verificar que PostgreSQL está corriendo
echo -e "${YELLOW}Verificando PostgreSQL...${NC}"
if pg_isready > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PostgreSQL está corriendo${NC}"
else
    echo -e "${YELLOW}⚠ PostgreSQL no responde. Asegurate de que esté corriendo.${NC}"
fi

# Activar entorno virtual si existe
if [ -d "venv" ]; then
    echo -e "${YELLOW}Activando entorno virtual...${NC}"
    source venv/bin/activate
    echo -e "${GREEN}✓ Entorno virtual activado${NC}"
fi

# Aplicar migraciones pendientes
echo -e "${YELLOW}Aplicando migraciones...${NC}"
python manage.py migrate --noinput
echo -e "${GREEN}✓ Migraciones aplicadas${NC}"

# Crear directorios para logs si no existen
mkdir -p logs

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Servicios listos para desarrollo${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Para iniciar todos los servicios, ejecutá en terminales separadas:"
echo ""
echo "  Terminal 1 (Django):"
echo "    python manage.py runserver"
echo ""
echo "  Terminal 2 (Celery Worker - opcional):"
echo "    celery -A config worker -l info"
echo ""
echo "  Terminal 3 (Celery Beat - opcional):"
echo "    celery -A config beat -l info"
echo ""
echo "O ejecutá todo en una sola terminal con:"
echo "  ./start_all.sh"
echo ""

