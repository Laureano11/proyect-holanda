"""
Views de la aplicación core.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Sum, Q
from django.core.paginator import Paginator
from datetime import datetime, timedelta, time as dt_time
from decimal import Decimal
from .models import Usuario, Complejo, Cancha, Turno, Bloqueo, CreditoCliente, TurnoFijo
from .services import TurnoService, CreditoService


def home(request):
    """Vista principal del sistema."""
    return render(request, 'home.html')


def login_view(request):
    """Vista de login simple."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, f'¡Bienvenido, {user.first_name or user.username}!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos')
    
    return render(request, 'auth/login.html')


def register_view(request):
    """Vista de registro simple con selector de rol."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    # Obtener complejos disponibles para el selector
    complejos = Complejo.objects.filter(activo=True)
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email', '')
        password = request.POST.get('password')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        celular = request.POST.get('celular', '')
        rol = request.POST.get('rol', Usuario.Rol.CLIENTE)
        complejo_id = request.POST.get('complejo')
        
        # Validación mínima
        if Usuario.objects.filter(username=username).exists():
            messages.error(request, 'Ese nombre de usuario ya existe')
            return render(request, 'auth/register.html', {'complejos': complejos})
        
        # Crear usuario
        user = Usuario.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            celular=celular,
            rol=rol,
        )
        
        # Asignar complejo si se seleccionó uno
        if complejo_id:
            try:
                complejo = Complejo.objects.get(id=complejo_id)
                user.complejo = complejo
                user.save()
                
                # TEMPORAL: Asignar crédito inicial de 150.000 para tests
                CreditoCliente.objects.create(
                    usuario=user,
                    complejo=complejo,
                    monto=Decimal('150000.00'),
                    motivo='Crédito inicial de bienvenida (temporal para tests)',
                    activo=True
                )
            except Complejo.DoesNotExist:
                pass
        
        # Login automático
        login(request, user)
        messages.success(request, f'¡Cuenta creada exitosamente! Bienvenido, {user.first_name or user.username}')
        return redirect('dashboard')
    
    return render(request, 'auth/register.html', {'complejos': complejos})


@login_required
def actualizar_perfil(request):
    """Actualizar datos personales (solo campos seguros)."""
    if not request.user.es_cliente:
        messages.error(request, 'No tenés permisos para editar este perfil')
        return redirect('dashboard')

    if request.method != 'POST':
        return redirect('dashboard')

    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    direccion = request.POST.get('direccion', '').strip()

    user = request.user
    if first_name:
        user.first_name = first_name
    if last_name:
        user.last_name = last_name
    user.direccion = direccion
    user.save()

    messages.success(request, 'Perfil actualizado correctamente')
    return redirect('dashboard')


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
    
    context = {
        'user': user,
        'hoy': hoy,
        'fecha_seleccionada': hoy,
        'fecha_minima': fecha_minima_default,
        'fecha_maxima': fecha_maxima_default,
        'es_fecha_pasada': False,
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
        
        # Usar servicio optimizado para generar slots disponibles
        slots_result = TurnoService.generar_slots_disponibles(complejo, fecha_seleccionada)
        slots_por_hora = slots_result['slots_por_hora']
        total_disponibles = slots_result['total_disponibles']
        es_fecha_pasada = slots_result['es_fecha_pasada']
        
        # Convertir a lista ordenada por hora para el template
        slots_ordenados = sorted(slots_por_hora.items(), key=lambda x: x[0])
        
        # Calcular créditos disponibles del cliente (método optimizado del modelo)
        creditos_disponibles = user.get_creditos_disponibles(complejo)
        
        # Obtener turnos del cliente (con select_related para evitar N+1)
        turnos_cliente = Turno.objects.filter(
            cliente=user,
            cancha__complejo=complejo
        ).select_related('cancha').order_by('fecha', 'hora_inicio')

        turnos_activos = turnos_cliente.filter(
            estado__in=[Turno.Estado.CONFIRMADO, Turno.Estado.PENDIENTE_PAGO]
        )
        turnos_historial = turnos_cliente.exclude(
            id__in=turnos_activos.values_list('id', flat=True)
        )
        
        # Turnos del mes actual
        mes_actual = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        turnos_mes = turnos_cliente.filter(fecha__gte=mes_actual).count()
        
        # Calcular fechas para el selector (ventana amplia centrada en la fecha seleccionada)
        fecha_minima = fecha_seleccionada - timedelta(days=rango_selector_dias)
        fecha_maxima = fecha_seleccionada + timedelta(days=rango_selector_dias)
        
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
        
        # Filtros y paginación
        estado_filtro = request.GET.get('estado')
        cancha_filtro = request.GET.get('cancha')
        cliente_filtro = request.GET.get('cliente', '').strip()
        desde = request.GET.get('desde')
        hasta = request.GET.get('hasta')
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
        turnos_base_qs = Turno.objects.filter(
            cancha__complejo=complejo
        ).exclude(
            estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
        ).select_related('cancha', 'cliente')
        
        # Query de listado (incluye todos los estados para permitir filtros)
        turnos_complejo_qs = Turno.objects.filter(
            cancha__complejo=complejo
        ).select_related('cancha', 'cliente')
        
        # Estadísticas (queries optimizadas)
        turnos_hoy = turnos_base_qs.filter(fecha=hoy).count()
        pendientes_pago = turnos_base_qs.filter(estado=Turno.Estado.PENDIENTE_PAGO).count()
        confirmados = turnos_base_qs.filter(estado=Turno.Estado.CONFIRMADO).count()
        cancelados = Turno.objects.filter(
            cancha__complejo=complejo,
            estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN]
        ).count()
        
        # Aplicar filtros al listado
        if not estado_filtro:
            # Por defecto ocultar cancelados/expirados (se muestran solo si se filtra)
            turnos_complejo_qs = turnos_complejo_qs.exclude(
                estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
            )
        else:
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
        })
    
    # Redirigir según rol
    if user.es_superadmin:
        return render(request, 'dashboard/superadmin.html', context)
    elif user.es_admin:
        return render(request, 'dashboard/admin.html', context)
    elif user.es_staff_complejo:
        return render(request, 'dashboard/staff.html', context)
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
    
    # Calcular créditos disponibles (método optimizado del modelo)
    creditos_disponibles = request.user.get_creditos_disponibles(cancha.complejo)
    
    context = {
        'cancha': cancha,
        'fecha': fecha_obj,
        'hora': hora_obj,
        'precio': cancha.precio_hora,
        'senia': cancha.precio_senia,
        'creditos_disponibles': creditos_disponibles,
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
    
    # Verificar si tiene créditos suficientes
    if creditos_disponibles < senia_requerida:
        messages.error(request, f'No tenés créditos suficientes. Necesitás ${senia_requerida}, tenés ${creditos_disponibles}')
        return redirect('dashboard')
    
    # Usar servicio de créditos para aplicar el pago
    creditos_a_usar = min(creditos_disponibles, senia_requerida)
    creditos_aplicados = CreditoService.aplicar_creditos(
        request.user, 
        cancha.complejo, 
        creditos_a_usar
    )
    
    # Crear el turno
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
    )
    
    # Invalidar caché de slots para esta fecha
    TurnoService.invalidar_cache_slots(cancha.complejo.id, fecha_obj)
    
    messages.success(request, f'¡Turno reservado exitosamente! {cancha.nombre} - {fecha_obj.strftime("%d/%m/%Y")} {hora_obj.strftime("%H:%M")}')
    return redirect('dashboard')


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
    
    # Cancelar el turno
    turno.estado = Turno.Estado.CANCELADO_USUARIO
    turno.save(update_fields=['estado', 'updated_at'])
    
    # Generar crédito para el cliente (si pagó seña) usando servicio
    if turno.senia_pagada > 0:
        CreditoService.generar_credito(
            usuario=request.user,
            complejo=turno.cancha.complejo,
            monto=turno.senia_pagada,
            motivo=f'Cancelación turno {turno.cancha.nombre} - {turno.fecha.strftime("%d/%m/%Y")} {turno.hora_inicio.strftime("%H:%M")}',
            turno_origen=turno,
        )
    
    # Invalidar caché de slots
    TurnoService.invalidar_cache_slots(turno.cancha.complejo.id, turno.fecha)
    
    messages.success(request, f'Turno cancelado. Se te acreditó ${turno.senia_pagada} en créditos.')
    return redirect('dashboard')


@login_required
def cancelar_turno_staff(request, turno_id):
    """Cancelar un turno (Staff/Admin)."""
    if not (request.user.es_staff_complejo or request.user.es_admin or request.user.es_superadmin):
        messages.error(request, 'No autorizado')
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
    
    # Cancelar el turno (marcado como cancelado por admin)
    turno.estado = Turno.Estado.CANCELADO_ADMIN
    turno.save(update_fields=['estado', 'updated_at'])
    
    # Generar crédito para el cliente (si pagó seña) usando servicio
    if turno.senia_pagada > 0:
        CreditoService.generar_credito(
            usuario=turno.cliente,
            complejo=turno.cancha.complejo,
            monto=turno.senia_pagada,
            motivo=f'Cancelación por staff - Turno {turno.cancha.nombre} - {turno.fecha.strftime("%d/%m/%Y")} {turno.hora_inicio.strftime("%H:%M")}',
            turno_origen=turno,
        )
    
    # Invalidar caché de slots
    TurnoService.invalidar_cache_slots(turno.cancha.complejo.id, turno.fecha)
    
    messages.success(request, f'Turno cancelado. Se acreditó ${turno.senia_pagada} en créditos al cliente.')
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
    turno.cancha = cancha
    turno.fecha = fecha_obj
    turno.hora_inicio = hora_obj
    turno.estado = nuevo_estado
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
    
    # Calcular turnos disponibles (misma lógica que en dashboard)
    canchas = Cancha.objects.filter(complejo=complejo, activa=True)
    turnos_ocupados = Turno.objects.filter(
        cancha__complejo=complejo,
        fecha=fecha_base
    ).exclude(
        estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
    ).values_list('cancha_id', 'hora_inicio')
    ocupados_set = set(turnos_ocupados)
    bloqueos = Bloqueo.objects.filter(complejo=complejo, fecha=fecha_base)
    
    slots_por_hora = {}
    hora_apertura = complejo.hora_apertura
    hora_cierre = complejo.hora_cierre
    ahora = timezone.now()
    hoy_actual = ahora.date()
    hora_actual = hora_apertura
    
    while hora_actual < hora_cierre:
        # Si es hoy, verificar que el turno no haya empezado ya
        if fecha_base == hoy_actual:
            # Crear datetime del inicio del turno
            inicio_turno = timezone.make_aware(datetime.combine(fecha_base, hora_actual))
            # Si el turno ya empezó (hora actual > hora inicio), saltarlo
            # Usamos > en lugar de >= para permitir reservar el turno si estamos justo en la hora de inicio
            if ahora > inicio_turno:
                hora_actual = (datetime.combine(datetime.today(), hora_actual) + timedelta(hours=1)).time()
                continue
        
        hora_fin = (datetime.combine(datetime.today(), hora_actual) + timedelta(hours=1)).time()
        canchas_disponibles = []
        
        for cancha in canchas:
            esta_bloqueada = False
            for bloqueo in bloqueos:
                if bloqueo.cancha is None or bloqueo.cancha == cancha:
                    if bloqueo.es_dia_completo:
                        esta_bloqueada = True
                        break
                    elif bloqueo.hora_inicio and bloqueo.hora_fin:
                        if bloqueo.hora_inicio <= hora_actual < bloqueo.hora_fin:
                            esta_bloqueada = True
                            break
                    elif bloqueo.hora_inicio and hora_actual >= bloqueo.hora_inicio:
                        esta_bloqueada = True
                        break
            
            esta_ocupada = (cancha.id, hora_actual) in ocupados_set
            
            if not esta_bloqueada and not esta_ocupada:
                canchas_disponibles.append({
                    'cancha': cancha,
                    'precio': cancha.precio_hora,
                    'senia': cancha.precio_senia,
                    'hora': hora_actual,
                })
        
        if canchas_disponibles:
            slots_por_hora[hora_actual] = {
                'hora_inicio': hora_actual,
                'hora_fin': hora_fin,
                'canchas': canchas_disponibles,
            }
        
        hora_actual = (datetime.combine(datetime.today(), hora_actual) + timedelta(hours=1)).time()
    
    slots_ordenados = sorted(slots_por_hora.items(), key=lambda x: x[0])
    
    context = {
        'complejo': complejo,
        'hoy': hoy,
        'fecha_seleccionada': fecha_base,
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
    turnos_qs = Turno.objects.filter(
        cancha__complejo=complejo,
        fecha=fecha_obj
    ).select_related('cliente', 'cancha')
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
        turno.save(update_fields=['estado', 'updated_at'])
        turnos_cancelados += 1
        
        if turno.senia_pagada > 0:
            CreditoService.generar_credito(
                usuario=turno.cliente,
                complejo=turno.cancha.complejo,
                monto=turno.senia_pagada,
                motivo=f'Bloqueo: {turno.cancha.nombre} {turno.fecha.strftime("%d/%m/%Y")} {turno.hora_inicio.strftime("%H:%M")}',
                turno_origen=turno,
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
    hora_inicio = request.POST.get('hora_inicio')
    dias_semana = request.POST.getlist('dias_semana')  # Múltiples días
    fecha_inicio = request.POST.get('fecha_inicio')
    fecha_fin = request.POST.get('fecha_fin', '').strip() or None
    notas = request.POST.get('notas', '').strip()
    
    # Validaciones
    if not all([cancha_id, nombre_cliente, hora_inicio, dias_semana, fecha_inicio]):
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
    
    # Buscar o crear cliente por nombre
    cliente, created = Usuario.objects.get_or_create(
        username=f"cliente_{nombre_cliente.lower().replace(' ', '_')}_{complejo.id}",
        defaults={
            'first_name': nombre_cliente,
            'rol': Usuario.Rol.CLIENTE,
            'complejo': complejo,
        }
    )
    
    if not created:
        cliente.first_name = nombre_cliente
        cliente.complejo = complejo
        cliente.save()
    
    # Crear un TurnoFijo por cada día seleccionado
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
    
    # Mensajes de resultado
    if turnos_creados:
        dias_creados = [t.get_dia_semana_display() for t in turnos_creados]
        messages.success(request, f'Turnos fijos creados para {nombre_cliente} - {cancha.nombre} - {", ".join(dias_creados)} a las {hora_obj.strftime("%H:%M")}')
    
    if turnos_duplicados:
        messages.warning(request, f'Turnos fijos ya existentes para: {", ".join(turnos_duplicados)}')
    
    if not turnos_creados and not turnos_duplicados:
        messages.error(request, 'No se pudo crear ningún turno fijo')
    
    return redirect('turnos_fijos')


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
    direccion = request.POST.get('direccion', '').strip()
    
    # Actualizar solo campos permitidos
    user.first_name = first_name
    user.last_name = last_name
    user.direccion = direccion
    user.save()
    
    messages.success(request, f'Perfil actualizado correctamente')
    return redirect('mi_perfil')


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
    
    # Obtener turnos activos (no cancelados, no expirados)
    turnos_activos = Turno.objects.filter(
        cliente=request.user,
        cancha__complejo=complejo
    ).exclude(
        estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
    ).order_by('fecha', 'hora_inicio')
    
    context = {
        'complejo': complejo,
        'turnos_activos': turnos_activos,
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
    
    # Obtener todos los turnos del cliente (incluyendo cancelados y expirados)
    turnos_historial = Turno.objects.filter(
        cliente=request.user,
        cancha__complejo=complejo
    ).order_by('-fecha', '-hora_inicio')
    
    context = {
        'complejo': complejo,
        'turnos_historial': turnos_historial,
    }
    
    return render(request, 'cliente/historial.html', context)


@login_required
def mi_perfil(request):
    """Vista del perfil del cliente."""
    if not request.user.es_cliente:
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    context = {
        'complejo': request.user.complejo,
    }
    
    return render(request, 'cliente/perfil.html', context)
