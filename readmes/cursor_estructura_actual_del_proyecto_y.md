# Estructura actual del proyecto y puntos débiles
_Exported on 1/9/2026 at 20:38:42 GMT-3 from Cursor (2.2.44)_

---

**User**

Como se encuentra el proyecto actualmente estructurado, con redis, celeris beat y celeris worker. DB de 10gb PostgreSQL corriendo en render. La web corriendo en render con 0.5 CPU y 512mb de ram. Cual es la capacidad tecnica de la pagina? Donde esta el punto debil, donde puede fallar?

---

**Cursor**

Vale. Voy a revisar la configuración real del repo (Django settings, Celery, Redis, middleware multi-tenant, etc.) para inferir límites de CPU/RAM en Render, patrones de carga y puntos únicos de falla. Luego te doy una evaluación práctica: capacidad aproximada, cuellos de botella y dónde es más probable que falle primero.

Aha: ya veo que en producción usan **Redis para caché y sesiones** y **Celery/Beat** con varias tareas periódicas (limpieza cada 10 min, backups diarios). Ahora voy a revisar `SETUP_PRODUCTION.md` y `core/tasks.py` para ubicar riesgos concretos (backups de 10GB, timeouts, concurrencia, y carga sobre DB/Redis).

### Capacidad técnica (con tu infraestructura actual)

Con **0.5 CPU y 512 MB RAM** en el servicio web de Render, la capacidad real suele estar limitada por **CPU (renderizado + ORM) y memoria (procesos/threads de Gunicorn + cachés + templates)** más que por Redis/Celery.

- **Carga “normal” (uso humano)**: para un sistema de turnos tipo HTMX (páginas con consultas y renders frecuentes), normalmente vas a estar cómodo con **decenas de usuarios concurrentes** (no “miles”) si las vistas críticas siguen en **5–10 queries** como apunta la doc.
- **Picos (apertura de agenda / horario pico)**: el límite aparece cuando muchos usuarios consultan disponibilidad a la vez; ahí dependés mucho de que el **caché de slots** funcione y de que no se dispare CPU/DB.

> Importante: en `SETUP_PRODUCTION.md` se recomienda un Gunicorn “grande” (4 workers * 2 threads). Con **512 MB** eso puede ser **demasiado** y causar reinicios por memoria (OOM) si realmente está aplicado así.

---

### Dónde está el punto débil (dónde puede fallar primero)

