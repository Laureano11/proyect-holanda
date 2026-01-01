"""
Configuración del proyecto.
Inicializa Celery para que se cargue cuando Django inicia.
"""

# Esto asegura que la app Celery siempre se importe cuando Django inicia
# para que shared_task use esta app.
from .celery import app as celery_app

__all__ = ('celery_app',)

