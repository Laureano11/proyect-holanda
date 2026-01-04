"""
URL configuration for Sistema de Gestión de Turnos.
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core.email_views import CustomPasswordResetView
from core import views as core_views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Mercado Pago - Vista de prueba aislada
    path('mercadopago/demo/', core_views.mercadopago_checkout_demo, name='mercadopago_checkout_demo'),
    path('mercadopago/feedback/', core_views.mercadopago_feedback, name='mercadopago_feedback'),
    path('mercadopago/webhook/', core_views.mercadopago_webhook, name='mercadopago_webhook'),
    
    # Password reset flow (Django built-in views con custom error handling)
    path('password-reset/', 
         CustomPasswordResetView.as_view(
             template_name='auth/password_reset.html',
             email_template_name='auth/password_reset_email.html',
             subject_template_name='auth/password_reset_subject.txt',
         ), 
         name='password_reset'),
    
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(
             template_name='auth/password_reset_done.html'
         ), 
         name='password_reset_done'),
    
    path('password-reset/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(
             template_name='auth/password_reset_confirm.html'
         ), 
         name='password_reset_confirm'),
    
    path('password-reset/complete/', 
         auth_views.PasswordResetCompleteView.as_view(
             template_name='auth/password_reset_complete.html'
         ), 
         name='password_reset_complete'),
    
    path('', include('core.urls')),
]

# Servir archivos media en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

