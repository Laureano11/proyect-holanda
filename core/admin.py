"""
Configuración del panel de administración de Django.
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


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """Admin personalizado para Usuario."""
    
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
    """Admin para Complejo."""
    
    list_display = ['nombre', 'slug', 'direccion', 'telefono', 'hora_apertura', 'hora_cierre', 'activo']
    list_filter = ['activo']
    search_fields = ['nombre', 'slug', 'direccion']
    prepopulated_fields = {'slug': ('nombre',)}
    ordering = ['nombre']
    
    inlines = [PreferenciasComplejoInline, IntegracionMercadoPagoInline, CanchaInline]


@admin.register(PreferenciasComplejo)
class PreferenciasComplejoAdmin(admin.ModelAdmin):
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
    """Admin para CaracteristicaCancha."""
    
    list_display = ['nombre', 'icono']
    search_fields = ['nombre']


@admin.register(Cancha)
class CanchaAdmin(admin.ModelAdmin):
    """Admin para Cancha."""
    
    list_display = ['nombre', 'complejo', 'precio_hora', 'capacidad', 'duracion_turno_minutos', 'activa']
    list_filter = ['complejo', 'activa', 'caracteristicas']
    search_fields = ['nombre', 'complejo__nombre']
    filter_horizontal = ['caracteristicas']


@admin.register(Bloqueo)
class BloqueoAdmin(admin.ModelAdmin):
    """Admin para Bloqueo (feriados, lluvia, mantenimiento)."""
    
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
class TurnoAdmin(admin.ModelAdmin):
    """Admin para Turno."""
    
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
class TurnoFijoAdmin(admin.ModelAdmin):
    """Admin para TurnoFijo."""
    
    list_display = ['cancha', 'cliente', 'dia_semana', 'hora_inicio', 'fecha_inicio', 'fecha_fin', 'activo']
    list_filter = ['activo', 'dia_semana', 'cancha__complejo']
    search_fields = ['cliente__username', 'cliente__first_name', 'cancha__nombre']
    ordering = ['dia_semana', 'hora_inicio']


@admin.register(CreditoCliente)
class CreditoClienteAdmin(admin.ModelAdmin):
    """Admin para CreditoCliente (sistema de reembolsos)."""
    
    list_display = ['usuario', 'complejo', 'monto', 'monto_usado', 'saldo_disponible', 'activo', 'created_at']
    list_filter = ['complejo', 'activo']
    search_fields = ['usuario__username', 'usuario__first_name', 'motivo']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    
    def saldo_disponible(self, obj):
        return f"${obj.saldo_disponible}"
    saldo_disponible.short_description = 'Saldo disponible'


@admin.register(IntegracionMercadoPago)
class IntegracionMercadoPagoAdmin(admin.ModelAdmin):
    """Admin para IntegracionMercadoPago."""
    
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
