"""
Tareas asincrónicas con Celery para el sistema de turnos.
"""

from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging
from django.core.management import call_command
from django.core.cache import cache

logger = logging.getLogger(__name__)


@shared_task(name='core.tasks.marcar_turnos_jugados_task')
def marcar_turnos_jugados_task():
    """
    Tarea periódica: marca turnos que ya pasaron como 'jugado'.
    Se ejecuta cada hora vía Celery Beat.
    """
    from .models import Turno
    
    try:
        cantidad = Turno.marcar_turnos_como_jugados()
        logger.info(f"Turnos marcados como jugados: {cantidad}")
        return {'exito': True, 'cantidad': cantidad}
    except Exception as e:
        logger.error(f"Error marcando turnos como jugados: {str(e)}")
        return {'exito': False, 'error': str(e)}


@shared_task(name='core.tasks.limpiar_turnos_expirados_task')
def limpiar_turnos_expirados_task():
    """
    Tarea periódica: marca turnos pendientes de pago que expiraron.
    Se ejecuta cada 10 minutos vía Celery Beat.
    """
    from .models import Turno
    
    try:
        ahora = timezone.now()
        turnos_expirados = Turno.objects.filter(
            estado=Turno.Estado.PENDIENTE_PAGO,
            expira_en__lt=ahora
        )
        
        cantidad = turnos_expirados.count()
        turnos_expirados.update(
            estado=Turno.Estado.EXPIRADO,
            cancelacion_origen=Turno.CancelacionOrigen.SISTEMA,
            cancelacion_motivo="Expirado por falta de pago",
            cancelado_por=None,
            cancelado_en=ahora,
        )
        
        logger.info(f"Turnos expirados limpiados: {cantidad}")
        return {'exito': True, 'cantidad': cantidad}
    except Exception as e:
        logger.error(f"Error limpiando turnos expirados: {str(e)}")
        return {'exito': False, 'error': str(e)}


@shared_task(name='core.tasks.invalidar_cache_complejo')
def invalidar_cache_complejo(complejo_id, fecha_str):
    """
    Invalida el caché de slots para un complejo y fecha específicos.
    Útil cuando se crea/modifica/cancela un turno.
    """
    from .services import TurnoService
    from datetime import datetime
    
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        TurnoService.invalidar_cache_slots(complejo_id, fecha)
        logger.info(f"Caché invalidado para complejo {complejo_id}, fecha {fecha_str}")
        return {'exito': True}
    except Exception as e:
        logger.error(f"Error invalidando caché: {str(e)}")
        return {'exito': False, 'error': str(e)}


@shared_task(bind=True, max_retries=3, name='core.tasks.enviar_email_async')
def enviar_email_async(self, subject, message, from_email, recipient_list):
    """
    Envía emails de forma asincrónica.
    Reintentos automáticos en caso de fallo.
    """
    from django.core.mail import send_mail
    
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            fail_silently=False,
        )
        logger.info(f"Email enviado a {recipient_list}")
        return {'exito': True}
    except Exception as exc:
        logger.error(f"Error enviando email: {str(exc)}")
        # Reintentar en 5 minutos
        raise self.retry(exc=exc, countdown=300)


@shared_task(name='core.tasks.respaldar_base_datos_task')
def respaldar_base_datos_task():
    """
    Genera un backup de la base de datos usando django-dbbackup.
    Incluye limpieza automática según DBBACKUP_CLEANUP_KEEP.
    """
    try:
        # clean=True respeta DBBACKUP_CLEANUP_KEEP para retención
        call_command('dbbackup', clean=True, verbosity=1)
        logger.info("Backup de base de datos generado exitosamente")
        return {'exito': True}
    except Exception as exc:
        logger.exception("Error al generar backup de base de datos")
        return {'exito': False, 'error': str(exc)}


@shared_task(name='core.tasks.ops_celery_ping_task')
def ops_celery_ping_task():
    """
    Tarea liviana para validar que el celery-worker está procesando jobs.
    """
    return {
        'ok': True,
        'ts': timezone.now().isoformat(),
    }


@shared_task(name='core.tasks.ops_celery_beat_heartbeat_task')
def ops_celery_beat_heartbeat_task():
    """
    Tarea periódica (Beat) que escribe un heartbeat en Redis/cache.
    El endpoint ops lo usa para confirmar que celery-beat está corriendo.
    """
    try:
        now = timezone.now()
        cache.set('ops:celery_beat_heartbeat', now.isoformat(), timeout=60 * 60)
        return {'ok': True, 'ts': now.isoformat()}
    except Exception as exc:
        logger.exception("Error escribiendo heartbeat de celery-beat")
        return {'ok': False, 'error': str(exc)}

