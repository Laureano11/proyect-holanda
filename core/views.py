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
        
        # Generar horas desde apertura hasta cierre (cada hora)
        hora_actual = hora_apertura
        while hora_actual < hora_cierre:
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
        
        # Convertir a lista ordenada por hora para el template
        slots_ordenados = sorted(slots_por_hora.items(), key=lambda x: x[0])
        
        context.update({
            'complejo': complejo,
            'hoy': hoy,
            'slots_por_hora': dict(slots_ordenados),
            'slots_ordenados': slots_ordenados,  # Lista ordenada para iterar fácilmente
            'total_disponibles': total_disponibles,
            'creditos_disponibles': creditos_disponibles,
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
