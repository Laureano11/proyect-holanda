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
from django.db.models import Sum
from datetime import datetime, timedelta, time as dt_time
from decimal import Decimal
from .models import Usuario, Complejo, Cancha, Turno, Bloqueo, CreditoCliente


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
            except Complejo.DoesNotExist:
                pass
        
        # Login automático
        login(request, user)
        messages.success(request, f'¡Cuenta creada exitosamente! Bienvenido, {user.first_name or user.username}')
        return redirect('dashboard')
    
    return render(request, 'auth/register.html', {'complejos': complejos})


def logout_view(request):
    """Cerrar sesión."""
    logout(request)
    messages.info(request, 'Sesión cerrada correctamente')
    return redirect('home')


@login_required
def dashboard(request):
    """Dashboard según el rol del usuario."""
    user = request.user
    
    context = {
        'user': user,
    }
    
    # Si es cliente, calcular turnos disponibles del día
    if user.es_cliente and user.complejo:
        hoy = timezone.now().date()
        complejo = user.complejo
        
        # Obtener todas las canchas activas del complejo
        canchas = Cancha.objects.filter(complejo=complejo, activa=True)
        
        # Obtener turnos ocupados del día (confirmados o pendientes de pago)
        turnos_ocupados = Turno.objects.filter(
            cancha__complejo=complejo,
            fecha=hoy
        ).exclude(
            estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
        ).values_list('cancha_id', 'hora_inicio')
        
        # Crear set de (cancha_id, hora) ocupados para búsqueda rápida
        ocupados_set = set(turnos_ocupados)
        
        # Obtener bloqueos del día
        bloqueos = Bloqueo.objects.filter(
            complejo=complejo,
            fecha=hoy
        )
        
        # Generar slots disponibles agrupados por hora
        slots_por_hora = {}
        hora_apertura = complejo.hora_apertura
        hora_cierre = complejo.hora_cierre
        
        # Obtener fecha/hora actual del sistema (en timezone de Argentina)
        ahora = timezone.now()
        hoy_actual = ahora.date()
        
        # Generar horas desde apertura hasta cierre (cada hora)
        hora_actual = hora_apertura
        while hora_actual < hora_cierre:
            # Si es hoy, verificar que el turno no haya empezado ya
            if hoy == hoy_actual:
                # Crear datetime del inicio del turno
                inicio_turno = timezone.make_aware(datetime.combine(hoy, hora_actual))
                # Si el turno ya empezó (hora actual >= hora inicio), saltarlo
                if ahora >= inicio_turno:
                    hora_actual = (datetime.combine(datetime.today(), hora_actual) + timedelta(hours=1)).time()
                    continue
            
            # Calcular hora de fin (1 hora después)
            hora_fin = (datetime.combine(datetime.today(), hora_actual) + timedelta(hours=1)).time()
            
            # Lista de canchas disponibles en esta hora
            canchas_disponibles = []
            
            for cancha in canchas:
                # Verificar si está bloqueada esta cancha/hora
                esta_bloqueada = False
                for bloqueo in bloqueos:
                    if bloqueo.cancha is None or bloqueo.cancha == cancha:
                        # Bloqueo de día completo
                        if bloqueo.es_dia_completo:
                            esta_bloqueada = True
                            break
                        # Bloqueo por rango horario
                        elif bloqueo.hora_inicio and bloqueo.hora_fin:
                            if bloqueo.hora_inicio <= hora_actual < bloqueo.hora_fin:
                                esta_bloqueada = True
                                break
                        elif bloqueo.hora_inicio and hora_actual >= bloqueo.hora_inicio:
                            esta_bloqueada = True
                            break
                
                # Verificar si está ocupada
                esta_ocupada = (cancha.id, hora_actual) in ocupados_set
                
                # Determinar estado
                if esta_bloqueada:
                    estado = 'no_disponible'
                elif esta_ocupada:
                    estado = 'reservado'
                else:
                    estado = 'disponible'
                
                # Agregar todas las canchas con su estado
                canchas_disponibles.append({
                    'cancha': cancha,
                    'precio': cancha.precio_hora,
                    'senia': cancha.precio_senia,
                    'estado': estado,
                    'hora': hora_actual,
                })
            
            # Contar canchas disponibles en esta hora
            canchas_disponibles_count = len([c for c in canchas_disponibles if c['estado'] == 'disponible'])
            
            # Agregar todas las horas (incluso si no hay disponibles)
            slots_por_hora[hora_actual] = {
                'hora_inicio': hora_actual,
                'hora_fin': hora_fin,
                'canchas': canchas_disponibles,
                'canchas_disponibles_count': canchas_disponibles_count,
            }
            
            # Avanzar 1 hora
            hora_actual = (datetime.combine(datetime.today(), hora_actual) + timedelta(hours=1)).time()
        
        # Calcular total de slots disponibles
        total_disponibles = sum(len([c for c in slot['canchas'] if c['estado'] == 'disponible']) for slot in slots_por_hora.values())
        
        # Calcular créditos disponibles del cliente
        creditos_totales = CreditoCliente.objects.filter(
            usuario=user,
            complejo=complejo,
            activo=True
        ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
        
        creditos_usados = CreditoCliente.objects.filter(
            usuario=user,
            complejo=complejo,
            activo=True
        ).aggregate(total=Sum('monto_usado'))['total'] or Decimal('0.00')
        
        creditos_disponibles = creditos_totales - creditos_usados
        
        # Obtener turnos del cliente
        turnos_cliente = Turno.objects.filter(
            cliente=user,
            cancha__complejo=complejo
        ).exclude(
            estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
        ).order_by('fecha', 'hora_inicio')
        
        # Turnos del mes actual
        mes_actual = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        turnos_mes = turnos_cliente.filter(fecha__gte=mes_actual).count()
        
        # Convertir a lista ordenada por hora para el template
        slots_ordenados = sorted(slots_por_hora.items(), key=lambda x: x[0])
        
        context.update({
            'complejo': complejo,
            'hoy': hoy,
            'slots_por_hora': dict(slots_ordenados),
            'slots_ordenados': slots_ordenados,  # Lista ordenada para iterar fácilmente
            'total_disponibles': total_disponibles,
            'creditos_disponibles': creditos_disponibles,
            'turnos_cliente': turnos_cliente,
            'turnos_mes': turnos_mes,
        })
    
    # Si es staff, obtener turnos del complejo y calcular disponibles
    if user.es_staff_complejo and user.complejo:
        hoy = timezone.now().date()
        complejo = user.complejo
        
        # Obtener todos los turnos del complejo (excepto cancelados/expirados)
        turnos_complejo = Turno.objects.filter(
            cancha__complejo=complejo
        ).exclude(
            estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
        ).order_by('fecha', 'hora_inicio')
        
        # Estadísticas
        turnos_hoy = turnos_complejo.filter(fecha=hoy).count()
        pendientes_pago = turnos_complejo.filter(estado=Turno.Estado.PENDIENTE_PAGO).count()
        confirmados = turnos_complejo.filter(estado=Turno.Estado.CONFIRMADO).count()
        cancelados = Turno.objects.filter(
            cancha__complejo=complejo,
            estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN]
        ).count()
        
        # Calcular turnos disponibles del día (similar a cliente)
        canchas = Cancha.objects.filter(complejo=complejo, activa=True)
        turnos_ocupados = Turno.objects.filter(
            cancha__complejo=complejo,
            fecha=hoy
        ).exclude(
            estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
        ).values_list('cancha_id', 'hora_inicio')
        ocupados_set = set(turnos_ocupados)
        bloqueos = Bloqueo.objects.filter(complejo=complejo, fecha=hoy)
        
        # Generar slots disponibles agrupados por hora
        slots_por_hora_staff = {}
        hora_apertura = complejo.hora_apertura
        hora_cierre = complejo.hora_cierre
        ahora = timezone.now()
        hoy_actual = ahora.date()
        hora_actual = hora_apertura
        
        while hora_actual < hora_cierre:
            # Si es hoy, verificar que el turno no haya empezado ya
            if hoy == hoy_actual:
                # Crear datetime del inicio del turno
                inicio_turno = timezone.make_aware(datetime.combine(hoy, hora_actual))
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
                slots_por_hora_staff[hora_actual] = {
                    'hora_inicio': hora_actual,
                    'hora_fin': hora_fin,
                    'canchas': canchas_disponibles,
                }
            
            hora_actual = (datetime.combine(datetime.today(), hora_actual) + timedelta(hours=1)).time()
        
        slots_ordenados_staff = sorted(slots_por_hora_staff.items(), key=lambda x: x[0])
        
        context.update({
            'complejo': complejo,
            'hoy': hoy,
            'turnos_complejo': turnos_complejo,
            'turnos_hoy': turnos_hoy,
            'pendientes_pago': pendientes_pago,
            'confirmados': confirmados,
            'cancelados': cancelados,
            'slots_ordenados_staff': slots_ordenados_staff,
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
    
    # Calcular créditos disponibles
    creditos_totales = CreditoCliente.objects.filter(
        usuario=request.user,
        complejo=cancha.complejo,
        activo=True
    ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    
    creditos_usados = CreditoCliente.objects.filter(
        usuario=request.user,
        complejo=cancha.complejo,
        activo=True
    ).aggregate(total=Sum('monto_usado'))['total'] or Decimal('0.00')
    
    creditos_disponibles = creditos_totales - creditos_usados
    
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
    
    # Verificar que el turno no sea en el pasado
    # timezone.now() ya usa el timezone configurado en settings (America/Argentina/Buenos_Aires)
    ahora = timezone.now()
    # make_aware usa el timezone activo de Django (configurado en TIME_ZONE)
    fecha_hora_turno = timezone.make_aware(datetime.combine(fecha_obj, hora_obj))
    if fecha_hora_turno < ahora:
        messages.error(request, 'No se puede reservar un turno en el pasado')
        return redirect('dashboard')
    
    # Verificar que el turno no esté ocupado
    turno_existente = Turno.objects.filter(
        cancha=cancha,
        fecha=fecha_obj,
        hora_inicio=hora_obj
    ).exclude(
        estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
    ).first()
    
    if turno_existente:
        messages.error(request, 'Este turno ya está reservado')
        return redirect('dashboard')
    
    # Verificar bloqueos
    bloqueos = Bloqueo.objects.filter(
        complejo=cancha.complejo,
        fecha=fecha_obj
    )
    
    for bloqueo in bloqueos:
        if bloqueo.cancha is None or bloqueo.cancha == cancha:
            if bloqueo.es_dia_completo:
                messages.error(request, 'Este día está bloqueado')
                return redirect('dashboard')
            elif bloqueo.hora_inicio and bloqueo.hora_fin:
                if bloqueo.hora_inicio <= hora_obj < bloqueo.hora_fin:
                    messages.error(request, 'Este horario está bloqueado')
                    return redirect('dashboard')
    
    # Calcular créditos disponibles
    creditos_totales = CreditoCliente.objects.filter(
        usuario=request.user,
        complejo=cancha.complejo,
        activo=True
    ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    
    creditos_usados = CreditoCliente.objects.filter(
        usuario=request.user,
        complejo=cancha.complejo,
        activo=True
    ).aggregate(total=Sum('monto_usado'))['total'] or Decimal('0.00')
    
    creditos_disponibles = creditos_totales - creditos_usados
    senia_requerida = cancha.precio_senia
    
    # Verificar si tiene créditos suficientes
    if creditos_disponibles < senia_requerida:
        messages.error(request, f'No tenés créditos suficientes. Necesitás ${senia_requerida}, tenés ${creditos_disponibles}')
        return redirect('dashboard')
    
    # Usar créditos disponibles
    creditos_a_usar = min(creditos_disponibles, senia_requerida)
    creditos_restantes = senia_requerida - creditos_a_usar
    
    # Obtener créditos activos ordenados por fecha (más antiguos primero)
    creditos_activos = CreditoCliente.objects.filter(
        usuario=request.user,
        complejo=cancha.complejo,
        activo=True
    ).order_by('created_at')
    
    # Aplicar créditos
    creditos_aplicados = Decimal('0.00')
    for credito in creditos_activos:
        if creditos_aplicados >= creditos_a_usar:
            break
        
        saldo_credito = credito.saldo_disponible
        if saldo_credito > 0:
            monto_a_usar = min(saldo_credito, creditos_a_usar - creditos_aplicados)
            credito.monto_usado += monto_a_usar
            credito.save()
            creditos_aplicados += monto_a_usar
    
    # Crear el turno
    turno = Turno.objects.create(
        cancha=cancha,
        cliente=request.user,
        fecha=fecha_obj,
        hora_inicio=hora_obj,
        estado=Turno.Estado.CONFIRMADO,
        precio_total=cancha.precio_hora,
        senia_requerida=senia_requerida,
        senia_pagada=creditos_a_usar,
        creditos_usados=creditos_a_usar,
    )
    
    messages.success(request, f'¡Turno reservado exitosamente! {cancha.nombre} - {fecha_obj} {hora_obj.strftime("%H:%M")}')
    return redirect('dashboard')


@login_required
def cancelar_turno(request, turno_id):
    """Cancelar un turno del cliente."""
    if not request.user.es_cliente:
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    turno = get_object_or_404(Turno, id=turno_id)
    
    # Verificar que el turno pertenece al cliente
    if turno.cliente != request.user:
        messages.error(request, 'No podés cancelar turnos de otros usuarios')
        return redirect('dashboard')
    
    # Verificar que no esté ya cancelado
    if turno.fue_cancelado:
        messages.error(request, 'Este turno ya está cancelado')
        return redirect('dashboard')
    
    # Cancelar el turno
    turno.estado = Turno.Estado.CANCELADO_USUARIO
    turno.save()
    
    # Generar crédito para el cliente (si pagó seña)
    if turno.senia_pagada > 0:
        CreditoCliente.objects.create(
            usuario=request.user,
            complejo=turno.cancha.complejo,
            monto=turno.senia_pagada,
            motivo=f'Cancelación turno {turno.cancha.nombre} - {turno.fecha} {turno.hora_inicio.strftime("%H:%M")}',
            turno_origen=turno,
        )
    
    messages.success(request, f'Turno cancelado. Se te acreditó ${turno.senia_pagada} en créditos.')
    return redirect('dashboard')


@login_required
def cancelar_turno_staff(request, turno_id):
    """Cancelar un turno (Staff/Admin)."""
    if not (request.user.es_staff_complejo or request.user.es_admin or request.user.es_superadmin):
        messages.error(request, 'No autorizado')
        return redirect('dashboard')
    
    turno = get_object_or_404(Turno, id=turno_id)
    
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
    turno.save()
    
    # Generar crédito para el cliente (si pagó seña)
    if turno.senia_pagada > 0:
        CreditoCliente.objects.create(
            usuario=turno.cliente,
            complejo=turno.cancha.complejo,
            monto=turno.senia_pagada,
            motivo=f'Cancelación por staff - Turno {turno.cancha.nombre} - {turno.fecha} {turno.hora_inicio.strftime("%H:%M")}',
            turno_origen=turno,
        )
    
    messages.success(request, f'Turno cancelado. Se acreditó ${turno.senia_pagada} en créditos al cliente.')
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
    
    # Calcular turnos disponibles (misma lógica que en dashboard)
    canchas = Cancha.objects.filter(complejo=complejo, activa=True)
    turnos_ocupados = Turno.objects.filter(
        cancha__complejo=complejo,
        fecha=hoy
    ).exclude(
        estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
    ).values_list('cancha_id', 'hora_inicio')
    ocupados_set = set(turnos_ocupados)
    bloqueos = Bloqueo.objects.filter(complejo=complejo, fecha=hoy)
    
    slots_por_hora = {}
    hora_apertura = complejo.hora_apertura
    hora_cierre = complejo.hora_cierre
    ahora = timezone.now()
    hoy_actual = ahora.date()
    hora_actual = hora_apertura
    
    while hora_actual < hora_cierre:
        # Si es hoy, verificar que el turno no haya empezado ya
        if hoy == hoy_actual:
            # Crear datetime del inicio del turno
            inicio_turno = timezone.make_aware(datetime.combine(hoy, hora_actual))
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
    
    if not all([cancha_id, fecha, hora, nombre_cliente]):
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
    
    # Verificar que el turno no esté ocupado
    turno_existente = Turno.objects.filter(
        cancha=cancha,
        fecha=fecha_obj,
        hora_inicio=hora_obj
    ).exclude(
        estado__in=[Turno.Estado.CANCELADO_USUARIO, Turno.Estado.CANCELADO_ADMIN, Turno.Estado.EXPIRADO]
    ).first()
    
    if turno_existente:
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
        }
    )
    
    if not created:
        # Si ya existe, actualizar el nombre por si cambió
        cliente.first_name = nombre_cliente
        cliente.complejo = cancha.complejo
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
    
    messages.success(request, f'Turno creado para {nombre_cliente} - {cancha.nombre} - {fecha_obj} {hora_obj.strftime("%H:%M")}')
    return redirect('dashboard')
