"""
Script para testear la conexión SMTP con Resend.
Ejecutar: python test_smtp.py
"""
import os
import sys
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.core.mail import send_mail
from django.conf import settings

print("=" * 60)
print("TEST DE CONEXIÓN SMTP - RESEND")
print("=" * 60)

print(f"\nConfiguración actual:")
print(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
print(f"EMAIL_HOST: {settings.EMAIL_HOST}")
print(f"EMAIL_PORT: {settings.EMAIL_PORT}")
print(f"EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}")
print(f"EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}")
print(f"EMAIL_HOST_PASSWORD: {'*' * 10 if settings.EMAIL_HOST_PASSWORD else 'NO CONFIGURADO'}")
print(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")

print("\n" + "=" * 60)
print("Intentando enviar email de prueba...")
print("=" * 60)

try:
    send_mail(
        subject='Test desde Django',
        message='Este es un email de prueba desde tu app Django.',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=['tu_email@ejemplo.com'],  # Cambiá esto por tu email
        fail_silently=False,
    )
    print("\n✅ EMAIL ENVIADO EXITOSAMENTE!")
    print("Revisá tu bandeja de entrada (y spam)")
except Exception as e:
    print(f"\n❌ ERROR AL ENVIAR EMAIL:")
    print(f"Tipo de error: {type(e).__name__}")
    print(f"Mensaje: {str(e)}")
    
    # Diagnóstico adicional
    if "Authentication" in str(e):
        print("\n🔍 Diagnóstico: Problema de autenticación")
        print("   - Verificá que EMAIL_HOST_PASSWORD sea correcta")
        print("   - Verificá que EMAIL_HOST_USER sea 'resend'")
    elif "Connection" in str(e) or "timeout" in str(e).lower():
        print("\n🔍 Diagnóstico: Problema de conexión")
        print("   - Verificá que EMAIL_HOST sea 'smtp.resend.com'")
        print("   - Verificá que EMAIL_PORT sea 587")
        print("   - Render puede estar bloqueando el puerto 587")
    else:
        print("\n🔍 Diagnóstico: Error desconocido")
        print("   - Revisá los logs completos arriba")

print("\n" + "=" * 60)

