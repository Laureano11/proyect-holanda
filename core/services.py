"""
Servicios de lógica de negocio para el sistema de turnos.
Centraliza la lógica compleja y optimiza las consultas a la base de datos.
"""

from django.utils import timezone
from django.db.models import Sum
from django.core.cache import cache
from datetime import datetime, timedelta
from decimal import Decimal
import requests
from django.conf import settings


class TurnoService:
    """
    Servicio para gestión de turnos y slots disponibles.
    Optimiza las consultas y centraliza la lógica de negocio.
    """
    
    # Tiempo de caché para slots disponibles (en segundos)
    CACHE_TIMEOUT = 300  # 5 minutos
    # Para "hoy" usamos un TTL corto porque es lo más consultado y cambia seguido.
    # Con invalidación explícita al reservar/cancelar, esto reduce carga sin mostrar datos stale mucho tiempo.
    CACHE_TODAY_TIMEOUT = 15  # segundos
    
    @staticmethod
    def get_cache_key(complejo_id, fecha):
        """Genera la clave de caché para los slots de un día."""
        return f'slots_disponibles_{complejo_id}_{fecha.isoformat()}'
    
    @staticmethod
    def invalidar_cache_slots(complejo_id, fecha):
        """Invalida el caché de slots para una fecha específica."""
        cache_key = TurnoService.get_cache_key(complejo_id, fecha)
        cache.delete(cache_key)

    @staticmethod
    def obtener_ventana_horaria(complejo, fecha):
        """
        Retorna la ventana horaria efectiva (apertura, cierre) como datetimes.
        Si el cierre es menor o igual a la apertura, se interpreta como cierre al día siguiente.
        """
        apertura_dt = datetime.combine(fecha, complejo.hora_apertura)
        cierre_dt = datetime.combine(fecha, complejo.hora_cierre)
        if cierre_dt <= apertura_dt:
            cierre_dt += timedelta(days=1)
        return apertura_dt, cierre_dt

    @staticmethod
    def obtener_fecha_real_turno(complejo, fecha_base, hora_turno):
        """
        Convierte una fecha operativa (día de la grilla) a fecha real de juego.
        Si el complejo cruza medianoche, las horas menores a apertura pertenecen al día siguiente.
        """
        if complejo.hora_cierre <= complejo.hora_apertura and hora_turno < complejo.hora_apertura:
            return fecha_base + timedelta(days=1)
        return fecha_base

    @staticmethod
    def expirar_turnos_pendientes(complejo, fecha, ahora=None):
        """
        Marca como expirados los turnos pendientes cuyo expira_en ya pasó.
        Devuelve la cantidad de turnos actualizados.
        """
        from .models import Turno
        if ahora is None:
            ahora = timezone.now()
        turnos_expirados = Turno.objects.filter(
            cancha__complejo=complejo,
            fecha=fecha,
            estado=Turno.Estado.PENDIENTE_PAGO,
            expira_en__lt=ahora
        )
        cantidad = turnos_expirados.count()
        if cantidad:
            turnos_expirados.update(
                estado=Turno.Estado.EXPIRADO,
                cancelacion_origen=Turno.CancelacionOrigen.SISTEMA,
                cancelacion_motivo="Expirado por falta de pago",
                cancelado_por=None,
                cancelado_en=ahora,
            )
        return cantidad
    
    @staticmethod
    def preprocesar_bloqueos(bloqueos):
        """
        Preprocesa los bloqueos para búsqueda O(1) en lugar de O(n).
        Retorna: (bloqueos_globales, bloqueos_por_cancha)
        """
        bloqueos_por_cancha = {}
        bloqueos_globales = []
        
        for bloqueo in bloqueos:
            if bloqueo.cancha is None:
                bloqueos_globales.append(bloqueo)
            else:
                cancha_id = bloqueo.cancha_id
                if cancha_id not in bloqueos_por_cancha:
                    bloqueos_por_cancha[cancha_id] = []
                bloqueos_por_cancha[cancha_id].append(bloqueo)
        
        return bloqueos_globales, bloqueos_por_cancha
    
    @staticmethod
    def hora_esta_bloqueada(hora, bloqueos_relevantes):
        """Verifica si una hora está bloqueada por alguno de los bloqueos."""
        for bloqueo in bloqueos_relevantes:
            if bloqueo.es_dia_completo:
                return True
            elif bloqueo.hora_inicio and bloqueo.hora_fin:
                if bloqueo.hora_inicio <= hora < bloqueo.hora_fin:
                    return True
            elif bloqueo.hora_inicio and hora >= bloqueo.hora_inicio:
                return True
        return False
    
    @classmethod
    def generar_slots_disponibles(cls, complejo, fecha, use_cache=True):
        """
        Genera los slots disponibles para un complejo en una fecha.
        Optimizado con caché y preprocesamiento de bloqueos.
        
        IMPORTANTE: Los turnos se generan respetando los horarios del complejo.
        El último turno disponible debe TERMINAR a la hora de cierre, no empezar.
        Ejemplo: Si cierra a las 20:00 y turnos de 1 hora, el último turno es 19:00-20:00.
        
        Args:
            complejo: Instancia del Complejo
            fecha: date object
            use_cache: Si True, intenta usar caché
            
        Returns:
            dict con slots_por_hora, total_disponibles, es_fecha_pasada
        """
        from .models import Cancha, Turno, TurnoFijo, Bloqueo, PreferenciasComplejo
        
        # Expirar pendientes vencidos de hoy/fecha antes de calcular slots
        cls.expirar_turnos_pendientes(complejo, fecha)

        # Intentar obtener de caché
        cache_key = cls.get_cache_key(complejo.id, fecha)
        if use_cache:
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                # Recalcular es_fecha_pasada porque puede cambiar
                ahora = timezone.now()
                cached_result['es_fecha_pasada'] = fecha < ahora.date()
                return cached_result
        
        ahora = timezone.now()
        hoy_actual = ahora.date()
        es_fecha_pasada = fecha < hoy_actual
        
        # Obtener canchas activas (single query)
        canchas = list(Cancha.objects.filter(
            complejo=complejo, 
            activa=True
        ).order_by('nombre'))
        
        if not canchas:
            return {
                'slots_por_hora': {},
                'total_disponibles': 0,
                'es_fecha_pasada': es_fecha_pasada
            }
        
        # Obtener turnos ocupados considerando fecha real cuando cruza medianoche
        turnos_ocupados_qs = Turno.objects.filter(cancha__complejo=complejo)
        if complejo.hora_cierre <= complejo.hora_apertura:
            turnos_ocupados_qs = turnos_ocupados_qs.filter(
                fecha=fecha
            ) | Turno.objects.filter(
                cancha__complejo=complejo,
                fecha=fecha + timedelta(days=1),
                hora_inicio__lt=complejo.hora_apertura,
            )
        else:
            turnos_ocupados_qs = turnos_ocupados_qs.filter(fecha=fecha)

        turnos_ocupados = set(turnos_ocupados_qs.exclude(
            estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
        ).values_list('cancha_id', 'hora_inicio'))
        
        # Obtener turnos fijos que aplican (con select_related)
        dia_semana_fecha = fecha.weekday()
        
        # Filtrar turnos fijos (fecha_fin es None O fecha_fin >= fecha)
        turnos_fijos_filtrados = []
        for tf in TurnoFijo.objects.filter(
            cancha__complejo=complejo,
            activo=True,
            dia_semana=dia_semana_fecha,
            fecha_inicio__lte=fecha
        ).select_related('cancha'):
            if tf.fecha_fin is None or fecha <= tf.fecha_fin:
                turnos_fijos_filtrados.append((tf.cancha_id, tf.hora_inicio))
        
        # Combinar ocupados
        ocupados_set = turnos_ocupados | set(turnos_fijos_filtrados)
        
        # Obtener bloqueos y preprocesarlos (O(n) una vez, luego O(1))
        bloqueos = list(Bloqueo.objects.filter(
            complejo=complejo,
            fecha=fecha
        ).select_related('cancha'))
        
        bloqueos_globales, bloqueos_por_cancha = cls.preprocesar_bloqueos(bloqueos)
        
        # Generar slots
        slots_por_hora = {}
        apertura_dt, cierre_dt = cls.obtener_ventana_horaria(complejo, fecha)
        total_disponibles = 0
        
        for cancha in canchas:
            duracion_turno = cancha.get_duracion_turno()
            inicio_dt = apertura_dt

            while inicio_dt < cierre_dt:
                # Calcular hora de fin del turno basado en duración de la cancha
                fin_dt = inicio_dt + timedelta(minutes=duracion_turno)
                hora_fin = fin_dt.time()
                hora_actual = inicio_dt.time()
                
                # IMPORTANTE: El turno debe TERMINAR antes o exactamente a la hora de cierre
                # Si el turno terminaría después del cierre, no lo generamos
                if fin_dt > cierre_dt:
                    break
                
                # Si es hoy, verificar que el turno no haya empezado
                if fecha == hoy_actual:
                    inicio_turno = timezone.make_aware(datetime.combine(inicio_dt.date(), hora_actual))
                    if ahora > inicio_turno:
                        inicio_dt = inicio_dt + timedelta(minutes=duracion_turno)
                        continue
                
                # Obtener bloqueos relevantes (O(1) lookup)
                bloqueos_relevantes = bloqueos_globales + bloqueos_por_cancha.get(cancha.id, [])
                
                # Verificar estado
                esta_bloqueada = cls.hora_esta_bloqueada(hora_actual, bloqueos_relevantes)
                esta_ocupada = (cancha.id, hora_actual) in ocupados_set
                
                if es_fecha_pasada:
                    estado = 'no_disponible'
                elif esta_bloqueada:
                    estado = 'no_disponible'
                elif esta_ocupada:
                    estado = 'reservado'
                else:
                    estado = 'disponible'
                    if not es_fecha_pasada:
                        total_disponibles += 1
                
                slot = slots_por_hora.setdefault(hora_actual, {
                    'hora_inicio': hora_actual,
                    'hora_fin': None,
                    'hora_fin_set': set(),
                    'canchas': [],
                    'canchas_disponibles_count': 0,
                })
                
                slot['canchas'].append({
                    'cancha': cancha,
                    'precio': cancha.precio_hora,
                    'senia': cancha.precio_senia,
                    'estado': estado,
                    'hora': hora_actual,
                    'hora_fin': hora_fin,
                    'duracion_minutos': duracion_turno,
                })
                slot['hora_fin_set'].add(hora_fin)
                if estado == 'disponible' and not es_fecha_pasada:
                    slot['canchas_disponibles_count'] += 1
                
                # Avanzar según la duración del turno de la cancha
                inicio_dt = inicio_dt + timedelta(minutes=duracion_turno)
        
        for slot in slots_por_hora.values():
            if len(slot['hora_fin_set']) == 1:
                slot['hora_fin'] = next(iter(slot['hora_fin_set']))
            else:
                slot['hora_fin'] = None
            del slot['hora_fin_set']
        
        result = {
            'slots_por_hora': slots_por_hora,
            'total_disponibles': total_disponibles,
            'es_fecha_pasada': es_fecha_pasada
        }
        
        # Guardar en caché:
        # - Fechas futuras: CACHE_TIMEOUT
        # - Hoy: TTL corto para aliviar el dashboard del cliente (suele consultarse mucho)
        # - Fechas pasadas: no cachear
        if use_cache and fecha >= hoy_actual:
            ttl = cls.CACHE_TODAY_TIMEOUT if fecha == hoy_actual else cls.CACHE_TIMEOUT
            cache.set(cache_key, result, ttl)
        
        return result
    
    @classmethod
    def generar_slots_staff(cls, complejo, fecha):
        """
        Genera slots disponibles para el staff (solo disponibles, sin todos los estados).
        
        IMPORTANTE: Los turnos se generan respetando los horarios del complejo.
        El último turno disponible debe TERMINAR a la hora de cierre, no empezar.
        """
        from .models import Cancha, Turno, Bloqueo, PreferenciasComplejo
        
        # Expirar pendientes vencidos de hoy/fecha antes de calcular slots
        cls.expirar_turnos_pendientes(complejo, fecha)

        ahora = timezone.now()
        hoy_actual = ahora.date()
        
        # Obtener canchas activas
        canchas = list(Cancha.objects.filter(
            complejo=complejo, 
            activa=True
        ).order_by('nombre'))
        
        if not canchas:
            return {}
        
        # Obtener turnos ocupados considerando fecha real cuando cruza medianoche
        turnos_ocupados_qs = Turno.objects.filter(cancha__complejo=complejo)
        if complejo.hora_cierre <= complejo.hora_apertura:
            turnos_ocupados_qs = turnos_ocupados_qs.filter(
                fecha=fecha
            ) | Turno.objects.filter(
                cancha__complejo=complejo,
                fecha=fecha + timedelta(days=1),
                hora_inicio__lt=complejo.hora_apertura,
            )
        else:
            turnos_ocupados_qs = turnos_ocupados_qs.filter(fecha=fecha)

        turnos_ocupados = set(turnos_ocupados_qs.exclude(
            estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
        ).values_list('cancha_id', 'hora_inicio'))
        
        # Obtener y preprocesar bloqueos
        bloqueos = list(Bloqueo.objects.filter(
            complejo=complejo,
            fecha=fecha
        ).select_related('cancha'))
        
        bloqueos_globales, bloqueos_por_cancha = cls.preprocesar_bloqueos(bloqueos)
        
        # Generar slots
        slots_por_hora = {}
        apertura_dt, cierre_dt = cls.obtener_ventana_horaria(complejo, fecha)
        
        for cancha in canchas:
            duracion_turno = cancha.get_duracion_turno()
            inicio_dt = apertura_dt
            
            while inicio_dt < cierre_dt:
                # Calcular hora de fin del turno basado en duración de la cancha
                fin_dt = inicio_dt + timedelta(minutes=duracion_turno)
                hora_fin = fin_dt.time()
                hora_actual = inicio_dt.time()
                
                # IMPORTANTE: El turno debe TERMINAR antes o exactamente a la hora de cierre
                if fin_dt > cierre_dt:
                    break
                
                # Si es hoy, verificar que el turno no haya empezado
                if fecha == hoy_actual:
                    inicio_turno = timezone.make_aware(datetime.combine(inicio_dt.date(), hora_actual))
                    if ahora > inicio_turno:
                        inicio_dt = inicio_dt + timedelta(minutes=duracion_turno)
                        continue
                
                bloqueos_relevantes = bloqueos_globales + bloqueos_por_cancha.get(cancha.id, [])
                esta_bloqueada = cls.hora_esta_bloqueada(hora_actual, bloqueos_relevantes)
                esta_ocupada = (cancha.id, hora_actual) in turnos_ocupados
                
                if not esta_bloqueada and not esta_ocupada:
                    slot = slots_por_hora.setdefault(hora_actual, {
                        'hora_inicio': hora_actual,
                        'hora_fin': None,
                        'hora_fin_set': set(),
                        'canchas': [],
                    })
                    slot['canchas'].append({
                        'cancha': cancha,
                        'precio': cancha.precio_hora,
                        'senia': cancha.precio_senia,
                        'hora': hora_actual,
                        'hora_fin': hora_fin,
                        'duracion_minutos': duracion_turno,
                    })
                    slot['hora_fin_set'].add(hora_fin)
                
                # Avanzar según la duración del turno de la cancha
                inicio_dt = inicio_dt + timedelta(minutes=duracion_turno)
        
        for slot in slots_por_hora.values():
            if len(slot['hora_fin_set']) == 1:
                slot['hora_fin'] = next(iter(slot['hora_fin_set']))
            else:
                slot['hora_fin'] = None
            del slot['hora_fin_set']
        
        return slots_por_hora
    
    @staticmethod
    def validar_disponibilidad(cancha, fecha, hora):
        """
        Valida si un turno está disponible para reservar.
        
        Returns:
            tuple: (disponible: bool, mensaje_error: str o None)
        """
        from .models import Turno, Bloqueo, TurnoFijo
        
        ahora = timezone.now()
        apertura_dt, cierre_dt = TurnoService.obtener_ventana_horaria(cancha.complejo, fecha)
        fecha_hora_turno = datetime.combine(fecha, hora)
        # Si el complejo cruza medianoche (ej: 15:00 a 01:00), los horarios de
        # madrugada pertenecen operativamente al mismo día base pero ocurren al día siguiente.
        if cancha.complejo.hora_cierre <= cancha.complejo.hora_apertura and hora < cancha.complejo.hora_apertura:
            fecha_hora_turno = fecha_hora_turno + timedelta(days=1)
        if timezone.is_naive(apertura_dt):
            apertura_dt = timezone.make_aware(apertura_dt)
        if timezone.is_naive(cierre_dt):
            cierre_dt = timezone.make_aware(cierre_dt)
        fecha_hora_turno = timezone.make_aware(fecha_hora_turno)
        
        # Expirar pendientes vencidos antes de validar
        TurnoService.expirar_turnos_pendientes(cancha.complejo, fecha, ahora=ahora)

        # Verificar que no sea en el pasado
        if fecha_hora_turno < ahora:
            return False, 'No se puede reservar un turno en el pasado'

        # Verificar que esté dentro del horario operativo del complejo
        if not (apertura_dt <= fecha_hora_turno < cierre_dt):
            return False, 'Este horario está fuera del horario de apertura'
        
        # Verificar turno existente
        fecha_real_turno = TurnoService.obtener_fecha_real_turno(cancha.complejo, fecha, hora)
        turno_existente = Turno.objects.filter(
            cancha=cancha,
            fecha=fecha_real_turno,
            hora_inicio=hora
        ).exclude(
            estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
        ).exists()
        
        if turno_existente:
            return False, 'Este turno ya está reservado'
        
        # Verificar turno fijo
        dia_semana = fecha.weekday()
        turno_fijo_existe = TurnoFijo.objects.filter(
            cancha=cancha,
            dia_semana=dia_semana,
            hora_inicio=hora,
            activo=True,
            fecha_inicio__lte=fecha
        ).filter(
            # fecha_fin is None OR fecha_fin >= fecha
        ).exists()
        
        # Verificar manualmente fecha_fin
        for tf in TurnoFijo.objects.filter(
            cancha=cancha,
            dia_semana=dia_semana,
            hora_inicio=hora,
            activo=True,
            fecha_inicio__lte=fecha
        ):
            if tf.fecha_fin is None or fecha <= tf.fecha_fin:
                return False, 'Este horario está reservado como turno fijo'
        
        # Verificar bloqueos
        bloqueos = Bloqueo.objects.filter(
            complejo=cancha.complejo,
            fecha=fecha
        ).select_related('cancha')
        
        for bloqueo in bloqueos:
            if bloqueo.cancha is None or bloqueo.cancha == cancha:
                if bloqueo.es_dia_completo:
                    return False, 'Este día está bloqueado'
                elif bloqueo.hora_inicio and bloqueo.hora_fin:
                    if bloqueo.hora_inicio <= hora < bloqueo.hora_fin:
                        return False, 'Este horario está bloqueado'
                elif bloqueo.hora_inicio and hora >= bloqueo.hora_inicio:
                    return False, 'Este horario está bloqueado'
        
        return True, None


