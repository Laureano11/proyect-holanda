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

## Licencia

Proyecto privado.

