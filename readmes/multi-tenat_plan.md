---
name: Multi-tenant_subdominio
overview: Preparar la app para multi-tenant por subdominio con aislamiento por complejo y control de superadmin
todos:
  - id: model-subdominio
    content: Agregar campo subdominio a Complejo y migración
    status: pending
  - id: middleware-tenant
    content: Middleware que resuelva complejo por subdominio
    status: pending
  - id: auth-aislamiento
    content: Bloquear login cruzado y setear complejo en registro
    status: pending
  - id: filtros-datos
    content: Asegurar filtros por complejo en vistas/servicios no superadmin
    status: pending
  - id: admin-filtros
    content: Filtrar admin por complejo para admin/staff
    status: pending
  - id: tests
    content: Agregar tests para middleware/login/registro y smoke de vistas
    status: pending
  - id: dns-config
    content: Doc de DNS y env (ALLOWED_HOSTS/CSRF wildcard)
    status: pending
---

# Plan para multi-tenant por subdominio

## Objetivo

- Soportar múltiples complejos en **un solo deploy** usando **subdominios** (`complejoX.ha.com`).
- Aislar datos por complejo (solo superadmin ve todo).
- Impedir login si `user.complejo` no coincide con el subdominio actual.

## Pasos

1) **Modelo y datos**

- Agregar campo `subdominio` único a `Complejo` (slug).
- Comando/fixture para asignar subdominio a los complejos existentes.

2) **Resolución de tenant (middleware)**

- Crear middleware que tome `request.get_host()` → extraiga subdominio → cargue `Complejo` → setee `request.complejo_actual` (o 404 si no existe).
- Manejar excepciones locales (`localhost`, `127.0.0.1`) con un subdominio de desarrollo por defecto.

3) **Context processor**

- Exponer `complejo_actual` en templates para branding (colores, logo, textos).

4) **Auth y aislamiento**

- En `login_view`: después de `authenticate`, si no es superadmin y `user.complejo != request.complejo_actual`, rechazar login.
- En `register_view`: asignar siempre `user.complejo = request.complejo_actual` (rol cliente) y usar preferencias del complejo.
- En vistas/servicios críticos: asegurar filtros por `request.complejo_actual` para turnos/canchas/usuarios (no superadmin).

5) **URLs y rutas**

- Mantener rutas actuales, pero la selección de complejo se hace por **host**; no es necesario prefijar paths. Ajustar redirecciones y `reverse` si dependen del host.

6) **Admin Django**

- Superadmin: sin cambios.
- Admin/staff de un complejo: filtrar querysets por `user.complejo` en el admin para evitar ver otros complejos.

7) **Config / seguridad**

- `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS`: aceptar wildcard `*.ha.com` y entorno local.
- Cookies/sesión: no compartir dominio; dejar por defecto (cada subdominio mantiene su sesión).

8) **Tests y verificación**

- Tests de middleware: resolución correcta de subdominio y 404 si no existe.
- Tests de login/registro: bloquea cruce de complejos, permite superadmin en todos.
- Smoke test de vistas principales con `complejo_actual`.

9) **Rollout**