class CreditoService:
    """
    Servicio para gestión de créditos de clientes.
    """
    
    @staticmethod
    def aplicar_creditos(usuario, complejo, monto_requerido):
        """
        Aplica créditos del usuario para cubrir un monto.
        Usa los créditos más antiguos primero (FIFO).
        
        Args:
            usuario: Usuario que paga
            complejo: Complejo donde se usa el crédito
            monto_requerido: Decimal con el monto a cubrir
            
        Returns:
            Decimal: Monto efectivamente cubierto con créditos
        """
        from .models import CreditoCliente
        from django.utils import timezone
        
        creditos_activos = CreditoCliente.objects.filter(
            usuario=usuario,
            complejo=complejo,
            activo=True
        ).order_by('created_at')
        
        creditos_aplicados = Decimal('0.00')
        
        for credito in creditos_activos:
            if creditos_aplicados >= monto_requerido:
                break
            
            saldo = credito.saldo_disponible
            if saldo > 0:
                monto_a_usar = min(saldo, monto_requerido - creditos_aplicados)
                monto_usado_anterior = credito.monto_usado
                credito.monto_usado += monto_a_usar
                
                # Registrar en historial
                if not isinstance(credito.historial, list):
                    credito.historial = []
                credito.historial.append({
                    'accion': 'aplicado',
                    'fecha': timezone.now().isoformat(),
                    'monto_aplicado': str(monto_a_usar),
                    'monto_usado_anterior': str(monto_usado_anterior),
                    'monto_usado_nuevo': str(credito.monto_usado),
                })
                
                credito.save(update_fields=['monto_usado', 'updated_at', 'historial'])
                creditos_aplicados += monto_a_usar
        
        return creditos_aplicados
    
    @staticmethod
    def generar_credito(usuario, complejo, monto, motivo, turno_origen=None, creado_por=None):
        """
        Genera un nuevo crédito para el usuario con validaciones de seguridad.
        
        Args:
            usuario: Usuario que recibe el crédito
            complejo: Complejo donde se genera el crédito
            monto: Monto del crédito (Decimal)
            motivo: Motivo del crédito (string)
            turno_origen: Turno que originó el crédito (opcional)
            creado_por: Usuario que crea el crédito (opcional, para auditoría)
            
        Returns:
            CreditoCliente: El crédito creado
            
        Raises:
            PermissionDenied: Si el creador no tiene permisos
            ValueError: Si hay errores de validación
        """
        from .models import CreditoCliente, Turno
        from django.core.exceptions import PermissionDenied, ValidationError
        from django.utils import timezone
        
        # Validación 1: Permisos del creador
        if creado_por and not creado_por.puede_gestionar_turnos:
            raise PermissionDenied(
                "Solo staff/admin puede generar créditos. "
                f"Usuario '{creado_por.username}' no tiene permisos."
            )
        
        # Validación 2: Usuario debe pertenecer al complejo
        if usuario.complejo != complejo:
            raise ValueError(
                f"El usuario '{usuario.username}' no pertenece al complejo '{complejo.nombre}'"
            )
        
        # Validación 3: Validar turno origen si existe
        if turno_origen:
            if turno_origen.cliente != usuario:
                raise ValueError(
                    f"El turno #{turno_origen.id} no pertenece al usuario '{usuario.username}'"
                )
            
            if turno_origen.cancha.complejo != complejo:
                raise ValueError(
                    f"El turno #{turno_origen.id} no pertenece al complejo '{complejo.nombre}'"
                )
            
            # Validar que el monto coincide con la seña pagada (con tolerancia de 0.01)
            diferencia = abs(monto - turno_origen.senia_pagada)
            if diferencia > Decimal('0.01'):
                raise ValueError(
                    f"El monto del crédito (${monto}) debe coincidir con la seña pagada "
                    f"(${turno_origen.senia_pagada}) del turno #{turno_origen.id}"
                )
        
        # Validación 4: Monto debe ser positivo
        if monto <= Decimal('0.00'):
            raise ValueError("El monto del crédito debe ser mayor a cero")
        
        # Crear crédito con auditoría
        credito = CreditoCliente(
            usuario=usuario,
            complejo=complejo,
            monto=monto,
            motivo=motivo,
            turno_origen=turno_origen,
            creado_por=creado_por,
        )
        
        # Registrar creación en historial
        credito.historial = [{
            'accion': 'creado',
            'fecha': timezone.now().isoformat(),
            'monto': str(monto),
            'motivo': motivo,
            'creado_por': creado_por.username if creado_por else 'sistema',
            'turno_origen_id': turno_origen.id if turno_origen else None,
        }]
        
        # Validar y guardar
        try:
            credito.full_clean()
            credito.save()
        except ValidationError as e:
            raise ValueError(f"Error de validación: {e}")
        
        return credito


