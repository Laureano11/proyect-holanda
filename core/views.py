"""
Views de la aplicación core.
"""

import os
from hmac import compare_digest

from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.core import signing
from django.core.cache import cache
from django.utils.dateparse import parse_datetime
from django.db import transaction, IntegrityError
from django.db.models import Sum, Q
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from urllib.parse import urlencode
from datetime import datetime, timedelta, time as dt_time
from decimal import Decimal
import base64
import hashlib
import secrets
import requests
import json
import logging
from .models import (
    Usuario,
    Complejo,
    Cancha,
    Turno,
    Bloqueo,
    CreditoCliente,
    TurnoFijo,
    IntegracionMercadoPago,
    PagoMercadoPago,
)
from .services import TurnoService, CreditoService
import mercadopago

logger = logging.getLogger(__name__)

DEFAULT_HOME_GALLERY_IMAGES = [
    {
        "image": "img/landing/screen1.png",
        "alt": "Panel de turnos en vivo mostrando disponibilidad",
        "caption": "Panel de turnos",
    },
    {
        "image": "img/landing/screen2.png",
        "alt": "Checkout y pagos integrados",
        "caption": "Pagos y señas",
    },
    {
        "image": "img/landing/screen3.png",
        "alt": "Gestión de staff y bloqueos manuales",
        "caption": "Gestión de staff",
    },
]


def _build_canonical_absolute_uri(request, path: str) -> str:
    """
    Construye una URL absoluta asegurando host canónico (sin `www.`).
    Esto evita pérdida de sesión cuando el usuario alterna www/no-www y vuelve
    desde redirects externos (Mercado Pago, OAuth, etc).
    """
    host = request.get_host()
    if host.lower().startswith("www."):
        host = host[4:]
    scheme = "https" if request.is_secure() else "http"
    return f"{scheme}://{host}{path}"


def _get_home_gallery_items():
    """Load gallery images from the configured folder (or fallback)."""
    gallery_dir = getattr(settings, "HOME_GALLERY_FOLDER", os.path.join(settings.BASE_DIR, "static", "img", "landing", "galeria"))
    supported_ext = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif"}
    images = []

    if not os.path.isdir(gallery_dir):
        return images

    for entry in sorted(os.listdir(gallery_dir)):
        entry_path = os.path.join(gallery_dir, entry)
        name, ext = os.path.splitext(entry)
        if ext.lower() not in supported_ext or not os.path.isfile(entry_path):
            continue

        caption = name.replace("-", " ").replace("_", " ").strip().capitalize()
        images.append(
            {
                "image": f"img/landing/galeria/{entry}",
                "alt": f"Galería · {caption or 'Imagen'}",
                "caption": caption or "Galería del sistema",
            }
        )

    return images


def _crear_preferencia_mp_para_turno(request, integration, turno, monto_mp):
    """
    Crea una preferencia de MP para cobrar el monto pendiente de seña.
    Devuelve (checkout_url, preference_id, external_reference).
    """
    sdk = mercadopago.SDK(integration.access_token_plain)
    feedback_url = _build_canonical_absolute_uri(request, reverse("mercadopago_feedback"))
    webhook_url = _build_canonical_absolute_uri(request, reverse("mercadopago_webhook"))
    external_reference = f"turno:{turno.id}"

    preference = {
        "items": [
            {
                "title": f"Seña turno {turno.cancha.nombre}",
                "quantity": 1,
                "unit_price": float(monto_mp),
                "currency_id": "ARS",
            }
        ],
        "back_urls": {
            "success": feedback_url,
            "failure": feedback_url,
            "pending": feedback_url,
        },
        "binary_mode": True,
        "external_reference": external_reference,
    }

    if feedback_url.startswith("https://"):
        preference["auto_return"] = "approved"
    if webhook_url.startswith("https://"):
        preference["notification_url"] = webhook_url

    preference_response = sdk.preference().create(preference)
    body = preference_response.get("response") or {}
    checkout_url = body.get("init_point") or body.get("sandbox_init_point")
    preference_id = body.get("id") or body.get("preference_id")

    if not checkout_url or not preference_id:
        mp_message = body.get("message") or body.get("error") or body.get("status")
        mp_cause = body.get("cause") or body.get("causes") or body.get("details")
        raise ValueError(f"MP no devolvió checkout/preference_id (message={mp_message}, cause={mp_cause}).")

    return checkout_url, preference_id, external_reference


def _devolver_creditos_turno(turno, motivo: str):
    """
    Devuelve créditos usados en un turno (si existen) y pone en cero la seña pagada por créditos.
    Retorna True si se devolvieron créditos.
    """
    if turno.creditos_usados <= 0:
        return False

    monto_devolver = turno.creditos_usados
    try:
        CreditoService.generar_credito(
            usuario=turno.cliente,
            complejo=turno.cancha.complejo,
            monto=monto_devolver,
            motivo=motivo,
            turno_origen=turno,
            creado_por=None,
        )
    except Exception as exc:  # pragma: no cover - defensivo
        logger.error(f"No se pudieron devolver créditos del turno {turno.id}: {exc}")
        return False

    nuevo_monto_senia = turno.senia_pagada - monto_devolver
    turno.senia_pagada = nuevo_monto_senia if nuevo_monto_senia > 0 else Decimal("0.00")
    turno.creditos_usados = Decimal("0.00")
    turno.save(update_fields=["senia_pagada", "creditos_usados", "updated_at"])
    return True


def home(request):
    """Vista principal del sistema para jugadores/clientes."""
    gallery_items = _get_home_gallery_items() or DEFAULT_HOME_GALLERY_IMAGES
    context = {"gallery_items": gallery_items}
    return render(request, 'home_cliente.html', context)


def landing(request):
    """Landing para dueños del complejo."""
    gallery_items = _get_home_gallery_items() or DEFAULT_HOME_GALLERY_IMAGES
    context = {"gallery_items": gallery_items}
    return render(request, 'home.html', context)


def turnos_publicos(request):
    """
    Vista pública (sin login) para visualizar horarios/turnos del complejo.
    Importante: NO permite reservar; solo muestra disponibilidad sin datos sensibles.
    """
    complejo = getattr(request, 'complejo_actual', None)
    if not complejo:
        messages.error(request, 'No hay un complejo disponible para mostrar turnos.')
        return redirect('home')

    hoy = timezone.now().date()

    # Limitar rango visible en público (igual que clientes)
    fecha_maxima = hoy + timedelta(days=15)
    fecha_param = (request.GET.get('fecha') or '').strip()
    if fecha_param:
        try:
            fecha_seleccionada = datetime.strptime(fecha_param, '%Y-%m-%d').date()
        except ValueError:
            fecha_seleccionada = hoy
    else:
        fecha_seleccionada = hoy

    if fecha_seleccionada < hoy:
        fecha_seleccionada = hoy
    if fecha_seleccionada > fecha_maxima:
        fecha_seleccionada = fecha_maxima
        messages.info(request, 'Solo podés ver turnos hasta 15 días en el futuro')

    slots_result = TurnoService.generar_slots_disponibles(complejo, fecha_seleccionada)
    slots_por_hora = slots_result['slots_por_hora']
    total_disponibles = slots_result['total_disponibles']

    slots_ordenados = sorted(slots_por_hora.items(), key=lambda x: x[0])

    # Selector rápido: próximos 7 días (desde hoy)
    dias_semana_selector = []
    dias_nombres = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    for i in range(7):
        fecha = hoy + timedelta(days=i)
        if i == 0:
            nombre = 'Hoy'
        elif i == 1:
            nombre = 'Mañana'
        else:
            nombre = dias_nombres[fecha.weekday()]
        dias_semana_selector.append({
            'fecha': fecha,
            'nombre': nombre,
            'activo': fecha == fecha_seleccionada,
        })

    context = {
        'complejo': complejo,
        'hoy': hoy,
        'fecha_seleccionada': fecha_seleccionada,
        'fecha_minima': hoy,
        'fecha_maxima': fecha_maxima,
        'slots_por_hora': dict(slots_ordenados),
        'slots_ordenados': slots_ordenados,
        'total_disponibles': total_disponibles,
        'dias_semana_selector': dias_semana_selector,
    }
    return render(request, 'public/turnos_publicos.html', context)


def terminos_y_condiciones(request):
    """
    Vista de Términos y Condiciones.
    """
    return render(request, 'terminos.html')


def politica_privacidad(request):
    """
    Vista de Políticas de Privacidad.
    """
    return render(request, 'privacidad.html')


@ensure_csrf_cookie
def login_view(request):
    """
    Vista de login con validación multi-tenant.
    
    Permite login con email o username.
    Bloquea el login si el usuario pertenece a un complejo diferente
    al subdominio actual (excepto superadmin que puede acceder a todos).
    """
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username_or_email = request.POST.get('username')
        password = request.POST.get('password')
        
        # Intentar autenticar con username o email
        user = None
        
        # Si contiene @, asumir que es email
        if '@' in username_or_email:
            try:
                usuario_obj = Usuario.objects.get(email__iexact=username_or_email)
                user = authenticate(request, username=usuario_obj.username, password=password)
            except Usuario.DoesNotExist:
                pass
        else:
            # Intentar con username directamente
            user = authenticate(request, username=username_or_email, password=password)
        
        if user is not None:
            # Validación multi-tenant: verificar que el usuario pertenece al complejo actual
            complejo_actual = getattr(request, 'complejo_actual', None)
            
            # Superadmin puede acceder desde cualquier subdominio
            if not user.es_superadmin:
                # Si hay complejo actual y el usuario tiene complejo asignado
                if complejo_actual and user.complejo:
                    if user.complejo.id != complejo_actual.id:
                        messages.error(
                            request, 
                            f'Tu cuenta pertenece a {user.complejo.nombre}. '
                            f'Por favor accedé desde el subdominio correcto.'
                        )
                        return render(request, 'auth/login.html')
            
            login(request, user)
            messages.success(request, f'¡Bienvenido, {user.first_name or user.username}!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos')
    
    return render(request, 'auth/login.html')


