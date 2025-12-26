"""
URLs de la aplicación core.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    
    # Auth
    path('login/', views.login_view, name='login'),
    path('registro/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    
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
]