class MercadoPagoOAuthService:
    """
    Maneja intercambio/refresh de tokens OAuth de Mercado Pago a nivel de integración por complejo.
    """
    
    TOKEN_URL = "https://api.mercadopago.com/oauth/token"

    @staticmethod
    def refresh_tokens(integration):
        """
        Refresca el access_token usando refresh_token almacenado.
        Guarda los nuevos tokens cifrados en la integración.
        """
        from core.utils.crypto import decrypt_string
        
        if not integration.refresh_token:
            raise ValueError("No hay refresh_token guardado para este complejo.")
        
        refresh_token_plain = integration.refresh_token_plain
        data = {
            "grant_type": "refresh_token",
            "client_id": settings.MP_CLIENT_ID,
            "client_secret": settings.MP_CLIENT_SECRET,
            "refresh_token": refresh_token_plain,
        }
        resp = requests.post(MercadoPagoOAuthService.TOKEN_URL, json=data, timeout=10)
        body = resp.json()
        if resp.status_code >= 300:
            raise ValueError(body.get("message") or body.get("error") or body)
        
        access_token = body.get("access_token")
        new_refresh_token = body.get("refresh_token") or refresh_token_plain
        expires_in = body.get("expires_in")
        mp_user_id = body.get("user_id") or integration.mp_user_id
        
        if not access_token:
            raise ValueError("Mercado Pago no devolvió access_token en el refresh.")
        
        integration.set_tokens(access_token, refresh_token=new_refresh_token, expires_in=expires_in, mp_user_id=mp_user_id)
        integration.save()
        return integration
    
    @staticmethod
    def generar_turnos_desde_fijos(complejo, fecha_desde=None, fecha_hasta=None):
        """
        Genera turnos normales a partir de los turnos fijos para un rango de fechas.
        
        Args:
            complejo: Instancia del Complejo
            fecha_desde: date object (default: hoy)
            fecha_hasta: date object (default: 30 días desde fecha_desde)
            
        Returns:
            tuple: (turnos_creados, turnos_ya_existentes)
        """
        from .models import TurnoFijo, Turno
        from django.db import IntegrityError
        
        hoy = timezone.now().date()
        if fecha_desde is None:
            fecha_desde = hoy
        if fecha_hasta is None:
            fecha_hasta = fecha_desde + timedelta(days=30)
        
        turnos_creados = 0
        turnos_ya_existentes = 0
        
        # Obtener todos los turnos fijos activos del complejo
        turnos_fijos = TurnoFijo.objects.filter(
            cancha__complejo=complejo,
            activo=True
        ).select_related('cancha', 'cliente')
        
        # Iterar por cada día en el rango
        fecha_actual = fecha_desde
        while fecha_actual <= fecha_hasta:
            dia_semana = fecha_actual.weekday()
            
            # Filtrar turnos fijos que aplican para este día
            for turno_fijo in turnos_fijos:
                if turno_fijo.dia_semana != dia_semana:
                    continue
                
                # Verificar que la fecha esté dentro del rango del turno fijo
                if fecha_actual < turno_fijo.fecha_inicio:
                    continue
                if turno_fijo.fecha_fin and fecha_actual > turno_fijo.fecha_fin:
                    continue
                
                # Verificar si ya existe un turno para esta fecha/hora/cancha
                turno_existente = Turno.objects.filter(
                    cancha=turno_fijo.cancha,
                    fecha=fecha_actual,
                    hora_inicio=turno_fijo.hora_inicio
                ).first()
                
                if turno_existente:
                    turnos_ya_existentes += 1
                    continue
                
                # Crear el turno
                try:
                    Turno.objects.create(
                        cancha=turno_fijo.cancha,
                        cliente=turno_fijo.cliente,
                        fecha=fecha_actual,
                        hora_inicio=turno_fijo.hora_inicio,
                        estado=Turno.Estado.PENDIENTE_PAGO,
                        precio_total=turno_fijo.cancha.precio_hora,
                        senia_requerida=turno_fijo.cancha.precio_senia,
                        senia_pagada=Decimal('0.00'),
                        notas=f'Turno fijo: {turno_fijo.notas or ""}',
                    )
                    turnos_creados += 1
                    # Invalidar caché para esta fecha
                    TurnoService.invalidar_cache_slots(complejo.id, fecha_actual)
                except IntegrityError:
                    # Por si acaso hay una race condition
                    turnos_ya_existentes += 1
                    continue
            
            fecha_actual += timedelta(days=1)
        
        return turnos_creados, turnos_ya_existentes