@ensure_csrf_cookie
def register_view(request):
    """
    Vista de registro con asignación automática de complejo por subdominio.
    
    Multi-tenant: El usuario se registra automáticamente en el complejo
    del subdominio desde el cual accede.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    # Multi-tenant: usar el complejo del subdominio actual
    complejo_actual = getattr(request, 'complejo_actual', None)
    
    # Fallback si no hay complejo en el request (desarrollo)
    if not complejo_actual:
        try:
            complejo_actual = Complejo.objects.get(slug__iexact='basanta')
        except Complejo.DoesNotExist:
            complejo_actual = Complejo.objects.filter(activo=True).first()
    
    if request.method == 'POST':
        # Campos obligatorios
        email = (request.POST.get('email', '') or '').strip()
        password = request.POST.get('password') or ''
        password_confirm = request.POST.get('password_confirm') or ''
        first_name = (request.POST.get('first_name', '') or '').strip()
        last_name = (request.POST.get('last_name', '') or '').strip()
        
        # Campos opcionales
        celular = (request.POST.get('celular', '') or '').strip()
        dni = (request.POST.get('dni', '') or '').strip()
        
        # Forzar siempre rol de cliente en el registro público
        rol = Usuario.Rol.CLIENTE

        # Validaciones de campos obligatorios
        if not email or not password or not first_name or not last_name:
            messages.error(request, 'Email, nombre, apellido y contraseña son obligatorios')
            return render(request, 'auth/register.html')
        
        # Validar que las contraseñas coincidan
        if password != password_confirm:
            messages.error(request, 'Las contraseñas no coinciden')
            return render(request, 'auth/register.html')
        
        # Validar formato de email
        if '@' not in email or '.' not in email:
            messages.error(request, 'Ingresá un email válido')
            return render(request, 'auth/register.html')
        
        # Verificar si el email ya existe
        if Usuario.objects.filter(email__iexact=email).exists():
            messages.error(request, 'Ese email ya está registrado. Probá iniciar sesión o recuperar tu contraseña.')
            return render(request, 'auth/register.html')
        
        # Generar username único basado en el email
        username = email.split('@')[0].lower()
        base_username = username
        counter = 1
        while Usuario.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        
        try:
            with transaction.atomic():
                # Crear usuario asignado al complejo del subdominio actual
                user = Usuario.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    celular=celular,
                    dni=dni,
                    direccion='',  # Se puede completar después en el perfil
                    rol=rol,
                    complejo=complejo_actual
                )
        except IntegrityError:
            messages.error(request, 'Error al crear la cuenta. El usuario o email ya existe.')
            return render(request, 'auth/register.html')
        except Exception as e:
            messages.error(request, f'Error al crear la cuenta: {str(e)}')
            return render(request, 'auth/register.html')
        
        # Login automático
        login(request, user)
        messages.success(request, f'¡Cuenta creada exitosamente! Bienvenido, {user.first_name or user.username}')
        return redirect('dashboard')
    
    return render(request, 'auth/register.html')


def logout_view(request):
    """Cerrar sesión."""
    logout(request)
    messages.info(request, 'Sesión cerrada correctamente')
    return redirect('home')


@login_required
def dashboard(request):
    """Dashboard según el rol del usuario."""
    user = request.user
    
    # Inicializar variables por defecto para evitar errores en templates
    hoy = timezone.now().date()
    rango_selector_dias = 365
    fecha_minima_default = hoy - timedelta(days=rango_selector_dias)
    fecha_maxima_default = hoy + timedelta(days=rango_selector_dias)
    
    # Layouts compactos para staff/admin (persisten en sesión)
    staff_layout = request.session.get("staff_layout", "classic")
    layout_param = request.GET.get("layout")
    if layout_param in ["classic", "compact"]:
        staff_layout = layout_param
        request.session["staff_layout"] = staff_layout

    context = {
        'user': user,
        'hoy': hoy,
        'fecha_seleccionada': hoy,
        'fecha_minima': fecha_minima_default,
        'fecha_maxima': fecha_maxima_default,
        'es_fecha_pasada': False,
        'staff_layout': staff_layout,
    }
    
    # Si es cliente, calcular turnos disponibles del día
    if user.es_cliente and user.complejo:
        # Obtener fecha desde parámetro GET o usar hoy
        fecha_param = request.GET.get('fecha')
        if fecha_param:
            try:
                fecha_seleccionada = datetime.strptime(fecha_param, '%Y-%m-%d').date()
            except ValueError:
                fecha_seleccionada = timezone.now().date()
        else:
            fecha_seleccionada = timezone.now().date()
        
        hoy = timezone.now().date()
        complejo = user.complejo
        
        # Limitar a máximo 15 días en el futuro para clientes
        fecha_maxima_permitida = hoy + timedelta(days=15)
        if fecha_seleccionada > fecha_maxima_permitida:
            fecha_seleccionada = fecha_maxima_permitida
            messages.info(request, 'Solo podés ver turnos hasta 15 días en el futuro')
        
        # Usar servicio optimizado para generar slots disponibles
        slots_result = TurnoService.generar_slots_disponibles(complejo, fecha_seleccionada)
        slots_por_hora = slots_result['slots_por_hora']
        total_disponibles = slots_result['total_disponibles']
        es_fecha_pasada = slots_result['es_fecha_pasada']
        
        # Convertir a lista ordenada por hora para el template
        slots_ordenados = sorted(slots_por_hora.items(), key=lambda x: x[0])
        
        # Calcular créditos disponibles del cliente (método optimizado del modelo)
        creditos_disponibles = user.get_creditos_disponibles(complejo)
        
        # Obtener turnos del cliente (optimizado con select_related para evitar N+1)
        # Importante: limitamos a últimos 60 días + futuros para que este query no crezca indefinidamente.
        turnos_desde = hoy - timedelta(days=60)
        turnos_cliente = Turno.objects.filter(
            cliente=user,
            cancha__complejo=complejo,
            fecha__gte=turnos_desde,
        ).select_related(
            'cancha',
            'cancha__complejo',
            'cliente'
        ).order_by('fecha', 'hora_inicio')

        # Mis turnos: solo hoy en adelante. Lo ya jugado/pasado va al historial.
        turnos_activos = turnos_cliente.filter(
            fecha__gte=hoy,
            estado__in=[Turno.Estado.CONFIRMADO, Turno.Estado.PENDIENTE_PAGO]
        )
        turnos_historial = turnos_cliente.exclude(
            id__in=turnos_activos.values_list('id', flat=True)
        )
        
        # Turnos del mes actual
        mes_actual = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        turnos_mes = turnos_cliente.filter(fecha__gte=mes_actual).count()
        
        # Calcular fechas para el selector (limitado a 15 días para clientes)
        fecha_minima = hoy  # Clientes no pueden ver fechas pasadas
        fecha_maxima = fecha_maxima_permitida  # Máximo 15 días
        
        context.update({
            'complejo': complejo,
            'hoy': hoy,
            'fecha_seleccionada': fecha_seleccionada,
            'fecha_minima': fecha_minima,
            'fecha_maxima': fecha_maxima,
            'slots_por_hora': dict(slots_ordenados),
            'slots_ordenados': slots_ordenados,
            'total_disponibles': total_disponibles,
            'creditos_disponibles': creditos_disponibles,
            'turnos_cliente': turnos_cliente,
            'turnos_activos': turnos_activos,
            'turnos_historial': turnos_historial,
            'turnos_mes': turnos_mes,
            'es_fecha_pasada': es_fecha_pasada,
        })
    
    # Si es staff, obtener turnos del complejo y calcular disponibles
    if user.es_staff_complejo and user.complejo:
        hoy = timezone.now().date()
        complejo = user.complejo
        orden_turnos = request.GET.get('orden', 'juego')
        
        # Vista de pestaña: "activos" (por defecto) o "historial"
        vista_tab = request.GET.get('vista', 'activos')
        
        # Filtros y paginación
        estado_filtro = request.GET.get('estado')
        cancha_filtro = request.GET.get('cancha')
        cliente_filtro = request.GET.get('cliente', '').strip()
        desde = request.GET.get('desde')
        hasta = request.GET.get('hasta')
        dia_filtro = request.GET.get('dia')  # Filtro por día específico
        page = request.GET.get('page', 1)
        try:
            por_pagina = int(request.GET.get('por_pagina', 50))
        except (TypeError, ValueError):
            por_pagina = 50
        if por_pagina not in [25, 50, 100]:
            por_pagina = 50
        query_params = request.GET.copy()
        if 'page' in query_params:
            query_params.pop('page')
        querystring = query_params.urlencode()
        
        # Query base (sin filtros) para estadísticas (solo activos)
        # Optimizado con select_related para evitar N+1 queries
        turnos_base_qs = Turno.objects.filter(
            cancha__complejo=complejo
        ).exclude(
            estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
        ).select_related('cancha', 'cancha__complejo', 'cliente', 'cliente__complejo')
        
        # Query de listado - depende de la pestaña activa
        # Optimizado con select_related para evitar N+1 queries
        turnos_complejo_qs = Turno.objects.filter(
            cancha__complejo=complejo
        ).select_related('cancha', 'cancha__complejo', 'cliente', 'cliente__complejo')
        
        # Aplicar filtro según la pestaña
        if vista_tab == 'historial':
            # Historial staff:
            # - Turnos del pasado
            # - Y también turnos cancelados/expirados aunque sean futuros (para que "no desaparezcan")
            turnos_complejo_qs = turnos_complejo_qs.filter(
                Q(fecha__lt=hoy) | Q(estado__in=[
                    Turno.Estado.CANCELADO_USUARIO,
                    Turno.Estado.CANCELADO_ADMIN,
                    Turno.Estado.EXPIRADO,
                ])
            )
        else:
            # Mostrar solo turnos activos (fecha de hoy o futura)
            turnos_complejo_qs = turnos_complejo_qs.filter(fecha__gte=hoy)
            # Por defecto excluir cancelados/expirados en vista activa
            if not estado_filtro:
                turnos_complejo_qs = turnos_complejo_qs.exclude(
                    estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
                )
        
        # Estadísticas (queries optimizadas)
        turnos_hoy = turnos_base_qs.filter(fecha=hoy).count()
        pendientes_pago = turnos_base_qs.filter(estado=Turno.Estado.PENDIENTE_PAGO).count()
        confirmados = turnos_base_qs.filter(estado=Turno.Estado.CONFIRMADO).count()
        cancelados = Turno.objects.filter(
            cancha__complejo=complejo,
            estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN]
        ).count()
        
        # Aplicar filtros de estado al listado
        if estado_filtro:
            if estado_filtro == 'cancelados':
                turnos_complejo_qs = turnos_complejo_qs.filter(
                    estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN]
                )
            elif estado_filtro in Turno.Estado.values:
                turnos_complejo_qs = turnos_complejo_qs.filter(estado=estado_filtro)
        
        if cancha_filtro:
            turnos_complejo_qs = turnos_complejo_qs.filter(cancha_id=cancha_filtro)
        
        if cliente_filtro:
            turnos_complejo_qs = turnos_complejo_qs.filter(
                Q(cliente__first_name__icontains=cliente_filtro) |
                Q(cliente__last_name__icontains=cliente_filtro) |
                Q(cliente__username__icontains=cliente_filtro)
            )
        
        # Filtro por día específico (tiene prioridad sobre rango de fechas)
        if dia_filtro:
            try:
                fecha_dia = datetime.strptime(dia_filtro, '%Y-%m-%d').date()
                turnos_complejo_qs = turnos_complejo_qs.filter(fecha=fecha_dia)
            except ValueError:
                pass
        else:
            # Solo aplicar filtros de rango si no hay filtro de día específico
            if desde:
                try:
                    fecha_desde = datetime.strptime(desde, '%Y-%m-%d').date()
                    turnos_complejo_qs = turnos_complejo_qs.filter(fecha__gte=fecha_desde)
                except ValueError:
                    pass
            
            if hasta:
                try:
                    fecha_hasta = datetime.strptime(hasta, '%Y-%m-%d').date()
                    turnos_complejo_qs = turnos_complejo_qs.filter(fecha__lte=fecha_hasta)
                except ValueError:
                    pass
        
        # Ordenar
        if orden_turnos == 'creacion':
            turnos_complejo_qs = turnos_complejo_qs.order_by('-created_at')
        elif orden_turnos == 'hora_desc':
            turnos_complejo_qs = turnos_complejo_qs.order_by('-fecha', '-hora_inicio')
        elif orden_turnos == 'cancha':
            turnos_complejo_qs = turnos_complejo_qs.order_by('cancha__nombre', 'fecha', 'hora_inicio')
        elif orden_turnos == 'cliente':
            turnos_complejo_qs = turnos_complejo_qs.order_by('cliente__first_name', 'cliente__last_name', 'fecha', 'hora_inicio')
        else:
            orden_turnos = 'juego'
            turnos_complejo_qs = turnos_complejo_qs.order_by('fecha', 'hora_inicio')
        
        # Paginar resultados
        paginator = Paginator(turnos_complejo_qs, por_pagina)
        turnos_complejo = paginator.get_page(page)
        
        # Usar servicio optimizado para generar slots disponibles del staff
        slots_por_hora_staff = TurnoService.generar_slots_staff(complejo, hoy)
        slots_ordenados_staff = sorted(slots_por_hora_staff.items(), key=lambda x: x[0])
        
        # Generar lista de próximos 14 días para el selector rápido
        dias_semana_selector = []
        selector_dias_ahead = 7
        for i in range(selector_dias_ahead):
            fecha = hoy + timedelta(days=i)
            dias_nombres = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            if i == 0:
                nombre = 'Hoy'
            elif i == 1:
                nombre = 'Mañana'
            else:
                nombre = dias_nombres[fecha.weekday()]
            
            dias_semana_selector.append({
                'fecha': fecha,
                'nombre': nombre,
                'activo': dia_filtro == fecha.strftime('%Y-%m-%d')
            })
        
        # Limitar rango máximo para el filtro manual de fechas (90 días en el futuro)
        fecha_maxima_rango = hoy + timedelta(days=90)
        context.update({
            'complejo': complejo,
            'hoy': hoy,
            'orden_turnos': orden_turnos,
            'turnos_complejo': turnos_complejo,
            'turnos_hoy': turnos_hoy,
            'pendientes_pago': pendientes_pago,
            'confirmados': confirmados,
            'cancelados': cancelados,
            'slots_ordenados_staff': slots_ordenados_staff,
            'paginator': paginator,
            'canchas': complejo.canchas.filter(activa=True),
            'estado_filtro': estado_filtro or '',
            'cancha_filtro': cancha_filtro or '',
            'cliente_filtro': cliente_filtro,
            'desde': desde or '',
            'hasta': hasta or '',
            'por_pagina': por_pagina,
            'querystring': querystring,
            'vista_tab': vista_tab,
            'dia_filtro': dia_filtro or '',
            'dias_semana_selector': dias_semana_selector,
            'fecha_maxima_rango': fecha_maxima_rango,
        })
    
    # Estado de integración Mercado Pago para admin/staff
    mp_integration = None
    mp_payments = []
    if user.complejo:
        try:
            mp_integration = user.complejo.mercadopago
        except IntegracionMercadoPago.DoesNotExist:
            mp_integration = None
        mp_payments = list(
            PagoMercadoPago.objects.filter(complejo=user.complejo).order_by("-created_at")[:10]
        )
    context.update({
        'mp_integration': mp_integration,
        'mp_oauth_ready': bool(settings.MP_CLIENT_ID and settings.MP_CLIENT_SECRET and settings.MP_REDIRECT_URI),
        'mp_token_expired': mp_integration.is_expired() if mp_integration else False,
        'mp_payments': mp_payments,
    })
    
    # Redirigir según rol
    if user.es_superadmin:
        return render(request, 'dashboard/superadmin.html', context)
    elif user.es_admin:
        return render(request, 'dashboard/admin.html', context)
    elif user.es_staff_complejo:
        staff_template = 'dashboard/staff_compact.html' if staff_layout == 'compact' else 'dashboard/staff.html'
        return render(request, staff_template, context)
    else:
        return render(request, 'dashboard/cliente.html', context)


@login_required
def modal_reservar(request, cancha_id):
    """Modal de confirmación de reserva."""
    if not request.user.es_cliente:
        return JsonResponse({'error': 'No autorizado'}, status=403)
    
    cancha = get_object_or_404(Cancha, id=cancha_id, activa=True)
    fecha = request.GET.get('fecha')
    hora = request.GET.get('hora')
    
    if not fecha or not hora:
        return JsonResponse({'error': 'Fecha y hora requeridas'}, status=400)
    
    try:
        fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
        hora_obj = datetime.strptime(hora, '%H:%M:%S').time()
    except ValueError:
        return JsonResponse({'error': 'Formato de fecha/hora inválido'}, status=400)
    
    # Verificar que el cliente pertenece al mismo complejo
    if request.user.complejo != cancha.complejo:
        return JsonResponse({'error': 'No autorizado'}, status=403)
    
    # Calcular créditos disponibles y desglose de pago de seña
    creditos_disponibles = request.user.get_creditos_disponibles(cancha.complejo)
    senia_requerida = cancha.precio_senia
    creditos_a_usar = min(creditos_disponibles, senia_requerida)
    monto_mp = senia_requerida - creditos_a_usar
    minutos_expiracion_pago = 10
    try:
        minutos_expiracion_pago = int(cancha.complejo.preferencias.minutos_expiracion_pago)
    except Exception:
        minutos_expiracion_pago = 10

    context = {
        'cancha': cancha,
        'fecha': fecha_obj,
        'hora': hora_obj,
        'precio': cancha.precio_hora,
        'senia': senia_requerida,
        'creditos_disponibles': creditos_disponibles,
        'creditos_a_usar': creditos_a_usar,
        'monto_mp': monto_mp,
        'minutos_expiracion_pago': minutos_expiracion_pago,
    }
    
    return render(request, 'modals/confirmar_reserva.html', context)


@login_required
@transaction.atomic
def reservar_turno(request):
    """Procesar la reserva de un turno."""
    if not request.user.es_cliente:
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    if request.method != 'POST':
        messages.error(request, 'Método no permitido')
        return redirect('dashboard')
    
    cancha_id = request.POST.get('cancha_id')
    fecha = request.POST.get('fecha')
    hora = request.POST.get('hora')
    
    if not all([cancha_id, fecha, hora]):
        messages.error(request, 'Faltan datos requeridos')
        return redirect('dashboard')
    
    cancha = get_object_or_404(Cancha, id=cancha_id, activa=True)
    
    # Verificar que el cliente pertenece al mismo complejo
    if request.user.complejo != cancha.complejo:
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    try:
        fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
        hora_obj = datetime.strptime(hora, '%H:%M:%S').time()
    except ValueError:
        messages.error(request, 'Formato de fecha/hora inválido')
        return redirect('dashboard')
    
    # Usar servicio de validación centralizado
    disponible, error_msg = TurnoService.validar_disponibilidad(cancha, fecha_obj, hora_obj)
    if not disponible:
        messages.error(request, error_msg)
        return redirect('dashboard')
    
    # Calcular créditos disponibles (método optimizado del modelo)
    creditos_disponibles = request.user.get_creditos_disponibles(cancha.complejo)
    senia_requerida = cancha.precio_senia
    creditos_a_usar = min(creditos_disponibles, senia_requerida)
    creditos_aplicados = CreditoService.aplicar_creditos(
        request.user,
        cancha.complejo,
        creditos_a_usar
    ) if creditos_a_usar > 0 else Decimal("0.00")
    monto_mp = senia_requerida - creditos_aplicados
    # Calcular expiración si queda saldo por pagar en MP
    minutos_expiracion = 10
    try:
        minutos_expiracion = int(cancha.complejo.preferencias.minutos_expiracion_pago)
    except Exception:
        minutos_expiracion = 10
    expira_en = timezone.now() + timedelta(minutes=minutos_expiracion) if monto_mp > 0 else None
    
    # Crear el turno
    try:
        turno = Turno.objects.create(
            cancha=cancha,
            cliente=request.user,
            fecha=fecha_obj,
            hora_inicio=hora_obj,
            estado=Turno.Estado.PENDIENTE_PAGO,
            precio_total=cancha.precio_hora,
            senia_requerida=senia_requerida,
            senia_pagada=creditos_aplicados,
            creditos_usados=creditos_aplicados,
            expira_en=expira_en,
        )
    except IntegrityError:
        # Otro usuario tomó el turno en paralelo o existe un turno activo igual
        TurnoService.invalidar_cache_slots(cancha.complejo.id, fecha_obj)
        messages.error(request, 'Ese horario acaba de reservarse. Elegí otro turno disponible.')
        return redirect('dashboard')
    
    # Invalidar caché de slots para esta fecha
    TurnoService.invalidar_cache_slots(cancha.complejo.id, fecha_obj)
    
    # Si queda saldo por pagar vía MP, crear preferencia y redirigir al checkout
    if monto_mp > 0:
        try:
            integ = cancha.complejo.mercadopago
        except IntegracionMercadoPago.DoesNotExist:
            transaction.set_rollback(True)
            messages.error(request, 'No hay integración de Mercado Pago configurada para este complejo.')
            return redirect('dashboard')

        if not integ.activo or not integ.access_token_plain:
            transaction.set_rollback(True)
            messages.error(request, 'La integración de Mercado Pago no está activa o falta el token.')
            return redirect('dashboard')

        try:
            checkout_url, preference_id, external_reference = _crear_preferencia_mp_para_turno(
                request=request,
                integration=integ,
                turno=turno,
                monto_mp=monto_mp
            )
        except Exception as exc:
            transaction.set_rollback(True)
            messages.error(request, f'No se pudo iniciar el pago con Mercado Pago: {exc}')
            return redirect('dashboard')

        turno.mp_preference_id = preference_id
        turno.pago_referencia = external_reference
        turno.mp_amount = monto_mp
        turno.mp_status = "pending"
        turno.mp_status_detail = None
        turno.mp_updated_at = timezone.now()
        turno.save(update_fields=[
            'mp_preference_id',
            'pago_referencia',
            'mp_amount',
            'mp_status',
            'mp_status_detail',
            'mp_updated_at',
            'updated_at',
        ])

        messages.info(request, 'Redirigiéndote a Mercado Pago para completar la seña.')
        return redirect(checkout_url)

    messages.success(request, f'¡Turno reservado con seña cubierta por créditos! {cancha.nombre} - {fecha_obj.strftime("%d/%m/%Y")} {hora_obj.strftime("%H:%M")}')

    # Redirigir a la misma fecha para que el cliente pueda seguir viendo turnos disponibles
    return redirect(f'{reverse("dashboard")}?fecha={fecha_obj.strftime("%Y-%m-%d")}')


@login_required
@transaction.atomic
def pagar_senia_turno(request, turno_id):
    """Permite reintentar el pago de la seña pendiente de un turno."""
    if not request.user.es_cliente:
        messages.error(request, 'No autorizado')
        return redirect('dashboard')

    turno = get_object_or_404(
        Turno.objects.select_related('cancha', 'cancha__complejo', 'cliente'),
        id=turno_id,
        cliente=request.user
    )

    if turno.fue_cancelado or turno.estado != Turno.Estado.PENDIENTE_PAGO:
        messages.error(request, 'Este turno no está disponible para pagar la seña.')
        return redirect('turnos_actuales')

    # Verificar expiración
    ahora = timezone.now()
    if turno.expira_en and ahora > turno.expira_en:
        _devolver_creditos_turno(turno, "Expirado por falta de pago")
        turno.estado = Turno.Estado.EXPIRADO
        turno.cancelacion_origen = Turno.CancelacionOrigen.SISTEMA
        turno.cancelacion_motivo = "Expirado por falta de pago"
        turno.cancelado_por = None
        turno.cancelado_en = ahora
        turno.save(update_fields=[
            'estado',
            'cancelacion_origen',
            'cancelacion_motivo',
            'cancelado_por',
            'cancelado_en',
            'updated_at',
        ])
        messages.error(request, 'El turno expiró por falta de pago.')
        return redirect('turnos_actuales')

    saldo = turno.saldo_senia_pendiente
    if saldo <= 0:
        messages.info(request, 'La seña ya está cubierta.')
        return redirect('turnos_actuales')

    # Renovar expiración
    minutos_expiracion = 10
    try:
        minutos_expiracion = int(turno.cancha.complejo.preferencias.minutos_expiracion_pago)
    except Exception:
        minutos_expiracion = 10
    turno.expira_en = timezone.now() + timedelta(minutes=minutos_expiracion)

    try:
        integ = turno.cancha.complejo.mercadopago
    except IntegracionMercadoPago.DoesNotExist:
        transaction.set_rollback(True)
        messages.error(request, 'No hay integración de Mercado Pago configurada para este complejo.')
        return redirect('turnos_actuales')

    if not integ.activo or not integ.access_token_plain:
        transaction.set_rollback(True)
        messages.error(request, 'La integración de Mercado Pago no está activa o falta el token.')
        return redirect('turnos_actuales')

    try:
        checkout_url, preference_id, external_reference = _crear_preferencia_mp_para_turno(
            request=request,
            integration=integ,
            turno=turno,
            monto_mp=saldo
        )
    except Exception as exc:
        transaction.set_rollback(True)
        messages.error(request, f'No se pudo iniciar el pago con Mercado Pago: {exc}')
        return redirect('turnos_actuales')

    turno.mp_preference_id = preference_id
    turno.pago_referencia = external_reference
    turno.mp_amount = saldo
    turno.mp_status = "pending"
    turno.mp_status_detail = None
    turno.mp_updated_at = timezone.now()
    turno.save(update_fields=[
        'mp_preference_id',
        'pago_referencia',
        'mp_amount',
        'mp_status',
        'mp_status_detail',
        'mp_updated_at',
        'expira_en',
        'updated_at',
    ])

    messages.info(request, 'Redirigiéndote a Mercado Pago para completar la seña.')
    return redirect(checkout_url)


@login_required
def cancelar_turno(request, turno_id):
    """Cancelar un turno del cliente."""
    if not request.user.es_cliente:
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    turno = get_object_or_404(
        Turno.objects.select_related('cancha', 'cancha__complejo'), 
        id=turno_id, 
        cliente=request.user
    )
    
    # Verificar que no esté ya cancelado
    if turno.fue_cancelado:
        messages.error(request, 'Este turno ya está cancelado')
        return redirect('dashboard')
    
    # Regla de reembolso: solo si se cancela con la anticipación mínima configurada por el complejo
    horas_minimas = 2
    try:
        horas_minimas = int(turno.cancha.complejo.preferencias.tiempo_minimo_cancelacion)
    except Exception:
        horas_minimas = 2

    ahora = timezone.now()
    inicio_turno = timezone.make_aware(datetime.combine(turno.fecha, turno.hora_inicio))
    elegible_reembolso = ahora <= (inicio_turno - timedelta(hours=horas_minimas))

    # Cancelar el turno
    turno.estado = Turno.Estado.CANCELADO_USUARIO
    turno.cancelacion_origen = Turno.CancelacionOrigen.USUARIO
    turno.cancelacion_motivo = "Cancelación del cliente" if elegible_reembolso else "Cancelación del cliente (fuera de ventana de reembolso)"
    turno.cancelado_por = None
    turno.cancelado_en = ahora
    turno.save(update_fields=['estado', 'cancelacion_origen', 'cancelacion_motivo', 'cancelado_por', 'cancelado_en', 'updated_at'])
    
    # Generar crédito para el cliente (si pagó seña) usando servicio
    # Nota: Cuando el cliente cancela, no hay creado_por (es automático del sistema)
    if elegible_reembolso and turno.senia_pagada > 0:
        CreditoService.generar_credito(
            usuario=request.user,
            complejo=turno.cancha.complejo,
            monto=turno.senia_pagada,
            motivo=f'Cancelación turno {turno.cancha.nombre} - {turno.fecha.strftime("%d/%m/%Y")} {turno.hora_inicio.strftime("%H:%M")}',
            turno_origen=turno,
            creado_por=None,  # Cancelación automática por cliente
        )
    
    # Invalidar caché de slots
    TurnoService.invalidar_cache_slots(turno.cancha.complejo.id, turno.fecha)
    
    if elegible_reembolso and turno.senia_pagada > 0:
        messages.success(request, f'Turno cancelado. Se te acreditó ${turno.senia_pagada} en créditos.')
    else:
        messages.success(
            request,
            f'Turno cancelado. No corresponde reembolso: la cancelación debe hacerse con al menos {horas_minimas}h de anticipación.'
        )
    return redirect('turnos_actuales')


@login_required
def cancelar_turno_staff(request, turno_id):
    """Cancelar un turno (Staff/Admin)."""
    if not (request.user.es_staff_complejo or request.user.es_admin or request.user.es_superadmin):
        messages.error(request, 'No autorizado')
        return redirect('dashboard')

    if request.method != 'POST':
        messages.error(request, 'Método no permitido')
        return redirect('dashboard')
    
    turno = get_object_or_404(Turno.objects.select_related('cancha', 'cancha__complejo', 'cliente'), id=turno_id)
    
    # Verificar que el staff/admin pertenece al mismo complejo (o es superadmin)
    if not request.user.es_superadmin:
        if not request.user.complejo or request.user.complejo != turno.cancha.complejo:
            messages.error(request, 'No podés cancelar turnos de otros complejos')
            return redirect('dashboard')
    
    # Verificar que no esté ya cancelado
    if turno.fue_cancelado:
        messages.error(request, 'Este turno ya está cancelado')
        return redirect('dashboard')

    # Reembolso: staff decide SI/NO explícitamente
    raw_reembolsar = request.POST.get('reembolsar')
    if raw_reembolsar not in ['0', '1']:
        messages.error(request, 'Debés indicar si corresponde reembolso (sí/no).')
        return redirect('dashboard')
    reembolsar = raw_reembolsar == '1'

    motivo = (request.POST.get('motivo') or '').strip()
    if not motivo:
        motivo = "Cancelación por staff"
    if not reembolsar:
        motivo = f"{motivo} (sin reembolso)"
    
    # Cancelar el turno (marcado como cancelado por admin)
    turno.estado = Turno.Estado.CANCELADO_ADMIN
    turno.cancelacion_origen = Turno.CancelacionOrigen.STAFF
    turno.cancelacion_motivo = motivo
    turno.cancelado_por = request.user
    turno.cancelado_en = timezone.now()
    turno.save(update_fields=['estado', 'cancelacion_origen', 'cancelacion_motivo', 'cancelado_por', 'cancelado_en', 'updated_at'])
    
    # Generar crédito para el cliente (si pagó seña) usando servicio
    if reembolsar and turno.senia_pagada > 0:
        CreditoService.generar_credito(
            usuario=turno.cliente,
            complejo=turno.cancha.complejo,
            monto=turno.senia_pagada,
            motivo=f'Cancelación por staff - Turno {turno.cancha.nombre} - {turno.fecha.strftime("%d/%m/%Y")} {turno.hora_inicio.strftime("%H:%M")}',
            turno_origen=turno,
            creado_por=request.user,  # Staff/admin que cancela
        )
    
    # Invalidar caché de slots
    TurnoService.invalidar_cache_slots(turno.cancha.complejo.id, turno.fecha)
    
    if reembolsar and turno.senia_pagada > 0:
        messages.success(request, f'Turno cancelado. Se acreditó ${turno.senia_pagada} en créditos al cliente.')
    else:
        messages.success(request, 'Turno cancelado sin reembolso.')
    return redirect('dashboard')


@login_required
@transaction.atomic
def marcar_turno_pagado(request, turno_id):
    """Marcar un turno como pagado completamente (Staff)."""
    if not (request.user.es_staff_complejo or request.user.es_admin or request.user.es_superadmin):
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    turno = get_object_or_404(
        Turno.objects.select_related('cancha', 'cancha__complejo'), 
        id=turno_id
    )
    
    # Verificar que el staff pertenece al mismo complejo (o es superadmin)
    if not request.user.es_superadmin:
        if not request.user.complejo or request.user.complejo != turno.cancha.complejo:
            messages.error(request, 'No autorizado')
            return redirect('dashboard')
    
    # Verificar que no esté cancelado
    if turno.fue_cancelado:
        messages.error(request, 'No se puede marcar como pagado un turno cancelado')
        return redirect('dashboard')
    
    # Marcar como confirmado (pagado completamente)
    turno.estado = Turno.Estado.CONFIRMADO
    turno.senia_pagada = turno.precio_total  # Marcar como pagado completamente
    turno.save(update_fields=['estado', 'senia_pagada', 'updated_at'])
    
    messages.success(request, f'Turno marcado como pagado: {turno.cancha.nombre} - {turno.fecha.strftime("%d/%m/%Y")} {turno.hora_inicio.strftime("%H:%M")}')
    return redirect('dashboard')


@login_required
def editar_turno(request, turno_id):
    """Vista para editar un turno (Staff)."""
    if not (request.user.es_staff_complejo or request.user.es_admin or request.user.es_superadmin):
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    turno = get_object_or_404(
        Turno.objects.select_related('cancha', 'cancha__complejo', 'cliente'), 
        id=turno_id
    )
    
    # Bloquear edición si el turno ya empezó (para no “romper” el turno).
    # En ese caso, el staff solo puede marcar como pagado o cancelar.
    if turno.estado == Turno.Estado.JUGADO or turno.ya_empezo:
        messages.error(request, 'Este turno ya empezó. Solo podés marcarlo como pagado o cancelarlo.')
        return redirect('dashboard')
    
    # Verificar que el staff pertenece al mismo complejo (o es superadmin)
    if not request.user.es_superadmin:
        if not request.user.complejo or request.user.complejo != turno.cancha.complejo:
            messages.error(request, 'No autorizado')
            return redirect('dashboard')
    
    # Obtener canchas del complejo
    complejo = turno.cancha.complejo
    canchas = Cancha.objects.filter(complejo=complejo, activa=True)
    
    context = {
        'turno': turno,
        'canchas': canchas,
        'complejo': complejo,
    }
    
    return render(request, 'staff/editar_turno.html', context)


@login_required
@transaction.atomic
def actualizar_turno(request, turno_id):
    """Actualizar un turno (Staff)."""
    if not (request.user.es_staff_complejo or request.user.es_admin or request.user.es_superadmin):
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    if request.method != 'POST':
        messages.error(request, 'Método no permitido')
        return redirect('dashboard')
    
    turno = get_object_or_404(
        Turno.objects.select_related('cancha', 'cancha__complejo'), 
        id=turno_id
    )
    
    # Bloquear edición si el turno ya empezó (para no “romper” el turno).
    # En ese caso, el staff solo puede marcar como pagado o cancelar.
    if turno.estado == Turno.Estado.JUGADO or turno.ya_empezo:
        messages.error(request, 'Este turno ya empezó. Solo podés marcarlo como pagado o cancelarlo.')
        return redirect('dashboard')
    
    # Verificar que el staff pertenece al mismo complejo (o es superadmin)
    if not request.user.es_superadmin:
        if not request.user.complejo or request.user.complejo != turno.cancha.complejo:
            messages.error(request, 'No autorizado')
            return redirect('dashboard')
    
    # Obtener datos del formulario
    cancha_id = request.POST.get('cancha_id')
    fecha = request.POST.get('fecha')
    hora_inicio = request.POST.get('hora_inicio')
    nuevo_estado = request.POST.get('estado')
    
    if not all([cancha_id, fecha, hora_inicio, nuevo_estado]):
        messages.error(request, 'Faltan datos requeridos')
        return redirect('editar_turno', turno_id=turno.id)
    
    estados_permitidos = [
        Turno.Estado.PENDIENTE_PAGO,
        Turno.Estado.CONFIRMADO,
        Turno.Estado.BLOQUEADO,
        Turno.Estado.CANCELADO_ADMIN,
    ]
    if nuevo_estado not in estados_permitidos:
        messages.error(request, 'Estado inválido')
        return redirect('editar_turno', turno_id=turno.id)
    
    try:
        cancha = Cancha.objects.get(id=cancha_id, activa=True, complejo=turno.cancha.complejo)
        fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
        hora_obj = datetime.strptime(hora_inicio, '%H:%M').time()
    except (ValueError, Cancha.DoesNotExist):
        messages.error(request, 'Datos inválidos')
        return redirect('editar_turno', turno_id=turno.id)
    
    # Guardar fecha original para invalidar caché
    fecha_original = turno.fecha
    
    # Verificar que el turno no esté ocupado (excepto el mismo turno)
    turno_existente = Turno.objects.filter(
        cancha=cancha,
        fecha=fecha_obj,
        hora_inicio=hora_obj
    ).exclude(
        id=turno.id
    ).exclude(
        estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
    ).exists()
    
    if turno_existente:
        messages.error(request, 'Este turno ya está reservado')
        return redirect('editar_turno', turno_id=turno.id)
    
    # Actualizar el turno
    estado_anterior = turno.estado
    turno.cancha = cancha
    turno.fecha = fecha_obj
    turno.hora_inicio = hora_obj
    turno.estado = nuevo_estado
    # Si se está marcando como cancelado por admin desde el editor, registrar origen/motivo.
    # Si se “reabre” (se cambia a otro estado), limpiar datos de cancelación para evitar confusiones.
    if nuevo_estado == Turno.Estado.CANCELADO_ADMIN:
        turno.cancelacion_origen = Turno.CancelacionOrigen.STAFF
        turno.cancelacion_motivo = turno.cancelacion_motivo or "Cancelación por staff"
        turno.cancelado_por = request.user
        turno.cancelado_en = timezone.now()
    else:
        # Si se reabre un turno que estaba cancelado/expirado, limpiar datos de cancelación.
        if estado_anterior in [Turno.Estado.CANCELADO_ADMIN, Turno.Estado.CANCELADO_USUARIO, Turno.Estado.EXPIRADO]:
            turno.cancelacion_origen = None
            turno.cancelacion_motivo = None
            turno.cancelado_por = None
            turno.cancelado_en = None
    turno.save()
    
    # Invalidar caché de slots para ambas fechas si cambió
    TurnoService.invalidar_cache_slots(cancha.complejo.id, fecha_obj)
    if fecha_original != fecha_obj:
        TurnoService.invalidar_cache_slots(cancha.complejo.id, fecha_original)
    
    messages.success(request, f'Turno actualizado: {cancha.nombre} - {fecha_obj.strftime("%d/%m/%Y")} {hora_obj.strftime("%H:%M")}')
    return redirect('dashboard')


@login_required
def nuevo_turno_rapido(request):
    """Vista para crear un turno rápido (Staff)."""
    if not (request.user.es_staff_complejo or request.user.es_admin or request.user.es_superadmin):
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    if not request.user.complejo:
        messages.error(request, 'No tenés un complejo asignado')
        return redirect('dashboard')
    
    complejo = request.user.complejo
    hoy = timezone.now().date()
    
    # Permitir seleccionar fecha por parámetro
    fecha_param = request.GET.get('fecha')
    if fecha_param:
        try:
            fecha_base = datetime.strptime(fecha_param, '%Y-%m-%d').date()
        except ValueError:
            fecha_base = hoy
    else:
        fecha_base = hoy
    
    # No permitir fechas pasadas
    if fecha_base < hoy:
        messages.error(request, 'No se pueden crear turnos en el pasado')
        return redirect(f"{request.path}?fecha={hoy.strftime('%Y-%m-%d')}")
    
    # Usar el servicio optimizado para generar slots disponibles
    slots_por_hora_staff = TurnoService.generar_slots_staff(complejo, fecha_base)
    slots_ordenados = sorted(slots_por_hora_staff.items(), key=lambda x: x[0])
    
    # Calcular fechas para navegación
    fecha_anterior = fecha_base - timedelta(days=1)
    fecha_siguiente = fecha_base + timedelta(days=1)
    
    context = {
        'complejo': complejo,
        'hoy': hoy,
        'fecha_seleccionada': fecha_base,
        'fecha_anterior': fecha_anterior,
        'fecha_siguiente': fecha_siguiente,
        'slots_ordenados': slots_ordenados,
    }
    
    return render(request, 'staff/nuevo_turno_rapido.html', context)


@login_required
@transaction.atomic
def crear_turno_rapido(request):
    """Procesar la creación de un turno rápido."""
    if not (request.user.es_staff_complejo or request.user.es_admin or request.user.es_superadmin):
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    if request.method != 'POST':
        messages.error(request, 'Método no permitido')
        return redirect('dashboard')
    
    cancha_id = request.POST.get('cancha_id')
    fecha = request.POST.get('fecha')
    hora = request.POST.get('hora')
    nombre_cliente = request.POST.get('nombre_cliente', '').strip()
    celular_cliente = request.POST.get('celular_cliente', '').strip()
    
    if not all([cancha_id, fecha, hora, nombre_cliente, celular_cliente]):
        messages.error(request, 'Faltan datos requeridos')
        return redirect('nuevo_turno_rapido')
    
    cancha = get_object_or_404(Cancha, id=cancha_id, activa=True)
    
    # Verificar que el staff pertenece al mismo complejo
    if not request.user.es_superadmin:
        if not request.user.complejo or request.user.complejo != cancha.complejo:
            messages.error(request, 'No autorizado')
            return redirect('dashboard')
    
    try:
        fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
        hora_obj = datetime.strptime(hora, '%H:%M:%S').time()
    except ValueError:
        messages.error(request, 'Formato de fecha/hora inválido')
        return redirect('nuevo_turno_rapido')
    
    # Verificar que el turno no sea en el pasado
    # timezone.now() ya usa el timezone configurado en settings (America/Argentina/Buenos_Aires)
    ahora = timezone.now()
    # make_aware usa el timezone activo de Django (configurado en TIME_ZONE)
    fecha_hora_turno = timezone.make_aware(datetime.combine(fecha_obj, hora_obj))
    if fecha_hora_turno < ahora:
        messages.error(request, 'No se puede reservar un turno en el pasado')
        return redirect('nuevo_turno_rapido')
    
    # Verificar si ya existe un turno en ese horario (incluye cancelados/expirados)
    turno_existente = Turno.objects.filter(
        cancha=cancha,
        fecha=fecha_obj,
        hora_inicio=hora_obj
    ).first()
    
    if turno_existente:
        if turno_existente.estado in [Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]:
            # Reabrir turno cancelado/expirado para evitar error de unique
            turno = turno_existente
            turno.cliente = turno_existente.cliente if turno_existente.cliente else request.user
            turno.cancha = cancha
            turno.fecha = fecha_obj
            turno.hora_inicio = hora_obj
            turno.estado = Turno.Estado.PENDIENTE_PAGO
            turno.precio_total = cancha.precio_hora
            turno.senia_requerida = cancha.precio_senia
            turno.senia_pagada = Decimal('0.00')
            turno.creditos_usados = Decimal('0.00')
            turno.notas = f'Turno reabierto por staff: {request.user.username}'
            turno.save()
            # Invalidar cache de slots
            TurnoService.invalidar_cache_slots(cancha.complejo.id, fecha_obj)
            messages.success(request, f'Turno reactivado: {cancha.nombre} - {fecha_obj.strftime("%d/%m/%Y")} {hora_obj.strftime("%H:%M")}')
            return redirect('dashboard')
        else:
            messages.error(request, 'Este turno ya está reservado')
            return redirect('nuevo_turno_rapido')
    
    # Buscar o crear cliente por nombre
    # Si no existe, crear un usuario cliente temporal
    cliente, created = Usuario.objects.get_or_create(
        username=f"cliente_{nombre_cliente.lower().replace(' ', '_')}_{fecha_obj}",
        defaults={
            'first_name': nombre_cliente,
            'rol': Usuario.Rol.CLIENTE,
            'complejo': cancha.complejo,
            'celular': celular_cliente,
        }
    )
    
    if not created:
        # Si ya existe, actualizar el nombre por si cambió
        cliente.first_name = nombre_cliente
        cliente.complejo = cancha.complejo
        if celular_cliente:
            cliente.celular = celular_cliente
        cliente.save()
    
    # Crear el turno como PENDIENTE_PAGO
    turno = Turno.objects.create(
        cancha=cancha,
        cliente=cliente,
        fecha=fecha_obj,
        hora_inicio=hora_obj,
        estado=Turno.Estado.PENDIENTE_PAGO,
        precio_total=cancha.precio_hora,
        senia_requerida=cancha.precio_senia,
        senia_pagada=Decimal('0.00'),
        creditos_usados=Decimal('0.00'),
        notas=f'Turno creado por staff: {request.user.username}',
    )
    
    messages.success(request, f'Turno creado para {nombre_cliente} - {cancha.nombre} - {fecha_obj.strftime("%d/%m/%Y")} {hora_obj.strftime("%H:%M")}')
    return redirect('dashboard')


@login_required
def bloqueos(request):
    """Vista para listar y crear bloqueos (Staff/Admin/Superadmin)."""
    if not (request.user.es_staff_complejo or request.user.es_admin or request.user.es_superadmin):
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    if not request.user.complejo and not request.user.es_superadmin:
        messages.error(request, 'No tenés un complejo asignado')
        return redirect('dashboard')
    
    complejo = request.user.complejo if not request.user.es_superadmin else request.user.complejo
    canchas = Cancha.objects.filter(complejo=complejo, activa=True) if complejo else Cancha.objects.none()
    bloqueos = Bloqueo.objects.filter(complejo=complejo).select_related('cancha').order_by('-fecha', '-created_at')
    
    context = {
        'complejo': complejo,
        'canchas': canchas,
        'bloqueos': bloqueos,
        'hoy': timezone.now().date(),
    }
    return render(request, 'staff/bloqueos.html', context)


@login_required
@transaction.atomic
def crear_bloqueo(request):
    """Crear un bloqueo de turnos/canchas y cancelar turnos afectados con reembolso en créditos."""
    if request.method != 'POST':
        return redirect('bloqueos')
    
    if not (request.user.es_staff_complejo or request.user.es_admin or request.user.es_superadmin):
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    if not request.user.complejo and not request.user.es_superadmin:
        messages.error(request, 'No tenés un complejo asignado')
        return redirect('dashboard')
    
    complejo = request.user.complejo
    fecha_str = request.POST.get('fecha')
    cancha_id = request.POST.get('cancha_id') or None
    dia_completo = request.POST.get('dia_completo') == 'on'
    hora_inicio_str = request.POST.get('hora_inicio') or ''
    hora_fin_str = request.POST.get('hora_fin') or ''
    motivo = request.POST.get('motivo', '').strip() or 'Bloqueo por staff'
    
    # Validaciones básicas
    if not fecha_str:
        messages.error(request, 'La fecha es obligatoria')
        return redirect('bloqueos')
    
    try:
        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, 'Formato de fecha inválido')
        return redirect('bloqueos')
    
    hora_inicio = None
    hora_fin = None
    if not dia_completo:
        if not hora_inicio_str:
            messages.error(request, 'La hora de inicio es obligatoria para un bloqueo parcial')
            return redirect('bloqueos')
        try:
            hora_inicio = datetime.strptime(hora_inicio_str, '%H:%M').time()
            if hora_fin_str:
                hora_fin = datetime.strptime(hora_fin_str, '%H:%M').time()
        except ValueError:
            messages.error(request, 'Formato de hora inválido')
            return redirect('bloqueos')
    
    cancha = None
    if cancha_id:
        cancha = get_object_or_404(Cancha, id=cancha_id, complejo=complejo, activa=True)
    
    # Crear bloqueo
    bloqueo = Bloqueo.objects.create(
        complejo=complejo,
        cancha=cancha,
        fecha=fecha_obj,
        hora_inicio=None if dia_completo else hora_inicio,
        hora_fin=None if dia_completo else hora_fin,
        motivo=motivo,
        created_by=request.user,
    )
    
    # Cancelar turnos afectados (autoridad máxima)
    # Optimizado con select_related para evitar N+1 queries
    turnos_qs = Turno.objects.filter(
        cancha__complejo=complejo,
        fecha=fecha_obj
    ).select_related('cliente', 'cliente__complejo', 'cancha', 'cancha__complejo')
    if cancha:
        turnos_qs = turnos_qs.filter(cancha=cancha)
    if not dia_completo and hora_inicio:
        if hora_fin:
            turnos_qs = turnos_qs.filter(hora_inicio__gte=hora_inicio, hora_inicio__lt=hora_fin)
        else:
            turnos_qs = turnos_qs.filter(hora_inicio=hora_inicio)
    
    turnos_cancelados = 0
    for turno in turnos_qs:
        if turno.fue_cancelado:
            continue
        turno.estado = Turno.Estado.CANCELADO_ADMIN
        turno.cancelacion_origen = Turno.CancelacionOrigen.BLOQUEO
        # Requisito: que en el historial staff figure con el motivo exacto:
        # "Cancelado por bloqueo"
        turno.cancelacion_motivo = "Cancelado por bloqueo"
        turno.cancelado_por = request.user
        turno.cancelado_en = timezone.now()
        turno.save(update_fields=['estado', 'cancelacion_origen', 'cancelacion_motivo', 'cancelado_por', 'cancelado_en', 'updated_at'])
        turnos_cancelados += 1
        
        if turno.senia_pagada > 0:
            CreditoService.generar_credito(
                usuario=turno.cliente,
                complejo=turno.cancha.complejo,
                monto=turno.senia_pagada,
                motivo=f'Bloqueo: {turno.cancha.nombre} {turno.fecha.strftime("%d/%m/%Y")} {turno.hora_inicio.strftime("%H:%M")}',
                turno_origen=turno,
                creado_por=request.user,  # Staff/admin que crea el bloqueo
            )
    
    # Invalidar cache de slots del día bloqueado
    TurnoService.invalidar_cache_slots(complejo.id, fecha_obj)
    
    mensajes = [f'Bloqueo creado para el {fecha_obj.strftime("%d/%m/%Y")}']
    if cancha:
        mensajes.append(f'Cancha: {cancha.nombre}')
    mensajes.append('Día completo' if dia_completo else 'Bloqueo parcial')
    if turnos_cancelados:
        mensajes.append(f'Turnos afectados: {turnos_cancelados}')
    messages.success(request, ' • '.join(mensajes))
    
    return redirect('bloqueos')


@login_required
@transaction.atomic
def eliminar_bloqueo(request, bloqueo_id):
    """Eliminar un bloqueo de turnos/canchas."""
    if not (request.user.es_staff_complejo or request.user.es_admin or request.user.es_superadmin):
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    bloqueo = get_object_or_404(
        Bloqueo.objects.select_related('complejo', 'cancha'),
        id=bloqueo_id
    )
    
    # Verificar que el staff pertenece al mismo complejo (o es superadmin)
    if not request.user.es_superadmin:
        if not request.user.complejo or request.user.complejo != bloqueo.complejo:
            messages.error(request, 'No autorizado')
            return redirect('dashboard')
    
    # Guardar información antes de eliminar (necesario para cache y mensaje)
    complejo_id = bloqueo.complejo.id
    fecha = bloqueo.fecha
    fecha_str = bloqueo.fecha.strftime("%d/%m/%Y")
    cancha_nombre = bloqueo.cancha.nombre if bloqueo.cancha else "Todas las canchas"
    
    # Eliminar el bloqueo
    bloqueo.delete()
    
    # Invalidar cache de slots del día bloqueado
    TurnoService.invalidar_cache_slots(complejo_id, fecha)
    
    messages.success(request, f'Bloqueo eliminado: {cancha_nombre} - {fecha_str}')
    return redirect('bloqueos')


@login_required
def turnos_fijos(request):
    """Vista para listar y gestionar turnos fijos (Staff)."""
    if not (request.user.es_staff_complejo or request.user.es_admin or request.user.es_superadmin):
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    if not request.user.complejo:
        messages.error(request, 'No tenés un complejo asignado')
        return redirect('dashboard')
    
    complejo = request.user.complejo
    
    # Obtener todas las canchas del complejo
    canchas = Cancha.objects.filter(complejo=complejo, activa=True)
    
    # Obtener todos los turnos fijos activos del complejo
    turnos_fijos = TurnoFijo.objects.filter(
        cancha__complejo=complejo,
        activo=True
    ).select_related('cancha', 'cliente').order_by('dia_semana', 'hora_inicio')
    
    # Agrupar por día de la semana para mejor visualización
    turnos_por_dia = {}
    for turno in turnos_fijos:
        dia = turno.get_dia_semana_display()
        if dia not in turnos_por_dia:
            turnos_por_dia[dia] = []
        turnos_por_dia[dia].append(turno)
    
    context = {
        'complejo': complejo,
        'canchas': canchas,
        'turnos_fijos': turnos_fijos,
        'turnos_por_dia': turnos_por_dia,
        'dias_semana': TurnoFijo.DiaSemana.choices,
    }
    
    return render(request, 'staff/turnos_fijos.html', context)


@login_required
@transaction.atomic
def crear_turno_fijo(request):
    """Crear uno o más turnos fijos (Staff)."""
    if not (request.user.es_staff_complejo or request.user.es_admin or request.user.es_superadmin):
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    if request.method != 'POST':
        messages.error(request, 'Método no permitido')
        return redirect('turnos_fijos')
    
    if not request.user.complejo:
        messages.error(request, 'No tenés un complejo asignado')
        return redirect('dashboard')
    
    complejo = request.user.complejo
    
    # Obtener datos del formulario
    cancha_id = request.POST.get('cancha_id')
    nombre_cliente = request.POST.get('nombre_cliente', '').strip()
    celular_cliente = request.POST.get('celular_cliente', '').strip()
    hora_inicio = request.POST.get('hora_inicio')
    dias_semana = request.POST.getlist('dias_semana')  # Múltiples días
    fecha_inicio = request.POST.get('fecha_inicio')
    fecha_fin = request.POST.get('fecha_fin', '').strip() or None
    notas = request.POST.get('notas', '').strip()
    
    # Validaciones
    if not all([cancha_id, nombre_cliente, celular_cliente, hora_inicio, dias_semana, fecha_inicio]):
        messages.error(request, 'Faltan datos requeridos')
        return redirect('turnos_fijos')
    
    cancha = get_object_or_404(Cancha, id=cancha_id, activa=True, complejo=complejo)
    
    # Verificar que el staff pertenece al mismo complejo
    if not request.user.es_superadmin:
        if request.user.complejo != cancha.complejo:
            messages.error(request, 'No autorizado')
            return redirect('dashboard')
    
    try:
        hora_obj = datetime.strptime(hora_inicio, '%H:%M').time()
        fecha_inicio_obj = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
        fecha_fin_obj = None
        if fecha_fin:
            fecha_fin_obj = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
            if fecha_fin_obj < fecha_inicio_obj:
                messages.error(request, 'La fecha de fin debe ser posterior a la fecha de inicio')
                return redirect('turnos_fijos')
    except ValueError:
        messages.error(request, 'Formato de fecha/hora inválido')
        return redirect('turnos_fijos')
    
    # Verificar si se forzó la creación (ignorar conflictos)
    forzar_creacion = request.POST.get('forzar_creacion') == 'true'
    
    # Buscar o crear cliente por nombre
    cliente, created = Usuario.objects.get_or_create(
        username=f"cliente_{nombre_cliente.lower().replace(' ', '_')}_{complejo.id}",
        defaults={
            'first_name': nombre_cliente,
            'rol': Usuario.Rol.CLIENTE,
            'complejo': complejo,
            'celular': celular_cliente,
        }
    )
    
    if not created:
        cliente.first_name = nombre_cliente
        cliente.complejo = complejo
        if celular_cliente:
            cliente.celular = celular_cliente
        cliente.save()
    
    # Detectar conflictos con turnos existentes
    if not forzar_creacion:
        conflictos_encontrados = []
        fecha_fin_limite = fecha_fin_obj or (fecha_inicio_obj + timedelta(days=365))
        
        # Iterar por cada día seleccionado
        for dia_str in dias_semana:
            try:
                dia_semana = int(dia_str)
                dia_nombre = TurnoFijo.DiaSemana(dia_semana).label
                
                # Buscar todas las fechas que coinciden con este día de la semana en el rango
                fecha_actual = fecha_inicio_obj
                turnos_conflictivos = []
                
                while fecha_actual <= fecha_fin_limite:
                    if fecha_actual.weekday() == dia_semana:
                        # Verificar si existe un turno en esta fecha/hora/cancha
                        turno_existente = Turno.objects.filter(
                            cancha=cancha,
                            fecha=fecha_actual,
                            hora_inicio=hora_obj
                        ).exclude(
                            estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
                        ).first()
                        
                        if turno_existente:
                            turnos_conflictivos.append({
                                'fecha': fecha_actual.strftime('%Y-%m-%d'),
                                'fecha_display': fecha_actual.strftime('%d/%m/%Y'),
                                'cliente': turno_existente.cliente.get_full_name() or turno_existente.cliente.username,
                            })
                    
                    fecha_actual += timedelta(days=1)
                
                if turnos_conflictivos:
                    conflictos_encontrados.append({
                        'dia': dia_nombre,
                        'turnos': turnos_conflictivos
                    })
            except (ValueError, KeyError):
                continue
        
        # Si hay conflictos, guardar en sesión y redirigir a confirmación
        if conflictos_encontrados:
            request.session['turno_fijo_pendiente'] = {
                'cancha_id': cancha_id,
                'nombre_cliente': nombre_cliente,
                'celular_cliente': celular_cliente,
                'hora_inicio': hora_inicio,
                'dias_semana': dias_semana,
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
                'notas': notas,
                'conflictos': conflictos_encontrados,
            }
            return redirect('confirmar_turno_fijo')
    
    # Si no hay conflictos o se forzó, crear los turnos fijos
    turnos_creados = []
    turnos_duplicados = []
    
    for dia_str in dias_semana:
        try:
            dia_semana = int(dia_str)
            
            # Verificar si ya existe un turno fijo activo para esta cancha, día y hora
            turno_existente = TurnoFijo.objects.filter(
                cancha=cancha,
                dia_semana=dia_semana,
                hora_inicio=hora_obj,
                activo=True
            ).first()
            
            if turno_existente:
                turnos_duplicados.append(TurnoFijo.DiaSemana(dia_semana).label)
                continue
            
            # Crear el turno fijo
            turno_fijo = TurnoFijo.objects.create(
                cancha=cancha,
                cliente=cliente,
                dia_semana=dia_semana,
                hora_inicio=hora_obj,
                fecha_inicio=fecha_inicio_obj,
                fecha_fin=fecha_fin_obj,
                activo=True,
                notas=notas or f'Turno fijo creado por staff: {request.user.username}',
            )
            turnos_creados.append(turno_fijo)
        except (ValueError, KeyError):
            continue
    
    # Limpiar datos de sesión si existen
    if 'turno_fijo_pendiente' in request.session:
        del request.session['turno_fijo_pendiente']
    
    # Generar turnos reales automáticamente para los turnos fijos creados
    turnos_generados = 0
    if turnos_creados:
        hoy = timezone.now().date()
        fecha_hasta = hoy + timedelta(days=60)  # Generar para los próximos 60 días
        
        # Generar turnos para cada turno fijo creado
        for turno_fijo in turnos_creados:
            fecha_actual = max(turno_fijo.fecha_inicio, hoy)
            fecha_fin_limite = turno_fijo.fecha_fin or fecha_hasta
            fecha_fin_limite = min(fecha_fin_limite, fecha_hasta)
            
            while fecha_actual <= fecha_fin_limite:
                # Verificar si esta fecha coincide con el día de la semana del turno fijo
                if fecha_actual.weekday() == turno_fijo.dia_semana:
                    # Verificar si ya existe un turno en esta fecha/hora/cancha
                    turno_existente = Turno.objects.filter(
                        cancha=turno_fijo.cancha,
                        fecha=fecha_actual,
                        hora_inicio=turno_fijo.hora_inicio
                    ).first()
                    
                    if not turno_existente:
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
                            turnos_generados += 1
                            # Invalidar caché para esta fecha
                            TurnoService.invalidar_cache_slots(complejo.id, fecha_actual)
                        except IntegrityError:
                            pass  # Si hay conflicto, continuar
                
                fecha_actual += timedelta(days=1)
    
    # Mensajes de resultado
    if turnos_creados:
        dias_creados = [t.get_dia_semana_display() for t in turnos_creados]
        mensaje = f'Turnos fijos creados para {nombre_cliente} - {cancha.nombre} - {", ".join(dias_creados)} a las {hora_obj.strftime("%H:%M")}'
        if turnos_generados > 0:
            mensaje += f' ({turnos_generados} turnos generados automáticamente)'
        messages.success(request, mensaje)
    
    if turnos_duplicados:
        messages.warning(request, f'Turnos fijos ya existentes para: {", ".join(turnos_duplicados)}')
    
    if not turnos_creados and not turnos_duplicados:
        messages.error(request, 'No se pudo crear ningún turno fijo')
    
    return redirect('turnos_fijos')


@login_required
def confirmar_turno_fijo(request):
    """Mostrar confirmación de turno fijo con conflictos."""
    if not (request.user.es_staff_complejo or request.user.es_admin or request.user.es_superadmin):
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    if not request.user.complejo:
        messages.error(request, 'No tenés un complejo asignado')
        return redirect('dashboard')
    
    # Obtener datos de la sesión
    turno_pendiente = request.session.get('turno_fijo_pendiente')
    if not turno_pendiente:
        messages.error(request, 'No hay turno fijo pendiente')
        return redirect('turnos_fijos')
    
    # Obtener la cancha
    cancha = get_object_or_404(
        Cancha, 
        id=turno_pendiente['cancha_id'], 
        complejo=request.user.complejo
    )
    
    context = {
        'complejo': request.user.complejo,
        'turno_pendiente': turno_pendiente,
        'cancha': cancha,
    }
    
    return render(request, 'staff/confirmar_turno_fijo.html', context)


@login_required
@transaction.atomic
def generar_turnos_desde_fijos(request):
    """Generar turnos normales a partir de los turnos fijos (Staff)."""
    if not (request.user.es_staff_complejo or request.user.es_admin or request.user.es_superadmin):
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    if not request.user.complejo:
        messages.error(request, 'No tenés un complejo asignado')
        return redirect('dashboard')
    
    complejo = request.user.complejo
    
    # Generar turnos para los próximos 60 días
    hoy = timezone.now().date()
    fecha_hasta = hoy + timedelta(days=60)
    
    turnos_creados, turnos_ya_existentes = TurnoService.generar_turnos_desde_fijos(
        complejo=complejo,
        fecha_desde=hoy,
        fecha_hasta=fecha_hasta
    )
    
    if turnos_creados > 0:
        messages.success(request, f'Se crearon {turnos_creados} turnos desde los turnos fijos ({turnos_ya_existentes} ya existían)')
    else:
        messages.info(request, f'No se crearon turnos nuevos ({turnos_ya_existentes} ya existían)')
    
    return redirect('dashboard')


@login_required
@transaction.atomic
def eliminar_turno_fijo(request, turno_fijo_id):
    """Eliminar o desactivar un turno fijo (Staff)."""
    if not (request.user.es_staff_complejo or request.user.es_admin or request.user.es_superadmin):
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    turno_fijo = get_object_or_404(
        TurnoFijo.objects.select_related('cancha', 'cancha__complejo'), 
        id=turno_fijo_id
    )
    
    # Verificar que el staff pertenece al mismo complejo
    if not request.user.es_superadmin:
        if not request.user.complejo or request.user.complejo != turno_fijo.cancha.complejo:
            messages.error(request, 'No autorizado')
            return redirect('dashboard')
    
    # Desactivar en lugar de eliminar (para mantener historial)
    turno_fijo.activo = False
    turno_fijo.save(update_fields=['activo', 'updated_at'])
    
    messages.success(request, f'Turno fijo eliminado: {turno_fijo.get_dia_semana_display()} {turno_fijo.hora_inicio.strftime("%H:%M")} - {turno_fijo.cancha.nombre}')
    return redirect('turnos_fijos')


@login_required
@transaction.atomic
def actualizar_perfil(request):
    """Actualizar perfil del cliente."""
    if not request.user.es_cliente:
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    if request.method != 'POST':
        messages.error(request, 'Método no permitido')
        return redirect('mi_perfil')
    
    user = request.user
    
    # Obtener datos del formulario (solo campos editables)
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    dni = request.POST.get('dni', '').strip()
    celular = request.POST.get('celular', '').strip()
    direccion = request.POST.get('direccion', '').strip()
    
    # Actualizar solo campos permitidos
    user.first_name = first_name
    user.last_name = last_name
    user.dni = dni if dni else None
    user.celular = celular if celular else None
    user.direccion = direccion
    user.save()
    
    messages.success(request, f'Perfil actualizado correctamente')
    return redirect('mi_perfil')


@login_required
@transaction.atomic
def darse_de_baja(request):
    """
    Eliminar la cuenta del cliente y todo lo asociado.
    Acción delicada: solo por POST y con confirmación explícita.
    """
    if not request.user.es_cliente:
        messages.error(request, 'No autorizado')
        return redirect('dashboard')

    if request.method != 'POST':
        messages.error(request, 'Método no permitido')
        return redirect('mi_perfil')

    if request.POST.get('confirmar') != '1':
        messages.error(request, 'Confirmación requerida para darse de baja')
        return redirect('mi_perfil')

    user = request.user
    username = user.username

    # 1) Eliminar (borrado en cascada de objetos relacionados)
    try:
        user.delete()
    except Exception as exc:
        messages.error(request, f'No se pudo eliminar la cuenta: {type(exc).__name__}: {exc}')
        return redirect('mi_perfil')

    # 2) Cerrar sesión y mostrar feedback (en nueva sesión)
    logout(request)
    messages.success(request, f'Tu cuenta ({username}) fue eliminada correctamente.')
    return redirect('home')


@login_required
def turnos_actuales(request):
    """Vista de turnos actuales del cliente."""
    if not request.user.es_cliente:
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    if not request.user.complejo:
        messages.error(request, 'No tenés un complejo asignado')
        return redirect('dashboard')
    
    complejo = request.user.complejo
    hoy = timezone.now().date()
    
    # Obtener turnos activos (no cancelados, no expirados)
    # Optimizado con select_related para evitar N+1 queries
    turnos_activos = Turno.objects.filter(
        cliente=request.user,
        cancha__complejo=complejo,
        fecha__gte=hoy,  # Solo hoy y futuro; lo pasado se ve en historial
    ).exclude(
        estado__in=[
            Turno.Estado.CANCELADO_USUARIO,
            Turno.Estado.CANCELADO_ADMIN,
            Turno.Estado.EXPIRADO,
            Turno.Estado.JUGADO,  # Jugados se muestran solo en historial
        ]
    ).select_related('cancha', 'cancha__complejo', 'cliente').order_by('fecha', 'hora_inicio')
    
    context = {
        'complejo': complejo,
        'turnos_activos': turnos_activos,
        'hoy': hoy,
    }
    
    return render(request, 'cliente/turnos_actuales.html', context)


@login_required
def historial_turnos(request):
    """Vista de historial de turnos del cliente."""
    if not request.user.es_cliente:
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    if not request.user.complejo:
        messages.error(request, 'No tenés un complejo asignado')
        return redirect('dashboard')
    
    complejo = request.user.complejo
    hoy = timezone.now().date()
    
    # Obtener filtro de día desde parámetro GET
    dia_filtro = request.GET.get('dia')
    
    # Obtener todos los turnos del cliente (incluyendo cancelados y expirados)
    # Optimizado con select_related para evitar N+1 queries
    turnos_historial = Turno.objects.filter(
        cliente=request.user,
        cancha__complejo=complejo
    ).select_related('cancha', 'cancha__complejo', 'cliente').order_by('-fecha', '-hora_inicio')
    
    # Filtrar por día si se proporciona
    if dia_filtro:
        try:
            fecha_filtro = datetime.strptime(dia_filtro, '%Y-%m-%d').date()
            turnos_historial = turnos_historial.filter(fecha=fecha_filtro)
        except ValueError:
            pass  # Si la fecha es inválida, mostrar todos
    
    # Generar selector de días (próximos 7 días)
    dias_semana_selector = []
    for i in range(7):
        fecha = hoy + timedelta(days=i)
        dias_nombres = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        if i == 0:
            nombre = 'Hoy'
        elif i == 1:
            nombre = 'Mañana'
        else:
            nombre = dias_nombres[fecha.weekday()]
        
        dias_semana_selector.append({
            'fecha': fecha,
            'nombre': nombre,
            'activo': dia_filtro == fecha.strftime('%Y-%m-%d')
        })
    
    context = {
        'complejo': complejo,
        'turnos_historial': turnos_historial,
        'hoy': hoy,
        'dia_filtro': dia_filtro or '',
        'dias_semana_selector': dias_semana_selector,
    }
    
    return render(request, 'cliente/historial.html', context)


@login_required
def mi_perfil(request):
    """Vista del perfil del cliente."""
    if not request.user.es_cliente:
        messages.error(request, 'No autorizado')
        return redirect('dashboard')

    from decimal import Decimal
    from django.utils import timezone

    complejo = request.user.complejo
    hoy = timezone.localdate()

    turnos_qs = Turno.objects.filter(cliente=request.user)
    if complejo:
        turnos_qs = turnos_qs.filter(cancha__complejo=complejo)

    turnos_activos = turnos_qs.filter(fecha__gte=hoy).exclude(
        estado__in=[
            Turno.Estado.CANCELADO_USUARIO,
            Turno.Estado.CANCELADO_ADMIN,
            Turno.Estado.EXPIRADO,
            Turno.Estado.JUGADO,
        ]
    )
    turnos_reservados = turnos_qs.filter(
        fecha__gte=hoy,
        estado=Turno.Estado.CONFIRMADO,
    )
    turnos_cancelados = turnos_qs.filter(
        estado__in=[
            Turno.Estado.CANCELADO_USUARIO,
            Turno.Estado.CANCELADO_ADMIN,
            Turno.Estado.EXPIRADO,
        ]
    )
    turnos_jugados = turnos_qs.filter(estado=Turno.Estado.JUGADO)

    creditos_actuales = (
        request.user.get_creditos_disponibles(complejo) if complejo else Decimal("0.00")
    )

    context = {
        'complejo': complejo,
        'stats_turnos_activos': turnos_activos.count(),
        'stats_turnos_reservados': turnos_reservados.count(),
        'stats_turnos_cancelados': turnos_cancelados.count(),
        'stats_turnos_jugados': turnos_jugados.count(),
        'stats_creditos_actuales': creditos_actuales,
    }

    return render(request, 'cliente/perfil.html', context)


@login_required
def turnos_en_vivo(request):
    """
    Dashboard estilo aeropuerto con turnos en tiempo real.
    Muestra una columna por cancha (todas las canchas activas del complejo),
    con turnos clasificados por estado temporal.
    """
    if not request.user.puede_gestionar_turnos:
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    complejo = request.user.complejo
    if not complejo:
        messages.error(request, 'No tenés un complejo asignado')
        return redirect('dashboard')
    
    # Obtener todas las canchas activas del complejo
    canchas = Cancha.objects.filter(
        complejo=complejo,
        activa=True
    ).order_by('nombre')
    
    hoy = timezone.now().date()
    ahora = timezone.now()
    
    # Estructura de datos: {cancha: {'turnos': [...], 'nombre': '...'}}
    canchas_con_turnos = []
    
    for cancha in canchas:
        # Obtener turnos del día actual que no estén cancelados
        turnos = Turno.objects.filter(
            cancha=cancha,
            fecha=hoy
        ).exclude(
            estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
        ).select_related('cliente').order_by('hora_inicio')
        
        # Clasificar cada turno según su estado temporal
        turnos_clasificados = []
        for turno in turnos:
            # Calcular fecha/hora de inicio y fin del turno
            fecha_hora_inicio = timezone.make_aware(
                timezone.datetime.combine(turno.fecha, turno.hora_inicio)
            )
            fecha_hora_fin = fecha_hora_inicio + timedelta(minutes=turno.duracion_minutos)
            
            # Determinar estado temporal
            if ahora > fecha_hora_fin:
                estado_temporal = 'terminado'  # Gris
            elif ahora >= fecha_hora_inicio:
                estado_temporal = 'jugando'  # Verde
            else:
                estado_temporal = 'por_comenzar'  # Azul
            
            turnos_clasificados.append({
                'turno': turno,
                'estado_temporal': estado_temporal,
                'hora_inicio': turno.hora_inicio,
                'hora_fin': turno.hora_fin,
            })
        
        canchas_con_turnos.append({
            'cancha': cancha,
            'turnos': turnos_clasificados,
        })
    
    context = {
        'complejo': complejo,
        'canchas_con_turnos': canchas_con_turnos,
        'hoy': hoy,
        'ahora': ahora,
    }
    
    return render(request, 'staff/turnos_en_vivo.html', context)


def _mp_state_key():
    return getattr(settings, "MP_OAUTH_STATE_SECRET", None) or settings.SECRET_KEY


def _mp_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


@login_required
def mp_oauth_debug(request):
    """
    Endpoint de diagnóstico para validar qué parámetros OAuth está generando el backend.
    Importante: NO devuelve secretos.
    """
    user = request.user
    if not user.puede_gestionar_complejo:
        return JsonResponse({"error": "forbidden"}, status=403)

    complejo = user.complejo or getattr(request, 'complejo_actual', None)
    if not complejo:
        return JsonResponse({"error": "no_complejo"}, status=400)

    # Construir una URL de ejemplo (con state ficticio) para inspección visual.
    code_verifier = "debug_verifier_no_usar"
    code_challenge = _mp_code_challenge(code_verifier)
    state_payload = {"c": complejo.id, "u": user.id, "ts": "debug"}
    state = signing.dumps(state_payload, key=_mp_state_key())

    params = {
        "response_type": "code",
        "client_id": settings.MP_CLIENT_ID,
        "redirect_uri": settings.MP_REDIRECT_URI,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "platform_id": "mp",
        "scope": "offline_access",
    }
    auth_url = "https://auth.mercadopago.com/authorization?" + urlencode(params)

    def _mask(v: str, keep=4):
        if not v:
            return ""
        s = str(v)
        if len(s) <= keep:
            return "*" * len(s)
        return ("*" * (len(s) - keep)) + s[-keep:]

    return JsonResponse(
        {
            "mp_client_id_last4": str(settings.MP_CLIENT_ID)[-4:] if settings.MP_CLIENT_ID else "",
            "mp_redirect_uri": settings.MP_REDIRECT_URI,
            "mp_oauth_ready": bool(settings.MP_CLIENT_ID and settings.MP_CLIENT_SECRET and settings.MP_REDIRECT_URI),
            "mp_client_secret_present": bool(settings.MP_CLIENT_SECRET),
            "mp_client_secret_masked": _mask(settings.MP_CLIENT_SECRET, keep=4) if settings.MP_CLIENT_SECRET else "",
            "auth_url": auth_url,
            "note": "Abrí auth_url en el navegador. Si MP dice 'la aplicación no está preparada', el problema es del lado de la app/credenciales en MP (entorno, permisos, app type) o mismatch de redirect_uri.",
        }
    )


@login_required
def mp_oauth_start(request):
    """Inicia el flujo OAuth (Authorization Code + PKCE) para el complejo del usuario."""
    if not (settings.MP_CLIENT_ID and settings.MP_CLIENT_SECRET and settings.MP_REDIRECT_URI):
        messages.error(request, "Falta configurar MP_CLIENT_ID / MP_CLIENT_SECRET / MP_REDIRECT_URI.")
        return redirect('dashboard')
    
    user = request.user
    if not user.puede_gestionar_complejo:
        messages.error(request, "No tenés permisos para conectar Mercado Pago.")
        return redirect('dashboard')
    
    complejo = user.complejo or getattr(request, 'complejo_actual', None)
    if not complejo:
        messages.error(request, "No se pudo determinar el complejo actual.")
        return redirect('dashboard')
    
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = _mp_code_challenge(code_verifier)
    state_payload = {
        "c": complejo.id,
        "u": user.id,
        "ts": timezone.now().isoformat(),
    }
    state = signing.dumps(state_payload, key=_mp_state_key())
    cache.set(f"mp_oauth_cv:{state}", code_verifier, timeout=900)
    
    params = {
        "response_type": "code",
        "client_id": settings.MP_CLIENT_ID,
        "redirect_uri": settings.MP_REDIRECT_URI,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "platform_id": "mp",
        "scope": "offline_access",
    }
    auth_url = "https://auth.mercadopago.com/authorization?" + urlencode(params)
    return redirect(auth_url)


def mp_oauth_callback(request):
    """Callback de OAuth: intercambia el code por tokens y los guarda cifrados por complejo."""
    error = request.GET.get("error")
    if error:
        messages.error(request, f"Mercado Pago devolvió un error: {error}")
        return redirect("dashboard")
    
    code = request.GET.get("code")
    state = request.GET.get("state")
    if not code or not state:
        messages.error(request, "Faltan parámetros de OAuth (code/state).")
        return redirect("dashboard")
    
    try:
        payload = signing.loads(state, key=_mp_state_key(), max_age=900)
    except Exception:
        messages.error(request, "State inválido o expirado.")
        return redirect("dashboard")
    
    code_verifier = cache.get(f"mp_oauth_cv:{state}")
    cache.delete(f"mp_oauth_cv:{state}")
    if not code_verifier:
        messages.error(request, "Code verifier expirado. Iniciá de nuevo la conexión.")
        return redirect("dashboard")
    
    complejo_id = payload.get("c")
    user_id = payload.get("u")
    # Nota: este callback puede ser accedido como usuario no autenticado (por redirección externa).
    # El `state` está firmado y expira, así que lo usamos como validación principal.
    # Si el usuario está autenticado, además verificamos que coincida.
    if getattr(request, "user", None) and request.user.is_authenticated:
        if request.user.id != user_id and not request.user.es_superadmin:
            messages.error(request, "El usuario autenticado no coincide con la solicitud de OAuth.")
            return redirect("dashboard")
    
    data = {
        "client_id": settings.MP_CLIENT_ID,
        "client_secret": settings.MP_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": settings.MP_REDIRECT_URI,
        "code_verifier": code_verifier,
    }
    
    try:
        resp = requests.post(
            "https://api.mercadopago.com/oauth/token",
            json=data,
            timeout=10,
        )
        body = resp.json()
    except Exception as exc:
        messages.error(request, f"No se pudo contactar a Mercado Pago: {exc}")
        return redirect("dashboard")
    
    if resp.status_code >= 300:
        mp_msg = body.get("message") or body.get("error") or body
        messages.error(request, f"Mercado Pago rechazó el intercambio de código: {mp_msg}")
        return redirect("dashboard")
    
    access_token = body.get("access_token")
    refresh_token = body.get("refresh_token")
    expires_in = body.get("expires_in")
    mp_user_id = body.get("user_id")
    
    if not access_token:
        messages.error(request, "Mercado Pago no devolvió access_token.")
        return redirect("dashboard")
    
    integ, _ = IntegracionMercadoPago.objects.get_or_create(
        complejo_id=complejo_id,
        defaults={"modo": IntegracionMercadoPago.Modo.PROD},
    )
    integ.set_tokens(access_token, refresh_token=refresh_token, expires_in=expires_in, mp_user_id=mp_user_id)
    integ.save()
    
    # Redirigir al subdominio del complejo (tenant) si es posible.
    redirect_host = None
    try:
        base_domains = getattr(settings, "TENANT_BASE_DOMAINS", None)
        if isinstance(base_domains, str):
            base_domains = [base_domains]
        base_domain = None
        if base_domains:
            for bd in base_domains:
                if bd and str(bd).strip():
                    base_domain = str(bd).strip().lower().rstrip(".")
                    break

        complejo = Complejo.objects.filter(id=complejo_id).first()
        tenant_label = None
        if complejo:
            tenant_label = (complejo.subdominio or complejo.slug or "").strip().lower().strip(".")

        if base_domain and tenant_label:
            redirect_host = f"{tenant_label}.{base_domain}"
    except Exception:  # pragma: no cover - defensivo
        redirect_host = None

    messages.success(request, "Cuenta de Mercado Pago conectada correctamente.")

    if redirect_host:
        scheme = "https" if request.is_secure() else "http"
        return redirect(f"{scheme}://{redirect_host}{reverse('dashboard')}")

    # Fallback: redirigir al host actual si no pudimos determinar el tenant.
    canonical_host = request.get_host()
    if canonical_host.lower().startswith("www."):
        canonical_host = canonical_host[4:]
    scheme = "https" if request.is_secure() else "http"
    return redirect(f"{scheme}://{canonical_host}{reverse('dashboard')}")


@login_required
def mp_oauth_disconnect(request):
    """Desconecta (revoca localmente) las credenciales del complejo del usuario."""
    user = request.user
    if not user.puede_gestionar_complejo:
        messages.error(request, "No tenés permisos para desconectar Mercado Pago.")
        return redirect("dashboard")
    
    complejo = user.complejo or getattr(request, 'complejo_actual', None)
    if not complejo:
        messages.error(request, "No se pudo determinar el complejo actual.")
        return redirect("dashboard")
    
    try:
        integ = complejo.mercadopago
    except IntegracionMercadoPago.DoesNotExist:
        messages.info(request, "El complejo no tiene integración configurada.")
        return redirect("dashboard")
    
    integ.access_token = None
    integ.refresh_token = None
    integ.token_expires_at = None
    integ.mp_user_id = None
    integ.activo = False
    integ.revoked_at = timezone.now()
    integ.save(update_fields=['access_token', 'refresh_token', 'token_expires_at', 'mp_user_id', 'activo', 'revoked_at', 'updated_at'])
    
    messages.success(request, "Mercado Pago fue desconectado para este complejo.")
    return redirect("dashboard")


@require_http_methods(["GET", "POST"])
def mercadopago_checkout_demo(request):
    """
    Vista aislada para testear Checkout Pro antes de integrarlo con los turnos.
    """
    if request.method == "GET":
        return render(request, "mercadopago/iniciar_pago.html")
    
    # POST: crear preferencia y redirigir al checkout
    if not settings.MERCADOPAGO_ACCESS_TOKEN:
        messages.error(request, "Configurá MERCADOPAGO_ACCESS_TOKEN en tu .env para iniciar pagos.")
        return redirect("mercadopago_checkout_demo")
    
    sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)
    feedback_url = _build_canonical_absolute_uri(request, reverse("mercadopago_feedback"))
    webhook_url = _build_canonical_absolute_uri(request, reverse("mercadopago_webhook"))
    
    preference = {
        "items": [
            {
                "title": "Turno de Prueba",
                "quantity": 1,
                "unit_price": float(Decimal("100.00")),
                "currency_id": "ARS",
            }
        ],
        "back_urls": {
            # Para auto_return, MP valida especialmente success. En local (http) suele fallar.
            "success": feedback_url,
            "failure": feedback_url,
            "pending": feedback_url,
        },
        # binary_mode fuerza que el pago quede aprobado o rechazado (evita "pending")
        "binary_mode": True,
        "external_reference": f"demo-{timezone.now().timestamp()}",
    }
    
    # Mercado Pago puede rechazar auto_return si success no es HTTPS/valida.
    # En local (http://localhost) es común que falle con:
    # "auto_return invalid. back_url.success must be defined"
    if feedback_url.startswith("https://"):
        preference["auto_return"] = "approved"
    
    # Mercado Pago puede rechazar notification_url si no es HTTPS/URL pública válida.
    # En local (http://localhost) es común el 400: "notification_url attribute must be a valid url"
    if webhook_url.startswith("https://"):
        preference["notification_url"] = webhook_url
    
    try:
        preference_response = sdk.preference().create(preference)
        status_code = preference_response.get("status")
        body = preference_response.get("response") or {}
        
        # En token de test, MP suele proveer `sandbox_init_point`.
        is_test_token = settings.MERCADOPAGO_ACCESS_TOKEN.startswith("TEST-") or settings.MERCADOPAGO_ACCESS_TOKEN.startswith("mp_test")
        init_point = body.get("init_point")
        sandbox_init_point = body.get("sandbox_init_point")
        
        checkout_url = (sandbox_init_point if is_test_token else init_point) or init_point or sandbox_init_point
        if not checkout_url:
            # Dejar error con información útil (mensaje/cause suele venir en 400/401)
            mp_message = body.get("message") or body.get("error") or body.get("status")
            mp_cause = body.get("cause") or body.get("causes") or body.get("details")
            raise ValueError(
                f"MP no devolvió URL de checkout (status={status_code}, message={mp_message}, cause={mp_cause})."
            )
    except Exception as exc:  # pragma: no cover - manejo defensivo
        messages.error(request, f"Error al crear la preferencia: {exc}")
        return redirect("mercadopago_checkout_demo")
    
    messages.info(request, "Redirigiendo a Mercado Pago...")
    return redirect(checkout_url)


@login_required
@require_http_methods(["POST"])
def mp_test_pagar_100(request):
    """
    Crea un pago de prueba de $100 usando la integración (access token) del complejo conectado por OAuth.
    Pensado para validación end-to-end desde el lado cliente.
    """
    user = request.user
    complejo = user.complejo or getattr(request, "complejo_actual", None)
    if not complejo:
        messages.error(request, "No se pudo determinar el complejo actual.")
        return redirect("dashboard")

    try:
        integ = complejo.mercadopago
    except IntegracionMercadoPago.DoesNotExist:
        messages.error(request, "Este complejo no tiene Mercado Pago conectado.")
        return redirect("dashboard")

    if not integ.activo or not integ.access_token_plain:
        messages.error(request, "La integración con Mercado Pago no está activa.")
        return redirect("dashboard")

    sdk = mercadopago.SDK(integ.access_token_plain)
    feedback_url = _build_canonical_absolute_uri(request, reverse("mercadopago_feedback"))
    webhook_url = _build_canonical_absolute_uri(request, reverse("mercadopago_webhook"))

    preference = {
        "items": [
            {
                "title": "Pago de prueba $100",
                "quantity": 1,
                "unit_price": float(Decimal("100.00")),
                "currency_id": "ARS",
            }
        ],
        "back_urls": {
            "success": feedback_url,
            "failure": feedback_url,
            "pending": feedback_url,
        },
        "binary_mode": True,
        "external_reference": f"test100-u{user.id}-c{complejo.id}-{timezone.now().timestamp()}",
    }

    if feedback_url.startswith("https://"):
        preference["auto_return"] = "approved"
    if webhook_url.startswith("https://"):
        preference["notification_url"] = webhook_url

    try:
        preference_response = sdk.preference().create(preference)
        body = preference_response.get("response") or {}
        checkout_url = body.get("init_point") or body.get("sandbox_init_point")
        if not checkout_url:
            mp_message = body.get("message") or body.get("error") or body.get("status")
            mp_cause = body.get("cause") or body.get("causes") or body.get("details")
            raise ValueError(f"MP no devolvió URL de checkout (message={mp_message}, cause={mp_cause}).")
    except Exception as exc:  # pragma: no cover
        messages.error(request, f"Error al crear el pago de prueba: {exc}")
        return redirect("mi_perfil")

    messages.info(request, "Redirigiendo a Mercado Pago (pago de prueba)...")
    return redirect(checkout_url)


@require_http_methods(["GET"])
def mercadopago_feedback(request):
    """
    Recibe los parámetros de retorno de Checkout Pro y los muestra para revisión.
    """
    # Definir a dónde redirigir después de mostrar el resultado.
    # Importante: si el usuario no está autenticado (por ejemplo, por mismatch www/no-www),
    # no forzar una URL con login_required porque parece un "deslogueo".
    if request.user.is_authenticated:
        if getattr(request.user, "es_cliente", False):
            redirect_url = reverse("turnos_actuales")
        else:
            redirect_url = reverse("dashboard")
    else:
        redirect_url = reverse("home")

    requested_redirect = (request.GET.get("redirect_url") or "").strip()
    if requested_redirect:
        if url_has_allowed_host_and_scheme(
            requested_redirect,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            redirect_url = requested_redirect

    context = {
        "payment_id": request.GET.get("payment_id"),
        "status": request.GET.get("status"),
        "merchant_order_id": request.GET.get("merchant_order_id"),
        "preference_id": request.GET.get("preference_id"),
        "redirect_url": redirect_url,
        "auto_redirect_seconds": 10,
    }
    return render(request, "mercadopago/feedback.html", context)


@csrf_exempt
@require_http_methods(["POST"])
def mercadopago_webhook(request):
    """
    Endpoint para recibir notificaciones (webhooks/IPN) de Mercado Pago.
    
    Nota: para producción, conviene validar la notificación:
    - verificar firma/secret (si lo configurás en MP)
    - y consultar a la API (payment) para obtener el estado final
    """
    # MP puede enviar JSON o form-data según configuración/evento
    raw_body = request.body.decode("utf-8") if request.body else ""
    try:
        body_json = json.loads(raw_body) if raw_body else {}
    except Exception:
        body_json = {}

    # Extraer IDs
    payment_id = (
        request.GET.get("id")
        or request.GET.get("data.id")
        or (body_json.get("data") or {}).get("id")
    )
    topic = request.GET.get("topic") or body_json.get("type") or body_json.get("topic")
    user_id = body_json.get("user_id") or body_json.get("userId")

    integ = None
    if user_id:
        integ = IntegracionMercadoPago.objects.filter(mp_user_id=str(user_id), activo=True).first()

    status = PagoMercadoPago.Estado.UNKNOWN
    status_detail = None
    external_reference = None
    merchant_order_id = None
    preference_id = None
    amount = None
    currency_id = None

    # Consultar a MP si es un pago y tenemos access token
    if topic == "payment" and payment_id and integ and integ.access_token_plain:
        try:
            resp = requests.get(
                f"https://api.mercadopago.com/v1/payments/{payment_id}",
                headers={"Authorization": f"Bearer {integ.access_token_plain}"},
                timeout=8,
            )
            if resp.status_code < 300:
                p = resp.json()
                status = p.get("status") or status
                status_detail = p.get("status_detail")
                external_reference = p.get("external_reference")
                preference_id = p.get("preference_id")
                merchant_order_id = p.get("order") or p.get("merchant_order_id")
                amount = p.get("transaction_amount")
                currency_id = p.get("currency_id")
                # Si el webhook trae user_id, mantenemos el match
        except Exception:
            # No romper el webhook; MP reintentará si necesita
            pass

    # Persistir registro mínimo
    if payment_id:
        defaults = {
            "integration": integ,
            "complejo": integ.complejo if integ else None,
            "status": status or PagoMercadoPago.Estado.UNKNOWN,
            "status_detail": status_detail,
            "external_reference": external_reference,
            "preference_id": preference_id,
            "merchant_order_id": merchant_order_id,
            "amount": amount,
            "currency_id": currency_id,
            "source": "webhook",
            "raw_payload": body_json or raw_body[:2000],
        }
        # Si no tenemos complejo, no podemos guardar por FK; en ese caso no guardamos
        if defaults["complejo"]:
            PagoMercadoPago.objects.update_or_create(
                payment_id=payment_id,
                defaults=defaults,
            )

    # Si el external_reference apunta a un turno, sincronizar estado del turno
    turno_obj = None
    if external_reference and isinstance(external_reference, str) and external_reference.startswith("turno:"):
        try:
            turno_id = int(external_reference.split("turno:")[-1])
            turno_obj = Turno.objects.select_related('cancha', 'cancha__complejo', 'cliente').filter(id=turno_id).first()
        except Exception:
            turno_obj = None

    if turno_obj:
        status_lower = (status or "").lower()
        monto_mp_decimal = Decimal(str(amount)) if amount is not None else Decimal("0.00")

        # Actualizar campos comunes
        turno_obj.mp_payment_id = payment_id
        turno_obj.mp_status = status
        turno_obj.mp_status_detail = status_detail
        turno_obj.mp_preference_id = preference_id or turno_obj.mp_preference_id
        turno_obj.mp_amount = monto_mp_decimal if monto_mp_decimal > 0 else turno_obj.mp_amount
        turno_obj.mp_updated_at = timezone.now()

        if status_lower == "approved":
            nueva_senia = turno_obj.senia_pagada + monto_mp_decimal
            # No dejar la seña por debajo de lo ya pagado
            if nueva_senia < turno_obj.senia_pagada:
                nueva_senia = turno_obj.senia_pagada
            # Limitar a la seña requerida (no importa si MP cobró de más)
            turno_obj.senia_pagada = nueva_senia if nueva_senia <= turno_obj.senia_requerida else turno_obj.senia_requerida
            turno_obj.expira_en = None
            turno_obj.save(update_fields=[
                'senia_pagada',
                'mp_payment_id',
                'mp_status',
                'mp_status_detail',
                'mp_preference_id',
                'mp_amount',
                'mp_updated_at',
                'expira_en',
                'updated_at',
            ])
        elif status_lower in {"pending", "in_process", "in_mediation"}:
            # Mantener el turno pendiente; opcionalmente extender expiración unos minutos
            try:
                minutos_expiracion = int(turno_obj.cancha.complejo.preferencias.minutos_expiracion_pago)
            except Exception:
                minutos_expiracion = 10
            turno_obj.expira_en = timezone.now() + timedelta(minutes=minutos_expiracion)
            turno_obj.save(update_fields=[
                'mp_payment_id',
                'mp_status',
                'mp_status_detail',
                'mp_preference_id',
                'mp_amount',
                'mp_updated_at',
                'expira_en',
                'updated_at',
            ])
        elif status_lower in {"rejected", "cancelled", "refunded", "charged_back"}:
            _devolver_creditos_turno(turno_obj, "Seña devuelta: pago rechazado/cancelado en MP")
            turno_obj.estado = Turno.Estado.EXPIRADO
            turno_obj.cancelacion_origen = Turno.CancelacionOrigen.SISTEMA
            turno_obj.cancelacion_motivo = "Pago de seña rechazado/cancelado en MP"
            turno_obj.cancelado_por = None
            turno_obj.cancelado_en = timezone.now()
            turno_obj.expira_en = None
            turno_obj.save(update_fields=[
                'estado',
                'cancelacion_origen',
                'cancelacion_motivo',
                'cancelado_por',
                'cancelado_en',
                'mp_payment_id',
                'mp_status',
                'mp_status_detail',
                'mp_preference_id',
                'mp_amount',
                'mp_updated_at',
                'expira_en',
                'updated_at',
            ])
            TurnoService.invalidar_cache_slots(turno_obj.cancha.complejo.id, turno_obj.fecha)

    return JsonResponse({"ok": True})
@login_required
def ops_health(request):
    """
    Endpoint de diagnóstico (producción) para validar:
    - Redis/cache accesible
    - celery-worker procesando tareas
    - celery-beat corriendo (via heartbeat en cache)
    
    Seguridad:
    - Requiere usuario logueado
    - Requiere superadmin
    - Requiere token secreto (OPS_HEALTHCHECK_TOKEN) por header X-Ops-Token o ?token=
    """
    # 1) Solo superadmin
    if not getattr(request.user, "es_superadmin", False):
        return JsonResponse({"ok": False, "error": "No autorizado"}, status=403)

    # 2) Token secreto por env
    expected = (os.getenv("OPS_HEALTHCHECK_TOKEN") or "").strip()
    provided = (request.headers.get("X-Ops-Token") or request.GET.get("token") or "").strip()
    if not expected or not provided or not compare_digest(provided, expected):
        # 404 para no filtrar existencia del endpoint
        return JsonResponse({"detail": "Not found"}, status=404)

    data: dict = {"ok": False, "checks": {}}

    # Redis / cache
    redis_ok = False
    redis_error = None
    try:
        cache.set("ops:redis_probe", "ok", timeout=30)
        redis_ok = cache.get("ops:redis_probe") == "ok"
    except Exception as exc:
        redis_error = str(exc)
    data["checks"]["redis_cache"] = {"ok": redis_ok, "error": redis_error}

    # Celery worker (ejecuta una tarea y espera breve)
    worker_ok = False
    worker_state = "unknown"
    worker_error = None
    try:
        from core.tasks import ops_celery_ping_task
        res = ops_celery_ping_task.delay()
        worker_state = res.state
        try:
            payload = res.get(timeout=2)
            worker_ok = bool(payload and payload.get("ok") is True)
            worker_state = "SUCCESS" if worker_ok else res.state
        except Exception as exc:  # timeout u otros
            worker_ok = False
            worker_error = f"{type(exc).__name__}: {exc}"
            worker_state = res.state
    except Exception as exc:
        worker_ok = False
        worker_error = f"{type(exc).__name__}: {exc}"
    data["checks"]["celery_worker"] = {"ok": worker_ok, "state": worker_state, "error": worker_error}

    # Celery beat (heartbeat periódico)
    beat_ok = False
    beat_error = None
    beat_last_iso = None
    try:
        beat_last_iso = cache.get("ops:celery_beat_heartbeat")
        if beat_last_iso:
            dt = parse_datetime(beat_last_iso)
            if dt is not None:
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt, timezone.get_current_timezone())
                age = (timezone.now() - dt).total_seconds()
                beat_ok = age <= 600  # 10 minutos de tolerancia (heartbeat corre cada 5 min)
            else:
                beat_error = "Formato de heartbeat inválido"
        else:
            beat_error = "Heartbeat no encontrado"
    except Exception as exc:
        beat_error = f"{type(exc).__name__}: {exc}"
    data["checks"]["celery_beat"] = {"ok": beat_ok, "last": beat_last_iso, "error": beat_error}

    data["ok"] = bool(redis_ok and worker_ok and beat_ok)
    return JsonResponse(data, status=200 if data["ok"] else 503)
