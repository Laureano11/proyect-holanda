"""
URLs de la aplicación core.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('turnos-publicos/', views.turnos_publicos, name='turnos_publicos'),

    # Ops / diagnóstico (solo superadmin + token)
    path('_ops/health/', views.ops_health, name='ops_health'),
    
    # Auth
    path('login/', views.login_view, name='login'),
    path('registro/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('perfil/actualizar/', views.actualizar_perfil, name='actualizar_perfil'),
    path('perfil/darse-de-baja/', views.darse_de_baja, name='darse_de_baja'),
    
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Reservas
    path('reservar/modal/<int:cancha_id>/', views.modal_reservar, name='modal_reservar'),
    path('reservar/', views.reservar_turno, name='reservar_turno'),
    
    # Cancelar turno
    path('cancelar/<int:turno_id>/', views.cancelar_turno, name='cancelar_turno'),
    path('cancelar-staff/<int:turno_id>/', views.cancelar_turno_staff, name='cancelar_turno_staff'),
    
    # Turno rápido (Staff)
    path('nuevo-turno-rapido/', views.nuevo_turno_rapido, name='nuevo_turno_rapido'),
    path('crear-turno-rapido/', views.crear_turno_rapido, name='crear_turno_rapido'),
    
    # Turnos fijos (Staff)
    path('turnos-fijos/', views.turnos_fijos, name='turnos_fijos'),
    path('crear-turno-fijo/', views.crear_turno_fijo, name='crear_turno_fijo'),
    path('confirmar-turno-fijo/', views.confirmar_turno_fijo, name='confirmar_turno_fijo'),
    path('eliminar-turno-fijo/<int:turno_fijo_id>/', views.eliminar_turno_fijo, name='eliminar_turno_fijo'),
    path('generar-turnos-desde-fijos/', views.generar_turnos_desde_fijos, name='generar_turnos_desde_fijos'),
    
    # Bloqueos (Staff/Admin)
    path('bloqueos/', views.bloqueos, name='bloqueos'),
    path('crear-bloqueo/', views.crear_bloqueo, name='crear_bloqueo'),
    path('eliminar-bloqueo/<int:bloqueo_id>/', views.eliminar_bloqueo, name='eliminar_bloqueo'),
    
    # Gestión de turnos (Staff)
    path('marcar-pagado/<int:turno_id>/', views.marcar_turno_pagado, name='marcar_turno_pagado'),
    path('editar-turno/<int:turno_id>/', views.editar_turno, name='editar_turno'),
    path('actualizar-turno/<int:turno_id>/', views.actualizar_turno, name='actualizar_turno'),
    path('turnos-en-vivo/', views.turnos_en_vivo, name='turnos_en_vivo'),
    
    # Cliente - Secciones
    path('turnos-actuales/', views.turnos_actuales, name='turnos_actuales'),
    path('historial/', views.historial_turnos, name='historial_turnos'),
    path('mi-perfil/', views.mi_perfil, name='mi_perfil'),
]
