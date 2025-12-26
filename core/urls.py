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
]