- **Memoria en el web service (probable #1)**  
  - Si Gunicorn está con varios workers/threads, Django + dependencias + templates + buffers puede superar 512 MB y Render puede matar el proceso.
  - Síntoma típico: **restarts**, timeouts intermitentes, 502/503 en picos.

- **DB PostgreSQL (probable #2, sobre todo con 10 GB y crecimiento)**  
  - Aunque haya Redis, muchas acciones siguen pegando a DB (reservas, listados, admin, reportes).
  - En producción, al usar `dj_database_url.config(...)`, **no veo aplicado el `statement_timeout`** que sí aparece en la config “local”; entonces una query lenta puede comerse threads/workers y generar **cola**.

- **Tarea periódica de “marcar jugados” (riesgo fuerte con volumen)**  
  - `Turno.marcar_turnos_como_jugados()` recorre *todos* los turnos no cancelados/no jugados y actualiza uno por uno. Con muchos registros, cada hora puede transformarse en un **job pesado O(n)** que consuma DB/CPU y afecte al resto.

- **Backups diarios de DB (riesgo fuerte con DB de 10 GB)**  
  - `respaldar_base_datos_task()` corre `dbbackup` diario. Un dump de **10 GB** puede:
    - tardar bastante,
    - consumir CPU/IO,
    - y si el destino es disco “no persistente” o chico, fallar por espacio.
  - Si falla repetidamente, te llena logs y te da una falsa sensación de seguridad (no tenés backup real).

- **Redis como “pieza crítica” (sesiones + broker + caché)**  
  - El caché tiene `IGNORE_EXCEPTIONS=True` (bien para no tirar toda la web si Redis cae), pero **las sesiones en Redis** (`SESSION_ENGINE = cache`) pueden degradar la experiencia o romper autenticación si Redis está inestable.
  - Además Redis es broker/result backend de Celery: si Redis cae, **se frenan tareas y programadas** (limpieza, heartbeat, backups).

- **Celery worker/beat como single point of failure operativo**  
  - Si se cae **celery-beat**, se dejan de ejecutar tareas periódicas (limpieza expirados, marcar jugados, backups).
  - Si se cae **celery-worker**, se acumulan tareas (emails, invalidaciones, etc.). Hoy no veo un mecanismo de “alerta” más allá del heartbeat en cache.

---

### Fallos típicos que verías en producción (y por qué)

- **Timeouts/latencia alta al consultar disponibilidad**: CPU saturada o DB lenta; caché no pegando (misses) o invalidaciones frecuentes.
- **Reservas duplicadas o conflictos**: está bastante cubierto por la `UniqueConstraint` condicional en `Turno` (bien), pero bajo picos igual vas a ver más **IntegrityError** y reintentos.
- **Turnos “expirados” que no se liberan / “jugados” que no se marcan**: celery-beat/worker caído o Redis broker caído.
- **Caídas “sin explicación”**: OOM por el web service (512 MB) o por jobs pesados (backup/mark-jugados) coincidiendo con tráfico.

---

### Si querés, te lo bajo a números y acciones concretas
Decime dos datos y te doy una estimación más precisa + checklist de monitoreo:
- **Cuántos complejos/canchas** y **turnos totales** aproximados en DB (orden de magnitud).
- **Tu comando real de Gunicorn en Render** (workers/threads/timeout).

---

**User**

Este es mi comando de Gunicorn render: python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 4 --threads 2 --worker-class gthread --worker-tmp-dir /dev/shm --timeout 60 --max-requests 1000 --max-requests-jitter 50 --log-level info

Complejos 10 y 4 canchas cada uno. 12 turnos por dia por cancha

---

**Cursor**

### Con tus números (10 complejos, 4 canchas c/u, 12 turnos/día/cancha)

- **Capacidad “de negocio” diaria**: \(10 \times 4 \times 12 = 480\) turnos/día (si todos se ocupan).
- **Carga típica en la web**: el “pico” no viene por crear 480 turnos/día, sino por **muchas consultas de disponibilidad/agenda en simultáneo** (HTMX suele generar varias requests por usuario).
- **Tamaño de datos**: aun con 6 meses de historial serían ~\(480 \times 180 \approx 86.400\) turnos; no es enorme, pero ya alcanza para que algunas tareas/consultas mal hechas se noten.

---

### Tu comando de Gunicorn es el punto más débil (para 0.5 CPU / 512MB)

Tu actual:

`--workers 4 --threads 2` ⇒ **8 threads** + 4 procesos Django. En **512MB** esto es el escenario más común de:
- **OOM / reinicios** (memoria)
- **CPU thrashing** (0.5 CPU con muchos threads/procesos compitiendo)
- **picos con latencia** (colas por saturación)

#### Recomendación práctica (más estable en Render chico)
Probá bajar agresivamente:

```bash
python manage.py migrate --noinput && \
gunicorn config.wsgi:application \
  --bind 0.0.0.0:$PORT \
  --workers 2 \
  --threads 1 \
  --worker-class gthread \
  --timeout 60 \
  --max-requests 1000 \
  --max-requests-jitter 50 \
  --log-level info
```

Si ves que se queda corto en concurrencia, siguiente escalón:

```bash
--workers 2 --threads 2
```

Yo **no** usaría 4 workers en 512MB salvo que hayas medido RSS real y te sobre memoria.

---

### Segundo punto débil: migraciones en cada deploy (y en el arranque del web)
`python manage.py migrate` en el start command puede:
- alargar el arranque (y Render puede marcarlo unhealthy),
- competir con tráfico si el deploy hace rolling,
- y si alguna migración tarda, te deja la web fuera.

Ideal: mover migraciones a una fase “release”/job separado (según cómo tengas Render configurado).

---

### Riesgos concretos con tu stack (ordenados por probabilidad)

- **(1) Memoria/CPU del servicio web** por la configuración actual de Gunicorn.
- **(2) DB + consultas pesadas en picos**: la disponibilidad (slots) está optimizada con caché, pero si Redis no está bien habilitado o hay muchos cache-miss, la DB sufre.
- **(3) Backups diarios de una DB de 10GB**: es pesado y puede fallar por tiempo/espacio/destino no persistente (y entonces “creés” que tenés backup pero no).
- **(4) Tarea `marcar_turnos_como_jugados()`**: hoy itera uno por uno; con el tiempo puede volverse un job que carga DB (hoy con tu volumen no explota, pero escala mal).
- **(5) Redis como SPOF operativo**: si Redis cae, Celery y sesiones/caché se degradan (aunque el caché está configurado para “no romper” la web).

---

### Dos checks rápidos que cambian mucho el resultado
- **¿En producción tenés `ENABLE_REDIS=True` y `ENABLE_CELERY=True`?** (en tu `env.example` veo `ENABLE_REDIS=False`; si eso está así en Render, perdés sesiones/caché compartido y tu web se vuelve mucho más DB-bound).
- **¿Dónde guardan los backups (`BACKUP_DIR`) y es persistente?** Con 10GB esto es crítico.

Si me pegás tus variables de entorno reales de Render (sin secretos; solo flags y URLs recortadas) te digo exactamente si hoy estás corriendo con Redis/sesiones/caché como corresponde y qué riesgo te queda primero.

```shellscript
python manage.py migrate --noinput && \
gunicorn config.wsgi:application \
  --bind 0.0.0.0:$PORT \
  --workers 2 \
  --threads 1 \
  --worker-class gthread \
  --timeout 60 \
  --max-requests 1000 \
  --max-requests-jitter 50 \
  --log-level info
```

```shellscript
--workers 2 --threads 2
```

