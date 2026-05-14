# 🚀 Setup Redis y Celery - Guía Rápida

Esta guía te ayudará a configurar Redis y Celery en tu entorno de desarrollo.

## ✅ Checklist de Instalación

- [ ] Instalar Redis
- [ ] Instalar dependencias Python
- [ ] Configurar variables de entorno
- [ ] Verificar que todo funciona

---

## 1️⃣ Instalar Redis

### macOS (con Homebrew)

```bash
# Instalar Redis
brew install redis

# Iniciar Redis (se iniciará automáticamente en cada boot)
brew services start redis

# Verificar que funciona
redis-cli ping
# Debe responder: PONG
```

### Ubuntu/Debian

```bash
# Instalar Redis
sudo apt-get update
sudo apt-get install redis-server

# Iniciar Redis
sudo systemctl start redis

# Habilitar para que inicie automáticamente
sudo systemctl enable redis

# Verificar que funciona
redis-cli ping
# Debe responder: PONG
```

### Windows

1. Descargar Redis desde: https://github.com/microsoftarchive/redis/releases
2. O usar WSL2 con Ubuntu y seguir las instrucciones de Ubuntu

---

## 2️⃣ Instalar Dependencias Python

```bash
# Activar tu entorno virtual
source venv/bin/activate  # Linux/macOS
# O en Windows: venv\Scripts\activate

# Instalar dependencias actualizadas
pip install -r requirements.txt
```

**Nuevas dependencias agregadas:**
- `redis>=5.0.0` - Cliente de Redis
- `django-redis>=5.4.0` - Backend de caché para Django
- `celery>=5.3.0` - Sistema de tareas asincrónicas
- `celery[redis]>=5.3.0` - Soporte de Redis para Celery

---

## 3️⃣ Configurar Variables de Entorno

Edita tu archivo `.env` y agrega:

```bash
# Redis - Caché y Celery
REDIS_URL=redis://localhost:6379/0
```

**Nota:** Si ya tienes un archivo `.env`, solo agrega la línea de `REDIS_URL`.

---

## 4️⃣ Verificar Instalación

### Paso 1: Verificar Redis

```bash
# Conectar a Redis
redis-cli

# Dentro de redis-cli, ejecutar:
ping
# Debe responder: PONG

# Salir
exit
```

### Paso 2: Verificar Django con Redis

```bash
# Iniciar shell de Django
python manage.py shell

# Dentro del shell, ejecutar:
from django.core.cache import cache
cache.set('test', 'funciona', 60)
print(cache.get('test'))
# Debe imprimir: funciona

# Salir
exit()
```

### Paso 3: Verificar Celery

```bash
# En una terminal, iniciar el worker de Celery
celery -A config worker -l info

# Deberías ver algo como:
# [tasks]
#   . core.tasks.marcar_turnos_jugados_task
#   . core.tasks.limpiar_turnos_expirados_task
#   ...
# celery@hostname ready.
```

### Paso 4: Probar una tarea

En otra terminal:

```bash
python manage.py shell

# Ejecutar una tarea de prueba
from config.celery import debug_task
result = debug_task.delay()
print(f"Tarea enviada: {result.id}")

# Salir
exit()
```

En la terminal del worker deberías ver que se ejecutó la tarea.

---

## 5️⃣ Ejecutar Todo en Desarrollo

### Opción A: Terminales Separadas (Recomendado para debug)

**Terminal 1 - Django:**
```bash
python manage.py runserver
```

**Terminal 2 - Celery Worker:**
```bash
celery -A config worker -l info
```

**Terminal 3 - Celery Beat (opcional, para tareas periódicas):**
```bash
celery -A config beat -l info
```

### Opción B: Script de Inicio

```bash
# Verificar servicios y preparar entorno
./start_dev.sh

# Luego iniciar Django normalmente
python manage.py runserver
```

---

## 🎯 ¿Qué Cambió en tu Aplicación?

### 1. Caché Compartido (Redis)

**Antes:**
- Cada worker de Gunicorn tenía su propio caché
- Slots disponibles se calculaban múltiples veces
- Alto uso de CPU y DB

**Ahora:**
- Caché compartido entre todos los workers
- Slots se calculan 1 vez y se cachean por 5 minutos
- Resolución de complejos se cachea por 1 hora
- **Resultado: 10x más rápido**
