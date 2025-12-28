"""
Configuración del panel de administración de Django.

Multi-tenant: Los usuarios admin/staff solo ven datos de su complejo.
Superadmin puede ver todo.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    Usuario,
    Complejo,
    PreferenciasComplejo,
    CaracteristicaCancha,
    Cancha,
    Bloqueo,
    Turno,
    TurnoFijo,
    CreditoCliente,
    IntegracionMercadoPago,
)


class ComplejoFilterMixin:
    """
    Mixin para filtrar querysets por complejo del usuario logueado.
    
    - Superadmin: ve todo
    - Admin/Staff: solo ve datos de su complejo
    """
    
    # Nombre del campo FK a Complejo (por defecto 'complejo')
    complejo_field = 'complejo'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        # Superadmin ve todo
        if request.user.is_superuser or request.user.es_superadmin:
            return qs
        
        # Admin/Staff filtra por su complejo
        if request.user.complejo:
            filter_kwargs = {self.complejo_field: request.user.complejo}
            return qs.filter(**filter_kwargs)
        
        # Sin complejo asignado no ve nada
        return qs.none()
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filtrar opciones de FK por complejo del usuario."""
        # Superadmin ve todo
        if request.user.is_superuser or request.user.es_superadmin:
            return super().formfield_for_foreignkey(db_field, request, **kwargs)
        
        # Filtrar opciones de Complejo
        if db_field.name == 'complejo' and request.user.complejo:
            kwargs['queryset'] = Complejo.objects.filter(id=request.user.complejo.id)
        
        # Filtrar canchas por complejo
        if db_field.name == 'cancha' and request.user.complejo:
            kwargs['queryset'] = Cancha.objects.filter(complejo=request.user.complejo)
        
        # Filtrar usuarios por complejo
        if db_field.name in ['cliente', 'usuario', 'created_by'] and request.user.complejo:
            kwargs['queryset'] = Usuario.objects.filter(complejo=request.user.complejo)
        
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Usuario)
class UsuarioAdmin(ComplejoFilterMixin, UserAdmin):
    """Admin personalizado para Usuario con filtrado por complejo."""
    
    list_display = ['username', 'email', 'first_name', 'last_name', 'rol', 'complejo', 'celular', 'is_active']
    list_filter = ['rol', 'complejo', 'is_active', 'is_staff']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'dni', 'celular']
    ordering = ['username']
    
    fieldsets = UserAdmin.fieldsets + (
        ('Información adicional', {
            'fields': ('rol', 'complejo', 'dni', 'celular', 'direccion')
        }),
    )
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Información adicional', {
            'fields': ('rol', 'complejo', 'dni', 'celular', 'direccion')
        }),
    )
    
    def get_queryset(self, request):
        qs = super(UserAdmin, self).get_queryset(request)
        
        # Superadmin ve todo
        if request.user.is_superuser or request.user.es_superadmin:
            return qs
        
        # Admin/Staff filtra por su complejo
        if request.user.complejo:
            return qs.filter(complejo=request.user.complejo)
        
        return qs.none()


class PreferenciasComplejoInline(admin.StackedInline):
    """Inline para preferencias dentro del complejo."""
    model = PreferenciasComplejo
    can_delete = False


class IntegracionMercadoPagoInline(admin.StackedInline):
    """Inline para integración de Mercado Pago dentro del complejo."""
    model = IntegracionMercadoPago
    can_delete = False
    classes = ['collapse']


class CanchaInline(admin.TabularInline):
    """Inline para canchas dentro del complejo."""
    model = Cancha
    extra = 0
    fields = ['nombre', 'precio_hora', 'capacidad', 'duracion_turno_minutos', 'activa']


@admin.register(Complejo)
class ComplejoAdmin(admin.ModelAdmin):
    """Admin para Complejo con filtrado por usuario."""
    
    list_display = ['nombre', 'slug', 'subdominio', 'direccion', 'telefono', 'hora_apertura', 'hora_cierre', 'activo']
    list_filter = ['activo']
    search_fields = ['nombre', 'slug', 'subdominio', 'direccion']
    prepopulated_fields = {'slug': ('nombre',)}
    ordering = ['nombre']
    
    inlines = [PreferenciasComplejoInline, IntegracionMercadoPagoInline, CanchaInline]
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        # Superadmin ve todo
        if request.user.is_superuser or request.user.es_superadmin:
            return qs
        
        # Admin/Staff solo ve su complejo
        if request.user.complejo:
            return qs.filter(id=request.user.complejo.id)
        
        return qs.none()


