"""
Views de la aplicación core.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.db import transaction, IntegrityError
from django.db.models import Sum, Q
from django.views.decorators.csrf import ensure_csrf_cookie
from django.core.paginator import Paginator
from django.urls import reverse
from datetime import datetime, timedelta, time as dt_time
from decimal import Decimal
from .models import Usuario, Complejo, Cancha, Turno, Bloqueo, CreditoCliente, TurnoFijo
from .services import TurnoService, CreditoService


def home(request):
    """Vista principal del sistema."""
    return render(request, 'home.html')


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
                    complejo=complejo_actual,  # Asignar complejo del subdominio
                )
                
                # TEMPORAL: Asignar crédito inicial de 150.000 para tests
                if complejo_actual:
                    CreditoService.generar_credito(
                        usuario=user,
                        complejo=complejo_actual,
                        monto=Decimal('150000.00'),
                        motivo='Crédito inicial de bienvenida (temporal para tests)',
                        turno_origen=None,
                        creado_por=None,  # Crédito automático del sistema
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
        # Marcar turnos como jugados automáticamente
        Turno.marcar_turnos_como_jugados()
        
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
        turnos_cliente = Turno.objects.filter(
            cliente=user,
            cancha__complejo=complejo
        ).select_related(
            'cancha',
            'cancha__complejo',
            'cliente'
        ).order_by('fecha', 'hora_inicio')

        turnos_activos = turnos_cliente.filter(
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
        # Marcar turnos como jugados automáticamente
        Turno.marcar_turnos_como_jugados()
        
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
            # Mostrar solo turnos del pasado (fecha anterior a hoy)
            turnos_complejo_qs = turnos_complejo_qs.filter(fecha__lt=hoy)
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
        
        # Generar lista de próximos 7 días para el selector rápido
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
        )
    except IntegrityError:
        # Otro usuario tomó el turno en paralelo o existe un turno activo igual
        TurnoService.invalidar_cache_slots(cancha.complejo.id, fecha_obj)
        messages.error(request, 'Ese horario acaba de reservarse. Elegí otro turno disponible.')
        return redirect('dashboard')
    
    # Invalidar caché de slots para esta fecha
    TurnoService.invalidar_cache_slots(cancha.complejo.id, fecha_obj)
    
    messages.success(request, f'¡Turno reservado exitosamente! {cancha.nombre} - {fecha_obj.strftime("%d/%m/%Y")} {hora_obj.strftime("%H:%M")}')
    
    # Redirigir a la misma fecha para que el cliente pueda seguir viendo turnos disponibles
    return redirect(f'{reverse("dashboard")}?fecha={fecha_obj.strftime("%Y-%m-%d")}')


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
    # Nota: Cuando el cliente cancela, no hay creado_por (es automático del sistema)
    if turno.senia_pagada > 0:
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
    
    messages.success(request, f'Turno cancelado. Se te acreditó ${turno.senia_pagada} en créditos.')
    return redirect('turnos_actuales')


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
            creado_por=request.user,  # Staff/admin que cancela
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
    
    # Bloquear edición de turnos ya jugados o que ya pasaron
    if turno.estado == Turno.Estado.JUGADO or turno.ya_paso:
        messages.error(request, 'Solo se pueden editar turnos futuros que no hayan sido jugados')
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
    
    # Bloquear edición de turnos ya jugados o que ya pasaron
    if turno.estado == Turno.Estado.JUGADO or turno.ya_paso:
        messages.error(request, 'Solo se pueden editar turnos futuros que no hayan sido jugados')
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
    
    # Usar el servicio optimizado para generar slots disponibles
    slots_por_hora_staff = TurnoService.generar_slots_staff(complejo, fecha_base)
    slots_ordenados = sorted(slots_por_hora_staff.items(), key=lambda x: x[0])
    
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
        turno.save(update_fields=['estado', 'updated_at'])
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
    
    # Verificar si se forzó la creación (ignorar conflictos)
    forzar_creacion = request.POST.get('forzar_creacion') == 'true'
    
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
    
    # Marcar turnos como jugados automáticamente
    Turno.marcar_turnos_como_jugados()
    
    # Obtener turnos activos (no cancelados, no expirados)
    # Optimizado con select_related para evitar N+1 queries
    turnos_activos = Turno.objects.filter(
        cliente=request.user,
        cancha__complejo=complejo
    ).exclude(
        estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
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
    
    # Marcar turnos como jugados automáticamente
    Turno.marcar_turnos_como_jugados()
    
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
    
    context = {
        'complejo': request.user.complejo,
    }
    
    return render(request, 'cliente/perfil.html', context)


@login_required
def turnos_en_vivo(request):
    """
    Dashboard estilo aeropuerto con turnos en tiempo real.
    Muestra 3 columnas (una por cancha) con turnos clasificados por estado temporal.
    """
    if not request.user.puede_gestionar_turnos:
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    complejo = request.user.complejo
    if not complejo:
        messages.error(request, 'No tenés un complejo asignado')
        return redirect('dashboard')
    
    # Obtener las primeras 3 canchas activas del complejo
    canchas = Cancha.objects.filter(
        complejo=complejo,
        activa=True
    ).order_by('nombre')[:3]
    
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
    
    # Si hay menos de 3 canchas, agregar columnas vacías
    while len(canchas_con_turnos) < 3:
        canchas_con_turnos.append({
            'cancha': None,
            'turnos': [],
        })
    
    context = {
        'complejo': complejo,
        'canchas_con_turnos': canchas_con_turnos,
        'hoy': hoy,
        'ahora': ahora,
    }
    
    return render(request, 'staff/turnos_en_vivo.html', context)
