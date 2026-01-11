---
name: Multi-tenant_subdominio
overview: Preparar la app para multi-tenant por subdominio con aislamiento por complejo y control de superadmin
todos:
  - id: model-subdominio
    content: Agregar campo subdominio a Complejo y migración
    status: completed
  - id: middleware-tenant
    content: Middleware que resuelva complejo por subdominio
    status: completed
  - id: context-processor
    content: Context processor para exponer complejo_actual en templates
    status: completed
  - id: auth-aislamiento
    content: Bloquear login cruzado y setear complejo en registro
    status: completed
  - id: filtros-datos
    content: Asegurar filtros por complejo en vistas/servicios no superadmin
    status: completed
  - id: admin-filtros
    content: Filtrar admin por complejo para admin/staff
    status: completed
  - id: dns-config
    content: Doc de DNS y env (ALLOWED_HOSTS/CSRF wildcard)
    status: completed
---

# Multi-tenant por subdominio

## Estado: ✅ Implementado

Sistema multi-tenant que permite múltiples complejos en un solo deploy usando subdominios.

## Cómo funciona

### Resolución de tenant (hs.<complejo>.<tld>)

El middleware `TenantMiddleware` resuelve el complejo actual basándose en el dominio:

| Host | Comportamiento |
|------|----------------|
| `www.hs.complejo4.com` | Resuelve `Complejo.subdominio='complejo4'` |
| `hs.complejo4.com` | Resuelve `Complejo.subdominio='complejo4'` |
| `localhost:8000` | Usa complejo por defecto (primero activo / primero existente) |
| `*.ngrok-free.dev` | Usa complejo por defecto (desarrollo) |
| Host sin prefijo `hs.` o sin match | Usa complejo por defecto |

### Variables disponibles

En **templates**:
```django
{{ complejo_actual.nombre }}
{{ complejo_actual.preferencias.color_primario }}
{{ preferencias_complejo.duracion_turno_minutos }}
```

En **views**:
```python
complejo = getattr(request, 'complejo_actual', None)
```

## Aislamiento de datos

### Login
- Los usuarios no pueden loguearse desde un subdominio diferente a su complejo
- Superadmin puede loguearse desde cualquier subdominio
- Mensaje de error claro si intentan acceder desde el subdominio incorrecto

### Registro
- Los usuarios se registran automáticamente en el complejo del dominio actual (`hs.<complejo>.<tld>`)
- No hay selector de complejo (se asigna automáticamente)

### Admin Django
- Superadmin: ve todo
- Admin/Staff: solo ven datos de su complejo
- Mixin `ComplejoFilterMixin` filtra querysets automáticamente

### Vistas/Servicios
- Las vistas ya filtraban por `user.complejo`
- El middleware garantiza que el usuario solo puede loguearse en su complejo

## Configuración DNS

### Producción

1. **DNS Wildcard** - Crear registro A/CNAME:
   ```
   *.ha.com → IP del servidor / load balancer
   ```

2. **Variables de entorno** (.env):
   ```bash
   # Hosts permitidos (usar wildcard)
   ALLOWED_HOSTS=.ha.com,ha.com
   
   # CSRF trusted origins
   CSRF_TRUSTED_ORIGINS=https://*.ha.com,https://ha.com
   ```

3. **Cookies** - Cada subdominio tiene su sesión separada (comportamiento por defecto de Django).

### Desarrollo local

No requiere configuración especial:
- `localhost:8000` → usa complejo por defecto (Basanta)
- `127.0.0.1:8000` → usa complejo por defecto

Para probar subdominios localmente, agregar en `/etc/hosts`:
```
127.0.0.1   basanta.local
127.0.0.1   otro-complejo.local
```

Y actualizar `.env`:
```bash
ALLOWED_HOSTS=localhost,127.0.0.1,basanta.local,otro-complejo.local
```

### Ngrok (desarrollo remoto)

El middleware detecta automáticamente hosts de ngrok y usa el complejo por defecto:
- `*.ngrok-free.dev`
- `*.ngrok-free.app`
- `*.ngrok.io`

## Archivos modificados

| Archivo | Cambios |
|---------|---------|
| `core/models.py` | Campo `subdominio` en `Complejo` |
| `core/middleware.py` | `TenantMiddleware` + context processor |
| `core/views.py` | Login/registro con validación multi-tenant |
| `core/admin.py` | `ComplejoFilterMixin` para filtrar querysets |
| `config/settings.py` | Middleware + context processor agregados |

## Migración

```bash
python manage.py migrate core 0005_add_subdominio_field
```

El campo `subdominio` se genera automáticamente del `slug` si está vacío.

## Agregar nuevo complejo

1. Crear el complejo en el admin o shell:
   ```python
   Complejo.objects.create(
       nombre="Nuevo Complejo",
       slug="nuevo-complejo",
       subdominio="nuevo",  # → nuevo.ha.com
       direccion="...",
   )
   ```

2. (Producción) El wildcard DNS ya lo resuelve automáticamente.

3. Crear preferencias:
   ```python
   PreferenciasComplejo.objects.create(
       complejo=complejo,
       color_primario="#4F46E5",  # Personalizar colores
   )
   ```

## Testing

### Test de middleware
```python
from django.test import TestCase, RequestFactory
from core.middleware import TenantMiddleware
from core.models import Complejo

class TenantMiddlewareTest(TestCase):
    def test_resolve_subdominio(self):
        complejo = Complejo.objects.create(
            nombre="Test",
            subdominio="test"
        )
        
        factory = RequestFactory()
        request = factory.get('/', HTTP_HOST='test.ha.com')
        
        middleware = TenantMiddleware(lambda r: None)
        middleware(request)
        
        self.assertEqual(request.complejo_actual, complejo)
```

### Test de login cruzado
```python
def test_login_cruzado_bloqueado(self):
    # Usuario de complejo A intenta loguear en complejo B
    user = Usuario.objects.create_user(
        username='test',
        password='test123',
        complejo=complejo_a
    )
    
    response = self.client.post(
        '/login/',
        {'username': 'test', 'password': 'test123'},
        HTTP_HOST='complejo-b.ha.com'
    )
    
    # Debe rechazar el login
    self.assertContains(response, 'pertenece a')
```

