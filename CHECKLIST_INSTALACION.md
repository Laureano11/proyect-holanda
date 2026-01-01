# ✅ Checklist de Instalación - Optimizaciones

Usa este checklist para verificar que todo está correctamente instalado y funcionando.

---

## 📋 Fase 1: Instalación de Redis

### macOS
```bash
brew install redis
brew services start redis
redis-cli ping  # Debe responder: PONG
```

- [ ] Redis instalado
- [ ] Redis corriendo
- [ ] `redis-cli ping` responde PONG

### Ubuntu/Debian
```bash
sudo apt-get install redis-server
sudo systemctl start redis
redis-cli ping  # Debe responder: PONG
```

- [ ] Redis instalado
- [ ] Redis corriendo
- [ ] `redis-cli ping` responde PONG

---

## 📋 Fase 2: Dependencias Python

```bash
# Activar entorno virtual
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

- [ ] Entorno virtual activado
- [ ] `redis>=5.0.0` instalado
- [ ] `django-redis>=5.4.0` instalado
- [ ] `celery>=5.3.0` instalado
- [ ] Sin errores de instalación

**Verificar:**
```bash
pip list | grep redis
pip list | grep celery
```

---

## 📋 Fase 3: Configuración

### Archivo .env

```bash
# Editar .env y agregar:
REDIS_URL=redis://localhost:6379/0
```

- [ ] Archivo `.env` existe
- [ ] Variable `REDIS_URL` agregada
- [ ] URL correcta (localhost:6379/0)

**Verificar:**
```bash
cat .env | grep REDIS_URL
```

---

## 📋 Fase 4: Verificación de Django

```bash
python manage.py shell
```

Dentro del shell:
```python
# Test 1: Caché
from django.core.cache import cache
cache.set('test', 'funciona', 60)
resultado = cache.get('test')
print(f"Caché: {resultado}")  # Debe imprimir: Caché: funciona

# Test 2: Settings
from django.conf import settings
print(f"Redis URL: {settings.REDIS_URL}")
print(f"Celery Broker: {settings.CELERY_BROKER_URL}")

# Salir
exit()
```

- [ ] Caché funciona correctamente
- [ ] Settings de Redis configurados
- [ ] Settings de Celery configurados
- [ ] Sin errores

---

## 📋 Fase 5: Verificación de Celery

### Terminal 1: Worker

```bash
celery -A config worker -l info
```

**Deberías ver:**
```
[tasks]
  . config.celery.debug_task
  . core.tasks.enviar_email_async
  . core.tasks.invalidar_cache_complejo
  . core.tasks.limpiar_turnos_expirados_task
  . core.tasks.marcar_turnos_jugados_task

celery@hostname ready.
```

- [ ] Worker inicia sin errores
- [ ] 5 tareas registradas
- [ ] Estado: "ready"

### Terminal 2: Probar Tarea

```bash
python manage.py shell
```

```python
from config.celery import debug_task
result = debug_task.delay()
print(f"Tarea ID: {result.id}")
exit()
```

- [ ] Tarea se envía correctamente
- [ ] En Terminal 1 se ve la ejecución
- [ ] Sin errores

### Terminal 3: Beat (Opcional)

```bash
celery -A config beat -l info
```

**Deberías ver:**
```
Scheduler: Starting...
beat: Starting...
```

- [ ] Beat inicia sin errores
- [ ] Muestra schedule de tareas
- [ ] Estado: "Starting"

---

## 📋 Fase 6: Verificación de Optimizaciones

### Test 1: Queries N+1

```bash
python manage.py runserver
```

Visitar: http://localhost:8000/dashboard/

**Con Django Debug Toolbar (si DEBUG=True):**
- [ ] Panel SQL visible
- [ ] Menos de 15 queries en dashboard
- [ ] Sin queries duplicadas (N+1)

### Test 2: Caché de Middleware

```bash
python manage.py shell
```

```python
from django.test import RequestFactory
from core.middleware import TenantMiddleware
from django.core.cache import cache

# Limpiar caché
cache.clear()

# Simular request
factory = RequestFactory()
request = factory.get('/', HTTP_HOST='localhost:8000')

middleware = TenantMiddleware(lambda r: None)
middleware(request)

print(f"Complejo: {request.complejo_actual}")

# Verificar que se cacheó
cache_key = 'complejo_default'
cached = cache.get(cache_key)
print(f"En caché: {cached is not None}")

exit()
```

- [ ] Complejo se resuelve correctamente
- [ ] Complejo se guarda en caché
- [ ] Sin errores

### Test 3: Sessions en Redis (Producción)

Solo aplica si `DEBUG=False` y `REDIS_URL` está configurado.

```bash
python manage.py shell
```

```python
from django.conf import settings
print(f"Session engine: {settings.SESSION_ENGINE}")
# En producción debe ser: django.contrib.sessions.backends.cache
exit()
```

- [ ] Session engine correcto según ambiente
- [ ] En desarrollo: puede ser 'db'
- [ ] En producción: debe ser 'cache'

---

## 📋 Fase 7: Test de Carga (Opcional)

### Instalar Apache Bench

```bash
# macOS (ya viene instalado)
ab -V

