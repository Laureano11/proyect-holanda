"""
Middleware para multi-tenant por subdominio.
Resuelve el complejo actual basado en el subdominio del request.
Optimizado con caché para reducir queries a la base de datos.
"""

from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect
from django.core.cache import cache


class CanonicalHostMiddleware:
    """
    Canonicaliza el host para evitar comportamientos inconsistentes de cookies de sesión
    cuando el usuario entra con `www.` y vuelve desde terceros (Mercado Pago, etc.).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host()
        # Solo normalizamos `www.` (no tocar subdominios de tenant).
        if host.lower().startswith("www."):
            canonical_host = host[4:]
            scheme = "https" if request.is_secure() else "http"
            return redirect(f"{scheme}://{canonical_host}{request.get_full_path()}", permanent=False)
        return self.get_response(request)


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
        
        # En hosts "default" (p.ej. onrender) o desarrollo (localhost/127.0.0.1), usar complejo por defecto
        if self._es_host_default(host) or host in self.HOSTS_DESARROLLO_DEFAULT or self._es_host_ngrok(host):
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
        Extrae la clave de tenant desde el host, soportando dos convenciones:

        1) Dominio base configurable (recomendado):
           - www.nombrecomplejo.hasselt.com → 'nombrecomplejo'
           - nombrecomplejo.hasselt.com → 'nombrecomplejo'
           - hasselt.com → None (usa default)

           Controlado por `settings.TENANT_BASE_DOMAINS` (lista), por ejemplo:
           TENANT_BASE_DOMAINS = ["hasselt.com"]

        2) Convención legacy (compatibilidad):
           - www.hs.complejo4.com → 'complejo4'
           - hs.complejo4.com → 'complejo4'
        """
        # Normalización
        host = (host or "").strip().lower().rstrip(".")
        if not host:
            return None

        # Quitar www. inicial si existe (solo canonicalización semántica, no de subdominios)
        if host.startswith("www."):
            host = host[4:]

        # 1) Dominio base configurable: <tenant>.<base_domain>
        base_domains = getattr(settings, "TENANT_BASE_DOMAINS", None)
        if isinstance(base_domains, str):
            base_domains = [base_domains]
        if not base_domains:
            # Compatibilidad: default "hasselt.com" si no se define nada.
            base_domains = ["hasselt.com"]

        for base in base_domains:
            if not base:
                continue
            base = base.strip().lower().rstrip(".")
            if not base:
                continue

            if host == base:
                return None

            suffix = "." + base
            if host.endswith(suffix):
                # Prefijo: todo lo que está antes de ".<base>"
                prefix = host[: -len(suffix)]
                if not prefix:
                    return None

                # Si queda algo como "www.tenant" (por host original raro), quitar www.
                if prefix.startswith("www."):
                    prefix = prefix[4:]
                if not prefix:
                    return None

                # Tomar el label más cercano al dominio base (tenant.<base>)
                return prefix.split(".")[-1] or None
        
        # 2) Legacy: hs.<tenant>.<tld>
        partes = host.split(".")
        if len(partes) >= 3 and partes[0] == "hs":
            return partes[1] or None

        return None
    
    def _es_host_ngrok(self, host):
        """Detecta si es un host de ngrok para desarrollo."""
        ngrok_suffixes = [
            '.ngrok-free.dev',
            '.ngrok-free.app',
            '.ngrok.io',
        ]
        return any(host.endswith(suffix) for suffix in ngrok_suffixes)

    def _es_host_default(self, host: str) -> bool:
        """
        Hosts que deben mapear siempre al complejo default (sin resolver tenant).
        Útil para entornos sin dominios configurados (p.ej. onrender).
        Configurable via settings.TENANT_DEFAULT_HOSTS.
        """
        host = (host or "").strip().lower().split(":", 1)[0].rstrip(".")
        if not host:
            return False
        if host.startswith("www."):
            host = host[4:]

        default_hosts = getattr(settings, "TENANT_DEFAULT_HOSTS", None)
        if isinstance(default_hosts, str):
            default_hosts = [default_hosts]
        if not default_hosts:
            return False

        normalized = []
        for h in default_hosts:
            if not h:
                continue
            hh = str(h).strip().lower().split(":", 1)[0].rstrip(".")
            if hh.startswith("www."):
                hh = hh[4:]
            if hh:
                normalized.append(hh)

        return host in set(normalized)
    
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
