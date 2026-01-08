"""
Configuración de Celery para tareas asincrónicas.
"""

import os
from celery import Celery
from celery.schedules import crontab

# Configurar Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('turnos')

# Cargar configuración desde Django settings con namespace 'CELERY'
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-descubrir tareas en todas las apps instaladas
app.autodiscover_tasks()


# Configurar Celery Beat Schedule (tareas periódicas)
app.conf.beat_schedule = {
    # Marcar turnos como jugados cada hora
    'marcar-turnos-jugados': {
        'task': 'core.tasks.marcar_turnos_jugados_task',
        'schedule': crontab(minute=0),  # Cada hora en punto
    },
    # Limpiar turnos expirados cada 10 minutos
    'limpiar-turnos-expirados': {
        'task': 'core.tasks.limpiar_turnos_expirados_task',
        'schedule': crontab(minute='*/10'),  # Cada 10 minutos
    },
    # Backup completo de la base de datos diariamente a las 03:30 AM
    'backup-base-datos-diario': {
        'task': 'core.tasks.respaldar_base_datos_task',
        'schedule': crontab(minute=30, hour=3),
    },
    # Heartbeat para validar que celery-beat está corriendo (cada minuto)
    'ops-celery-beat-heartbeat': {
        'task': 'core.tasks.ops_celery_beat_heartbeat_task',
        'schedule': crontab(minute='*/1'),
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Tarea de debug para verificar que Celery funciona."""
    print(f'Request: {self.request!r}')

