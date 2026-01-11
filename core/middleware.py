"""
Middleware para multi-tenant por subdominio.
Resuelve el complejo actual basado en el subdominio del request.
Optimizado con caché para reducir queries a la base de datos.
"""

from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect
from django.core.cache import cache


class TenantMiddleware:
   
    # Hosts de desarrollo que usan complejo por defecto
    HOSTS_DESARROLLO_DEFAULT = [
        'localhost',
        '127.0.0.1',
        'testserver',  # Para tests de Django
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        
        from core.models import Complejo
        
        request.complejo_actual = None
        
        # Obtener host sin puerto
        host = request.get_host().split(':')[0].lower()
        
        # Rutas que no requieren resolución de tenant
        rutas_excluidas = [
            '/admin/',
            '/static/',
            '/media/',
            '/__debug__/',
        ]
        
        for ruta in rutas_excluidas:
            if request.path.startswith(ruta):
                response = self.get_response(request)
                return response
        
        # Detectar host .local para desarrollo (ej: padel-point.local)
        # Estos hosts usan el nombre antes del .local como slug del complejo
        if host.endswith('.local'):
            slug = host.rsplit('.local', 1)[0]  # padel-point.local → padel-point
            request.complejo_actual = self._get_complejo_por_slug(slug)
            response = self.get_response(request)
            return response
        
        # En desarrollo (localhost/127.0.0.1), usar complejo por defecto
        if host in self.HOSTS_DESARROLLO_DEFAULT or self._es_host_ngrok(host):
            request.complejo_actual = self._get_complejo_default()
            response = self.get_response(request)
            return response
        
        # Extraer tenant key siguiendo la regla hs.<complejo>.<tld>
        # Ejemplo: www.hs.complejo4.com → tenant_key = 'complejo4'
        tenant_key = self._extraer_tenant_key(host)
        
        if tenant_key:
            # Intentar obtener del caché primero (evita query a DB)
            cache_key = f'complejo_subdominio_{tenant_key.lower()}'
            complejo = cache.get(cache_key)
            
            if complejo is None:
                try:
                    complejo = Complejo.objects.select_related('preferencias').get(
                        subdominio__iexact=tenant_key,
                        activo=True
                    )
                    # Cachear por 1 hora (3600 segundos)
                    cache.set(cache_key, complejo, 3600)
                except Complejo.DoesNotExist:
                    # Si no existe el subdominio, usar fallback
                    complejo = self._get_complejo_default()
            
            request.complejo_actual = complejo
        else:
            # Host sin subdominio (ej: ha.com) → usar default
            request.complejo_actual = self._get_complejo_default()
        
        response = self.get_response(request)
        return response
    
    def _extraer_tenant_key(self, host):
        """
        Extrae la clave de tenant usando la convención hs.<complejo>.<tld>.
        - www.hs.complejo4.com → 'complejo4'
        - hs.complejo4.com → 'complejo4'
        - otros hosts → None (usa default)
        """
        # Quitar www. inicial si existe
        if host.startswith('www.'):
            host = host[4:]
        
        partes = host.split('.')
        # Necesitamos al menos: hs, <complejo>, <tld>
        if len(partes) < 3:
            return None
        
        if partes[0] != 'hs':
            return None
        
        # La etiqueta siguiente a hs es el identificador del complejo
        return partes[1] or None
    
    def _es_host_ngrok(self, host):
        """Detecta si es un host de ngrok para desarrollo."""
        ngrok_suffixes = [
            '.ngrok-free.dev',
            '.ngrok-free.app',
            '.ngrok.io',
        ]
        return any(host.endswith(suffix) for suffix in ngrok_suffixes)
    
    def _get_complejo_por_slug(self, slug):
        """
        Busca un complejo por slug o subdominio.
        Útil para hosts .local en desarrollo (ej: padel-point.local)
        Optimizado con caché.
        """
        from core.models import Complejo
        
        # Intentar obtener del caché primero
        cache_key = f'complejo_slug_{slug.lower()}'
        complejo = cache.get(cache_key)
        
        if complejo is not None:
            return complejo
        
        # Intentar buscar por slug primero, luego por subdominio
        try:
            complejo = Complejo.objects.select_related('preferencias').get(
                slug__iexact=slug, activo=True
            )
            cache.set(cache_key, complejo, 3600)
            return complejo
        except Complejo.DoesNotExist:
            pass
        
        try:
            complejo = Complejo.objects.select_related('preferencias').get(
                subdominio__iexact=slug, activo=True
            )
            cache.set(cache_key, complejo, 3600)
            return complejo
        except Complejo.DoesNotExist:
            pass
        
        # Si no existe, retornar None (el context processor lo manejará)
        return None
    
    def _get_complejo_default(self):
        """
        Retorna el complejo por defecto para desarrollo/fallback.
        Primero intenta un complejo activo; si no hay activos, toma el primero existente.
        Optimizado con caché.
        """
        from core.models import Complejo
        
        # Intentar obtener del caché primero
        cache_key = 'complejo_default'
        complejo = cache.get(cache_key)
        
        if complejo is not None:
            return complejo
        
        # Intentar primero 'basanta' (el complejo principal actual)
        try:
            complejo = Complejo.objects.select_related('preferencias').get(
                slug__iexact='basanta', activo=True
            )
            cache.set(cache_key, complejo, 3600)
            return complejo
        except Complejo.DoesNotExist:
            pass
        
        # Fallback: primer complejo activo
        complejo = Complejo.objects.select_related('preferencias').filter(
            activo=True
        ).first()
        
        # Si no hay activos, tomar el primero que exista
        if complejo is None:
            complejo = Complejo.objects.select_related('preferencias').first()
        
        if complejo:
            cache.set(cache_key, complejo, 3600)
        
        return complejo


def complejo_context_processor(request):
    """
    Context processor que expone el complejo actual en todos los templates.
    
    En templates:
    - {{ complejo_actual }} → Objeto Complejo
    - {{ complejo_actual.nombre }} → "Basanta Pádel"
    - {{ complejo_actual.preferencias.color_primario }} → "#3B82F6"
    """
    complejo = getattr(request, 'complejo_actual', None)
    
    # Fallback: si no hay complejo resuelto por dominio (ej. dominio genérico),
    # tomar el complejo por defecto para que siempre haya branding y preferencias.
    if complejo is None:
        from core.models import Complejo
        try:
            complejo = Complejo.objects.get(slug__iexact='basanta', activo=True)
        except Complejo.DoesNotExist:
            complejo = Complejo.objects.filter(activo=True).first()
        
        # También exponerlo en request para el resto del ciclo de vida
        if complejo:
            setattr(request, 'complejo_actual', complejo)
    
    context = {
        'complejo_actual': complejo,
    }
    
    # Agregar preferencias si existen
    if complejo:
        try:
            context['preferencias_complejo'] = complejo.preferencias
        except Exception:
            context['preferencias_complejo'] = None
    
    return context
