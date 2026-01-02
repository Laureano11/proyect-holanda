# Sistema de Gestión de Turnos 🎾

Sistema para la gestión de reservas de canchas de pádel.

## Stack Tecnológico

- **Backend:** Python + Django 5.0 + PostgreSQL
- **Frontend:** Tailwind CSS + HTMX

## Requisitos Previos

- Python 3.10+
- PostgreSQL 14+

## Instalación

### 1. Clonar el repositorio y crear entorno virtual

```bash
cd project-holanda
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con tus configuraciones
```

### 4. Crear la base de datos en PostgreSQL

```sql
CREATE DATABASE turnos_db;
```

### 5. Ejecutar migraciones

```bash
python manage.py makemigrations
python manage.py migrate
```

### 6. Crear superusuario

```bash
python manage.py createsuperuser
```

### 7. Ejecutar servidor de desarrollo

```bash
python manage.py runserver
```

El sistema estará disponible en: http://localhost:8000

## Estructura del Proyecto

```
project-holanda/
├── config/                 # Configuración del proyecto Django
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── core/                   # App principal
│   ├── models.py          # Modelos de la BD
│   ├── admin.py           # Configuración del admin
│   ├── views.py
│   └── urls.py
├── templates/              # Templates HTML
├── static/                 # Archivos estáticos
├── media/                  # Archivos subidos
├── manage.py
├── requirements.txt
└── README.md
```

## Modelos de la Base de Datos

### Usuario
- Extiende el modelo de usuario de Django
- Roles: Admin / Cliente
- Campos adicionales: DNI, celular, dirección

### Complejo
- Nombre, dirección, teléfono, email
- Horarios de operación
- Logo

### PreferenciasComplejo
- Configuración visual (colores)
- Features habilitadas (ranking, seña, turnos fijos, etc.)

### Cancha
- Pertenece a un Complejo
- Precio por hora (seña = precio / 4)
- Capacidad (4 jugadores por defecto)
- Características (techada, iluminada, etc.)

### Turno
- Reserva de 1 hora de duración
- Estados: Reservado, Pagado, Cancelado
- Precio y seña pagada

### TurnoFijo
- Turnos recurrentes semanales
- Día de la semana y hora
- Fecha de inicio y fin

## Panel de Administración

Acceder a: http://localhost:8000/admin/

## 📚 Documentación Completa

### Guías Principales

| Documento | Descripción | Para |
|-----------|-------------|------|
| **[SETUP_PRODUCTION.md](SETUP_PRODUCTION.md)** | Guía completa de optimizaciones, setup, verificación y deployment | Cualquiera |
| **[SETUP_REDIS_CELERY.md](SETUP_REDIS_CELERY.md)** | Guía rápida para instalar Redis y Celery | Primeros pasos en desarrollo |
| **[DOCUMENTACION_CONSOLIDADA.md](DOCUMENTACION_CONSOLIDADA.md)** | Explicación de cómo se organizó la documentación | Entender la estructura |

### Documentación Específica

| Documento | Descripción |
|-----------|-------------|
| **[README_EMAIL.md](README_EMAIL.md)** | Configuración de envío de emails |
| **[ASYNC_EMAIL_FIX.md](ASYNC_EMAIL_FIX.md)** | Detalles de fix de emails asincrónico |

---

## 🚀 Inicio Rápido

### Desarrollo

```bash
# 1. Setup básico
source venv/bin/activate
pip install -r requirements.txt

# 2. Leer guía de Redis/Celery
# Ver: SETUP_REDIS_CELERY.md

# 3. Iniciar servicios
python manage.py runserver
celery -A config worker -l info
celery -A config beat -l info
```

### Producción (Render)

```bash
# Seguir guía completa:
# Ver: SETUP_PRODUCTION.md → Deployment en Producción
```

---

## 🔥 Optimizaciones Implementadas

✅ **Redis** - Caché compartido entre workers (10x más rápido)
✅ **Queries N+1** - Optimizadas con select_related (90% menos queries)
✅ **Celery** - Tareas asincrónicas en background
✅ **Sessions** - En Redis para mejor rendimiento
✅ **Connection Pooling** - Reutilización de conexiones DB
✅ **Middleware** - Caché de resolución de complejos

**Resultado:** 10x más rápido, 5x menos CPU, 100+ usuarios concurrentes

Para detalles: [SETUP_PRODUCTION.md](SETUP_PRODUCTION.md)

---

## Licencia

Proyecto privado.

