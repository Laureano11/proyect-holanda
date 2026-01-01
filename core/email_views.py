"""
Vistas personalizadas para manejo de emails con mejor error handling.
"""
from django.contrib.auth.views import PasswordResetView
from django.contrib import messages
from django.shortcuts import redirect
import logging

logger = logging.getLogger(__name__)


class CustomPasswordResetView(PasswordResetView):
    """
    Vista personalizada de password reset con manejo de errores SMTP.
    """
    
    def form_valid(self, form):
        """
        Intenta enviar el email y captura errores de SMTP.
        """
        try:
            # Intentar enviar el email
            response = super().form_valid(form)
            logger.info(f"Email de recuperación enviado exitosamente a {form.cleaned_data['email']}")
            return response
        except Exception as e:
            # Capturar cualquier error de SMTP
            logger.error(f"Error al enviar email de recuperación: {str(e)}")
            
            # Mostrar mensaje de error al usuario
            messages.error(
                self.request,
                'Hubo un problema al enviar el email. Por favor, intentá de nuevo en unos minutos '
                'o contactá al soporte si el problema persiste.'
            )
            
            # Redirigir de vuelta al formulario
            return redirect('password_reset')