@admin.register(PreferenciasComplejo)
class PreferenciasComplejoAdmin(ComplejoFilterMixin, admin.ModelAdmin):
    """Admin para PreferenciasComplejo."""
    
    list_display = ['complejo', 'duracion_turno_minutos', 'sistema_ranking', 'pago_senia', 'turnos_fijos_habilitados']
    list_filter = ['sistema_ranking', 'pago_senia', 'turnos_fijos_habilitados']
    
    fieldsets = (
        ('Complejo', {
            'fields': ('complejo',)
        }),
        ('Configuración Visual', {
            'fields': ('color_primario', 'color_secundario', 'color_fondo'),
            'classes': ('collapse',)
        }),
        ('Features', {
            'fields': ('sistema_ranking', 'pago_senia', 'turnos_fijos_habilitados', 
                      'cancelacion_online', 'notificaciones_whatsapp', 'notificaciones_email')
        }),
        ('Configuración de Reservas', {
            'fields': ('duracion_turno_minutos', 'tiempo_minimo_cancelacion', 
                      'tiempo_maximo_reserva', 'minutos_expiracion_pago')
        }),
    )


@admin.register(CaracteristicaCancha)
class CaracteristicaCanchaAdmin(admin.ModelAdmin):
    """Admin para CaracteristicaCancha (global, no filtrado)."""
    
    list_display = ['nombre', 'icono']
    search_fields = ['nombre']


@admin.register(Cancha)
class CanchaAdmin(ComplejoFilterMixin, admin.ModelAdmin):
    """Admin para Cancha con filtrado por complejo."""
    
    list_display = ['nombre', 'complejo', 'precio_hora', 'capacidad', 'duracion_turno_minutos', 'activa']
    list_filter = ['complejo', 'activa', 'caracteristicas']
    search_fields = ['nombre', 'complejo__nombre']
    filter_horizontal = ['caracteristicas']


@admin.register(Bloqueo)
class BloqueoAdmin(ComplejoFilterMixin, admin.ModelAdmin):
    """Admin para Bloqueo con filtrado por complejo."""
    
    list_display = ['complejo', 'cancha', 'fecha', 'hora_inicio', 'hora_fin', 'motivo', 'created_by']
    list_filter = ['complejo', 'fecha', 'motivo']
    search_fields = ['complejo__nombre', 'cancha__nombre', 'motivo']
    date_hierarchy = 'fecha'
    ordering = ['-fecha']
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Turno)
class TurnoAdmin(ComplejoFilterMixin, admin.ModelAdmin):
    """Admin para Turno con filtrado por complejo."""
    
    # Campo FK es a través de cancha
    complejo_field = 'cancha__complejo'
    
    list_display = ['cancha', 'cliente', 'fecha', 'hora_inicio', 'duracion_minutos', 'estado', 'precio_total', 'senia_pagada']
    list_filter = ['estado', 'cancha__complejo', 'fecha']
    search_fields = ['cliente__username', 'cliente__first_name', 'cliente__last_name', 'cancha__nombre']
    date_hierarchy = 'fecha'
    ordering = ['-fecha', 'hora_inicio']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Reserva', {
            'fields': ('cancha', 'cliente', 'fecha', 'hora_inicio', 'duracion_minutos', 'estado')
        }),
        ('Pago', {
            'fields': ('precio_total', 'senia_requerida', 'senia_pagada', 'creditos_usados', 'pago_referencia')
        }),
        ('Expiración', {
            'fields': ('expira_en',),
            'classes': ('collapse',)
        }),
        ('Notas', {
            'fields': ('notas',),
            'classes': ('collapse',)
        }),
        ('Auditoría', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TurnoFijo)
class TurnoFijoAdmin(ComplejoFilterMixin, admin.ModelAdmin):
    """Admin para TurnoFijo con filtrado por complejo."""
    
    # Campo FK es a través de cancha
    complejo_field = 'cancha__complejo'
    
    list_display = ['cancha', 'cliente', 'dia_semana', 'hora_inicio', 'fecha_inicio', 'fecha_fin', 'activo']
    list_filter = ['activo', 'dia_semana', 'cancha__complejo']
    search_fields = ['cliente__username', 'cliente__first_name', 'cancha__nombre']
    ordering = ['dia_semana', 'hora_inicio']


@admin.register(CreditoCliente)
class CreditoClienteAdmin(ComplejoFilterMixin, admin.ModelAdmin):
    """Admin para CreditoCliente con filtrado por complejo."""
    
    list_display = ['usuario', 'complejo', 'monto', 'monto_usado', 'saldo_disponible', 'activo', 'created_at']
    list_filter = ['complejo', 'activo']
    search_fields = ['usuario__username', 'usuario__first_name', 'motivo']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    
    def saldo_disponible(self, obj):
        return f"${obj.saldo_disponible}"
    saldo_disponible.short_description = 'Saldo disponible'


@admin.register(IntegracionMercadoPago)
class IntegracionMercadoPagoAdmin(ComplejoFilterMixin, admin.ModelAdmin):
    """Admin para IntegracionMercadoPago con filtrado por complejo."""
    
    list_display = ['complejo', 'modo', 'activo', 'updated_at']
    list_filter = ['modo', 'activo']
    search_fields = ['complejo__nombre']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Complejo', {
            'fields': ('complejo',)
        }),
        ('Credenciales', {
            'fields': ('access_token', 'public_key', 'webhook_secret'),
            'description': 'Nunca compartas estas credenciales. Obtenerlas desde el panel de Mercado Pago.'
        }),
        ('Configuración', {
            'fields': ('modo', 'activo')
        }),
        ('Auditoría', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
