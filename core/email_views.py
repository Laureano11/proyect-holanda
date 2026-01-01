"""
Vistas personalizadas para manejo de emails con mejor error handling.
"""
from django.contrib.auth.views import PasswordResetView
from django.contrib import messages
from django.shortcuts import redirect
from django.http import HttpResponseRedirect
from django.urls import reverse
import logging
import threading
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.template import loader
from django.core.mail import EmailMultiAlternatives
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger(__name__)


def send_email_async(subject, email_template_name, context, from_email, to_email, html_email_template_name=None):
    """
    Envía email en un thread separado para no bloquear la request.
    """
    def _send():
        try:
            body = loader.render_to_string(email_template_name, context)
            email_message = EmailMultiAlternatives(subject, body, from_email, [to_email])
            if html_email_template_name is not None:
                html_email = loader.render_to_string(html_email_template_name, context)
                email_message.attach_alternative(html_email, 'text/html')
            email_message.send(fail_silently=False)
            logger.info(f"Email enviado exitosamente a {to_email}")
        except Exception as e:
            logger.error(f"Error al enviar email a {to_email}: {str(e)}")
    
    # Enviar en thread separado
    thread = threading.Thread(target=_send)
    thread.daemon = True
    thread.start()


class CustomPasswordResetView(PasswordResetView):
    """
    Vista personalizada de password reset con envío asíncrono de emails.
    """
    
    def form_valid(self, form):
        """
        Envía el email de forma asíncrona para no bloquear la respuesta.
        """
        opts = {
            'use_https': self.request.is_secure(),
            'token_generator': self.token_generator,
            'from_email': self.from_email,
            'email_template_name': self.email_template_name,
            'subject_template_name': self.subject_template_name,
            'request': self.request,
            'html_email_template_name': self.html_email_template_name,
            'extra_email_context': self.extra_email_context,
        }
        
        # Obtener usuarios con ese email
        email = form.cleaned_data["email"]
        active_users = form.get_users(email)
        
        for user in active_users:
            # Preparar contexto del email
            current_site = get_current_site(self.request)
            site_name = current_site.name
            domain = current_site.domain
            
            context = {
                'email': email,
                'domain': domain,
                'site_name': site_name,
                'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                'user': user,
                'token': default_token_generator.make_token(user),
                'protocol': 'https' if self.request.is_secure() else 'http',
            }
            
            if self.extra_email_context is not None:
                context.update(self.extra_email_context)
            
            # Cargar subject
            subject = loader.render_to_string(self.subject_template_name, context)
            subject = ''.join(subject.splitlines())
            
            # Enviar email de forma asíncrona
            try:
                send_email_async(
                    subject=subject,
                    email_template_name=self.email_template_name,
                    context=context,
                    from_email=self.from_email,
                    to_email=user.email,
                    html_email_template_name=self.html_email_template_name,
                )
                logger.info(f"Email de recuperación programado para {user.email}")
            except Exception as e:
                logger.error(f"Error al programar email: {str(e)}")
        
        # Redirigir inmediatamente sin esperar el email
        return HttpResponseRedirect(reverse('password_reset_done'))

