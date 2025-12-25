"""
Views de la aplicación core.
"""

from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Usuario, Complejo


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
    
    # Redirigir según rol
    if user.es_superadmin:
        return render(request, 'dashboard/superadmin.html', context)
    elif user.es_admin:
        return render(request, 'dashboard/admin.html', context)
    elif user.es_staff_complejo:
        return render(request, 'dashboard/staff.html', context)
    else:
        return render(request, 'dashboard/cliente.html', context)