# Ubuntu
sudo apt-get install apache2-utils
```

### Ejecutar Test

```bash
# Test simple: 100 requests, 10 concurrentes
ab -n 100 -c 10 http://localhost:8000/

# Ver resultados
# Buscar: Requests per second
```

**Resultados esperados:**
- [ ] Sin errores (Failed requests: 0)
- [ ] Requests/segundo: >20
- [ ] Tiempo promedio: <500ms

---

## 📋 Fase 8: Verificación de Archivos

### Archivos Nuevos Creados

- [ ] `config/celery.py` existe
- [ ] `core/tasks.py` existe
- [ ] `DEPLOYMENT_OPTIMIZATIONS.md` existe
- [ ] `SETUP_REDIS_CELERY.md` existe
- [ ] `OPTIMIZATIONS_SUMMARY.md` existe
- [ ] `CHECKLIST_INSTALACION.md` existe (este archivo)
- [ ] `start_dev.sh` existe y es ejecutable

### Archivos Modificados

- [ ] `requirements.txt` tiene redis, celery, django-redis
- [ ] `config/settings.py` tiene configuración de Redis
- [ ] `config/settings.py` tiene configuración de Celery
- [ ] `config/settings.py` tiene sessions en Redis
- [ ] `config/settings.py` tiene connection pooling
- [ ] `config/__init__.py` importa celery_app
- [ ] `core/views.py` tiene select_related optimizado
- [ ] `core/middleware.py` tiene caché de complejos
- [ ] `env.example` tiene REDIS_URL

---

## 📋 Fase 9: Logs y Monitoreo

### Verificar Logs

```bash
# Terminal 1: Django
python manage.py runserver
# Ver logs en consola

# Terminal 2: Celery Worker
celery -A config worker -l info
# Ver logs de tareas

# Terminal 3: Redis
redis-cli MONITOR
# Ver comandos en tiempo real
```

- [ ] Django muestra logs sin errores
- [ ] Celery procesa tareas correctamente
- [ ] Redis recibe comandos SET/GET

### Verificar Estadísticas de Redis

```bash
redis-cli INFO stats
```

- [ ] `total_commands_processed` aumenta
- [ ] `keyspace_hits` > 0 (después de usar la app)
- [ ] `used_memory_human` razonable (<100MB)

---

## 📋 Fase 10: Deployment (Producción)

### Render.com

- [ ] Redis addon agregado
- [ ] Variable `REDIS_URL` automática
- [ ] Background Worker creado (Celery Worker)
- [ ] Background Worker creado (Celery Beat)
- [ ] Gunicorn configurado con 4 workers
- [ ] Deploy exitoso
- [ ] App funciona en producción

### Verificar en Producción

```bash
# Conectar a Redis de producción (desde Render Shell)
redis-cli -u $REDIS_URL ping

# Ver logs de Celery
# Desde Render dashboard → Background Workers → Logs
```

- [ ] Redis responde en producción
- [ ] Celery procesa tareas en producción
- [ ] Sin errores en logs

---

## 🎯 Resumen Final

### Checklist Completo

**Desarrollo:**
- [ ] Redis instalado y corriendo
- [ ] Dependencias Python instaladas
- [ ] .env configurado con REDIS_URL
- [ ] Django funciona con Redis
- [ ] Celery Worker funciona
- [ ] Celery Beat funciona (opcional)
- [ ] Queries optimizadas (Debug Toolbar)
- [ ] Caché funciona correctamente

**Producción:**
- [ ] Redis addon en Render
- [ ] Background Workers configurados
- [ ] Variables de entorno correctas
- [ ] Deploy exitoso
- [ ] App funciona sin errores
- [ ] Tareas periódicas ejecutándose

---

## 🚨 Troubleshooting Rápido

### Redis no conecta
```bash
redis-cli ping
# Si falla: brew services restart redis (macOS)
# O: sudo systemctl restart redis (Linux)
```

### Celery no inicia
```bash
# Verificar que estás en el entorno virtual
which python
# Debe apuntar a venv/bin/python

# Reinstalar Celery
pip install --force-reinstall celery
```

### Caché no funciona
```bash
# Limpiar caché y reintentar
redis-cli FLUSHDB

# Verificar configuración
python manage.py shell
>>> from django.conf import settings
>>> print(settings.CACHES)
```

### Queries N+1 persisten
```bash
# Usar Django Debug Toolbar
# Ver panel SQL
# Identificar queries duplicadas
# Agregar select_related() en la vista correspondiente
```

---

## ✅ Todo Listo!

Si todos los checkboxes están marcados, ¡felicitaciones! Tu aplicación está optimizada y lista para escalar.

**Próximos pasos:**
1. Leer `DEPLOYMENT_OPTIMIZATIONS.md` para deployment
2. Monitorear rendimiento en producción
3. Considerar Fase 2: WhatsApp, WebSockets, API REST

---

**¿Problemas?** Revisa:
- `SETUP_REDIS_CELERY.md` - Guía detallada
- `OPTIMIZATIONS_SUMMARY.md` - Resumen técnico
- Logs de Django, Celery y Redis

