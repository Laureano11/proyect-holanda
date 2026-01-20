"""
Modelos del Sistema de Gestión de Turnos.

Entidades principales:
- Usuario: Usuarios del sistema (SuperAdmin/Admin/Staff/Cliente)
- Complejo: Complejos deportivos
- PreferenciasComplejo: Configuración visual y features por complejo
- Cancha: Canchas de pádel
- CaracteristicaCancha: Características de las canchas (techada, iluminada, etc.)
- Turno: Reservas de turnos
- TurnoFijo: Turnos recurrentes/fijos
- Bloqueo: Cierres por feriados/lluvia/mantenimiento
- CreditoCliente: Sistema de créditos para reembolsos internos
- IntegracionMercadoPago: Credenciales de pago por complejo
"""

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.utils.text import slugify
from decimal import Decimal


class Usuario(AbstractUser):
    """
    Usuario del sistema extendiendo el modelo base de Django.
    Roles: SuperAdmin (vos), Admin de complejo, Staff, Cliente.
    
    - SuperAdmin: is_superuser=True, puede ver todo
    - Admin/Staff/Cliente: pertenecen a UN solo complejo
    """
    
    class Rol(models.TextChoices):
        SUPERADMIN = 'superadmin', 'Super Administrador'
        ADMIN = 'admin', 'Administrador de Complejo'
        STAFF = 'staff', 'Staff'
        CLIENTE = 'cliente', 'Cliente'
    
    rol = models.CharField(
        max_length=20,
        choices=Rol.choices,
        default=Rol.CLIENTE,
        verbose_name='Rol'
    )
    
    # Complejo al que pertenece (null para superadmin)
    complejo = models.ForeignKey(
        'Complejo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='usuarios',
        verbose_name='Complejo',
        help_text='Complejo al que pertenece (vacío para Super Administrador)'
    )
    
    dni = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='DNI'
    )
    celular = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Celular'
    )
    direccion = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Dirección'
    )

    # Términos y condiciones
    terms_version_accepted = models.PositiveIntegerField(
        default=0,
        verbose_name='Versión de términos aceptada'
    )
    terms_accepted_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Aceptó términos en'
    )
    
    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
    
    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_rol_display()})"
    
    @property
    def es_superadmin(self):
        return self.rol == self.Rol.SUPERADMIN or self.is_superuser
    
    @property
    def es_admin(self):
        return self.rol == self.Rol.ADMIN
    
    @property
    def es_staff_complejo(self):
        return self.rol == self.Rol.STAFF
    
    @property
    def es_cliente(self):
        return self.rol == self.Rol.CLIENTE
    
    @property
    def puede_gestionar_complejo(self):
        """Admin puede gestionar configuración del complejo."""
        return self.es_superadmin or self.es_admin
    
    @property
    def puede_gestionar_turnos(self):
        """Admin y Staff pueden gestionar turnos."""
        return self.es_superadmin or self.es_admin or self.es_staff_complejo
    
    def get_creditos_disponibles(self, complejo):
        """
        Calcula los créditos disponibles del usuario en un complejo específico.
        Optimizado para evitar queries duplicadas.
        """
        from django.db.models import Sum
        from decimal import Decimal
        
        # Query única con agregación
        resultado = self.creditos.filter(
            complejo=complejo,
            activo=True
        ).aggregate(
            total=Sum('monto'),
            usado=Sum('monto_usado')
        )
        
        total = resultado['total'] or Decimal('0.00')
        usado = resultado['usado'] or Decimal('0.00')
        
        return total - usado


class Complejo(models.Model):
    """
    Complejo deportivo que contiene canchas.
    El slug se usa para identificar el complejo en URLs.
    El subdominio se usa para multi-tenant (ej: basanta.ha.com).
    """
    
    nombre = models.CharField(
        max_length=100,
        verbose_name='Nombre'
    )
    slug = models.SlugField(
        max_length=50,
        unique=True,
        blank=True,
        verbose_name='Slug',
        help_text='Identificador único en URL (ej: padel-norte). Se genera automáticamente.'
    )
    subdominio = models.SlugField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        verbose_name='Subdominio',
        help_text='Subdominio para multi-tenant (ej: basanta para basanta.ha.com). Se genera del slug si está vacío.'
    )
    direccion = models.CharField(
        max_length=255,
        verbose_name='Dirección'
    )
    direccion_detallada = models.TextField(
        blank=True,
        null=True,
        verbose_name='Dirección Detallada',
        help_text='Información adicional de ubicación (referencias, indicaciones, etc.)'
    )
    telefono = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Teléfono'
    )
    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name='Email'
    )
    instagram = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Instagram',
        help_text='Usuario de Instagram (sin @)'
    )
    twitter_x = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='X (Twitter)',
        help_text='Usuario de X/Twitter (sin @)'
    )
    logo = models.ImageField(
        upload_to='complejos/logos/',
        blank=True,
        null=True,
        verbose_name='Logo'
    )
    
    # Horarios de operación
    hora_apertura = models.TimeField(
        default='08:00',
        verbose_name='Hora de apertura'
    )
    hora_cierre = models.TimeField(
        default='23:00',
        verbose_name='Hora de cierre'
    )
    
    activo = models.BooleanField(
        default=True,
        verbose_name='Activo'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Complejo'
        verbose_name_plural = 'Complejos'
        ordering = ['nombre']
    
    def __str__(self):
        return self.nombre
    
    def save(self, *args, **kwargs):
        # Generar slug automáticamente si no existe
        if not self.slug:
            base_slug = slugify(self.nombre)
            slug = base_slug
            counter = 1
            while Complejo.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        
        # Generar subdominio automáticamente del slug si no existe
        if not self.subdominio:
            self.subdominio = self.slug
        
        super().save(*args, **kwargs)


class PreferenciasComplejo(models.Model):
    """
    Preferencias de configuración y features por complejo.
    Permite personalizar la apariencia y funcionalidades.
    """
    
    complejo = models.OneToOneField(
        Complejo,
        on_delete=models.CASCADE,
        related_name='preferencias',
        verbose_name='Complejo'
    )
    
    # Configuración visual
    color_primario = models.CharField(
        max_length=7,
        default='#3B82F6',  # Azul
        verbose_name='Color primario',
        help_text='Color en formato hexadecimal (ej: #3B82F6)'
    )
    color_secundario = models.CharField(
        max_length=7,
        default='#1E40AF',
        verbose_name='Color secundario'
    )
    color_fondo = models.CharField(
        max_length=7,
        default='#F3F4F6',
        verbose_name='Color de fondo'
    )
    
    # Features habilitadas
    sistema_ranking = models.BooleanField(
        default=False,
        verbose_name='Sistema de ranking'
    )
    pago_senia = models.BooleanField(
        default=True,
        verbose_name='Requiere seña para reservar'
    )
    maneja_comisiones = models.BooleanField(
        default=False,
        verbose_name='Maneja comisiones',
        help_text='Si está activo, se suma la comisión configurada en cada cancha a la seña'
    )
    turnos_fijos_habilitados = models.BooleanField(
        default=True,
        verbose_name='Turnos fijos habilitados'
    )
    cancelacion_online = models.BooleanField(
        default=True,
        verbose_name='Cancelación online permitida'
    )
    notificaciones_whatsapp = models.BooleanField(
        default=False,
        verbose_name='Notificaciones por WhatsApp'
    )
    notificaciones_email = models.BooleanField(
        default=True,
        verbose_name='Notificaciones por Email'
    )
    
    # Configuración de reservas
    duracion_turno_minutos = models.PositiveIntegerField(
        default=60,
        verbose_name='Duración del turno (minutos)',
        help_text='Duración estándar de cada turno'
    )
    tiempo_minimo_cancelacion = models.PositiveIntegerField(
        default=2,
        verbose_name='Horas mínimas para cancelar',
        help_text='Horas de anticipación mínima para cancelar un turno'
    )
    tiempo_maximo_reserva = models.PositiveIntegerField(
        default=7,
        verbose_name='Días máximos para reservar',
        help_text='Días de anticipación máxima para reservar'
    )
    minutos_expiracion_pago = models.PositiveIntegerField(
        default=10,
        verbose_name='Minutos para completar pago',
        help_text='Tiempo máximo para completar el pago antes de liberar el turno'
    )
    
    class Meta:
        verbose_name = 'Preferencias de Complejo'
        verbose_name_plural = 'Preferencias de Complejos'
    
    def __str__(self):
        return f"Preferencias de {self.complejo}"


class CaracteristicaCancha(models.Model):
    """
    Características posibles de las canchas.
    Ej: Techada, Iluminada, Césped sintético, etc.
    """
    
    nombre = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Nombre'
    )
    icono = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='Icono',
        help_text='Nombre del icono (ej: para usar con Heroicons)'
    )
    
    class Meta:
        verbose_name = 'Característica de Cancha'
        verbose_name_plural = 'Características de Canchas'
        ordering = ['nombre']
    
    def __str__(self):
        return self.nombre


class Cancha(models.Model):
    """
    Cancha de pádel perteneciente a un complejo.
    """
    
    complejo = models.ForeignKey(
        Complejo,
        on_delete=models.CASCADE,
        related_name='canchas',
        verbose_name='Complejo'
    )
    nombre = models.CharField(
        max_length=50,
        verbose_name='Nombre',
        help_text='Ej: Cancha 1, Cancha A, etc.'
    )
    precio_hora = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='Precio por hora'
    )
    monto_senia = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='Monto seña'
    )
    monto_comision = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='Monto comisión'
    )
    capacidad = models.PositiveIntegerField(
        default=4,
        verbose_name='Capacidad de jugadores'
    )
    
    # Duración personalizada (opcional, si no usa la del complejo)
    duracion_turno_minutos = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Duración del turno (minutos)',
        help_text='Dejar vacío para usar la duración del complejo'
    )
    
    # Características de la cancha
    caracteristicas = models.ManyToManyField(
        CaracteristicaCancha,
        blank=True,
        related_name='canchas',
        verbose_name='Características'
    )
    
    descripcion = models.TextField(
        blank=True,
        null=True,
        verbose_name='Descripción'
    )
    imagen = models.ImageField(
        upload_to='canchas/',
        blank=True,
        null=True,
        verbose_name='Imagen'
    )
    
    activa = models.BooleanField(
        default=True,
        verbose_name='Activa'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Cancha'
        verbose_name_plural = 'Canchas'
        ordering = ['complejo', 'nombre']
        unique_together = ['complejo', 'nombre']
    
    def __str__(self):
        return f"{self.nombre} - {self.complejo}"
    
    @property
    def precio_senia(self):
        """
        Monto de seña configurable por cancha.
        Si el complejo maneja comisiones, se suma la comisión de la cancha.
        Para compatibilidad, si no hay seña configurada se usa precio_hora / 4.
        """
        monto_senia = self.monto_senia or Decimal('0.00')
        if monto_senia <= 0:
            try:
                monto_senia = self.precio_hora / 4
            except Exception:
                monto_senia = Decimal('0.00')
        try:
            if self.complejo.preferencias.maneja_comisiones:
                return monto_senia + (self.monto_comision or Decimal('0.00'))
        except PreferenciasComplejo.DoesNotExist:
            pass
        return monto_senia
    
    def get_duracion_turno(self):
        """Retorna la duración del turno (propia o del complejo)."""
        if self.duracion_turno_minutos:
            return self.duracion_turno_minutos
        try:
            return self.complejo.preferencias.duracion_turno_minutos
        except PreferenciasComplejo.DoesNotExist:
            return 60  # Default 1 hora


class Bloqueo(models.Model):
    """
    Bloqueo de disponibilidad por feriados, lluvia, mantenimiento, etc.
    Puede ser por día completo o por rango horario.
    """
    
    complejo = models.ForeignKey(
        Complejo,
        on_delete=models.CASCADE,
        related_name='bloqueos',
        verbose_name='Complejo'
    )
    cancha = models.ForeignKey(
        Cancha,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='bloqueos',
        verbose_name='Cancha',
        help_text='Dejar vacío para bloquear todas las canchas del complejo'
    )
    
    fecha = models.DateField(
        verbose_name='Fecha'
    )
    hora_inicio = models.TimeField(
        null=True,
        blank=True,
        verbose_name='Hora inicio',
        help_text='Dejar vacío para bloquear el día completo'
    )
    hora_fin = models.TimeField(
        null=True,
        blank=True,
        verbose_name='Hora fin'
    )
    
    motivo = models.CharField(
        max_length=100,
        verbose_name='Motivo',
        help_text='Ej: Feriado, Lluvia, Mantenimiento'
    )
    
    created_by = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        related_name='bloqueos_creados',
        verbose_name='Creado por'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Bloqueo'
        verbose_name_plural = 'Bloqueos'
        ordering = ['-fecha', 'hora_inicio']
        # Índices para optimizar queries frecuentes
        indexes = [
            models.Index(fields=['complejo', 'fecha'], name='bloqueo_complejo_fecha_idx'),
            models.Index(fields=['fecha', 'cancha'], name='bloqueo_fecha_cancha_idx'),
        ]
    
    def __str__(self):
        if self.cancha:
            return f"{self.cancha} - {self.fecha} ({self.motivo})"
        return f"{self.complejo} - {self.fecha} ({self.motivo})"
    
    @property
    def es_dia_completo(self):
        return self.hora_inicio is None


class Turno(models.Model):
    """
    Reserva de un turno en una cancha.
    """
    
    class Estado(models.TextChoices):
        PENDIENTE_PAGO = 'pendiente_pago', 'Pendiente de Pago'
        CONFIRMADO = 'confirmado', 'Confirmado'
        BLOQUEADO = 'bloqueado', 'Bloqueado'
        CANCELADO_USUARIO = 'cancelado_usuario', 'Cancelado por Usuario'
        CANCELADO_ADMIN = 'cancelado_admin', 'Cancelado por Admin'
        EXPIRADO = 'expirado', 'Expirado'
        JUGADO = 'jugado', 'Jugado'

    class CancelacionOrigen(models.TextChoices):
        USUARIO = 'usuario', 'Usuario'
        STAFF = 'staff', 'Staff'
        BLOQUEO = 'bloqueo', 'Bloqueo'
        SISTEMA = 'sistema', 'Sistema'
    
    cancha = models.ForeignKey(
        Cancha,
        on_delete=models.CASCADE,
        related_name='turnos',
        verbose_name='Cancha'
    )
    cliente = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name='turnos',
        verbose_name='Cliente'
    )
    
    fecha = models.DateField(
        verbose_name='Fecha'
    )
    hora_inicio = models.TimeField(
        verbose_name='Hora de inicio'
    )
    duracion_minutos = models.PositiveIntegerField(
        default=60,
        verbose_name='Duración (minutos)'
    )
    
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE_PAGO,
        verbose_name='Estado'
    )
    
    # Fecha límite para completar el pago
    expira_en = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Expira en',
        help_text='Fecha límite para completar el pago'
    )

    # Cancelación: motivo/origen/auditoría (opcional; se completa cuando aplica)
    cancelacion_origen = models.CharField(
        max_length=20,
        choices=CancelacionOrigen.choices,
        null=True,
        blank=True,
        verbose_name='Origen de cancelación',
        help_text='Quién/cómo se canceló (usuario, staff, bloqueo, sistema)'
    )
    cancelacion_motivo = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name='Motivo de cancelación',
        help_text='Motivo breve (p.ej. “Lluvia”, “Mantenimiento”, etc.)'
    )
    cancelado_por = models.ForeignKey(
        'Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='turnos_cancelados',
        verbose_name='Cancelado por',
        help_text='Usuario que canceló (staff/admin). Vacío si canceló el cliente o el sistema.'
    )
    cancelado_en = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Cancelado en'
    )
    
    precio_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Precio total'
    )
    senia_requerida = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Seña requerida'
    )
    senia_pagada = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Seña pagada'
    )
    creditos_usados = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Créditos usados'
    )
    monto_comision = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Monto comisión'
    )
    
    # Referencia de pago (Mercado Pago)
    pago_referencia = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Referencia de pago'
    )
    # Metadata de Mercado Pago (para seguimiento de la seña)
    mp_preference_id = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        verbose_name='Preferencia MP'
    )
    mp_payment_id = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        verbose_name='Pago MP'
    )
    mp_status = models.CharField(
        max_length=40,
        blank=True,
        null=True,
        verbose_name='Estado MP'
    )
    mp_status_detail = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        verbose_name='Detalle estado MP'
    )
    mp_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Monto pagado MP'
    )
    mp_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='MP actualizado en'
    )
    
    notas = models.TextField(
        blank=True,
        null=True,
        verbose_name='Notas'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Turno'
        verbose_name_plural = 'Turnos'
        ordering = ['fecha', 'hora_inicio']
        constraints = [
            # Evitar superposición de turnos activos en la misma cancha/fecha/hora
            models.UniqueConstraint(
                fields=['cancha', 'fecha', 'hora_inicio'],
                name='turno_cancha_fecha_hora_unico_activo',
                condition=~models.Q(
                    estado__in=[
                        'cancelado_usuario',
                        'cancelado_admin',
                        'expirado',
                    ]
                ),
            ),
        ]
        # Índices para optimizar queries frecuentes
        indexes = [
            models.Index(fields=['fecha', 'estado'], name='turno_fecha_estado_idx'),
            models.Index(fields=['cliente', 'estado'], name='turno_cliente_estado_idx'),
            models.Index(fields=['fecha', 'hora_inicio'], name='turno_fecha_hora_idx'),
            models.Index(fields=['estado', 'created_at'], name='turno_estado_created_idx'),
            models.Index(fields=['cancha', 'fecha'], name='turno_cancha_fecha_idx'),
        ]
    
    def __str__(self):
        return f"{self.cancha} - {self.fecha} {self.hora_inicio}"
    
    @property
    def hora_fin(self):
        """Calcula la hora de fin basada en la duración."""
        from datetime import datetime, timedelta
        dt = datetime.combine(self.fecha, self.hora_inicio)
        dt_fin = dt + timedelta(minutes=self.duracion_minutos)
        return dt_fin.time()
    
    @property
    def esta_pagado(self):
        return self.estado == self.Estado.CONFIRMADO
    
    @property
    def esta_pendiente(self):
        return self.estado == self.Estado.PENDIENTE_PAGO
    
    @property
    def fue_cancelado(self):
        return self.estado in [self.Estado.CANCELADO_USUARIO, self.Estado.CANCELADO_ADMIN, self.Estado.EXPIRADO]

    @property
    def cancelacion_descripcion(self) -> str:
        """
        Texto amigable para mostrar al cliente el motivo/origen de cancelación.
        Tiene fallback para turnos viejos (sin campos de cancelación cargados).
        """
        if self.estado == self.Estado.CANCELADO_USUARIO:
            base = "Cancelado por vos"
            if self.cancelacion_motivo:
                return f"{base}: {self.cancelacion_motivo}"
            return base

        if self.estado == self.Estado.EXPIRADO:
            # El “expirado” es una cancelación del sistema
            base = "Expirado por falta de pago"
            if self.cancelacion_motivo:
                return f"{base}: {self.cancelacion_motivo}"
            return base

        if self.estado == self.Estado.CANCELADO_ADMIN:
            # Distinguir staff vs bloqueo, con fallback a “staff”
            if self.cancelacion_origen == self.CancelacionOrigen.BLOQUEO:
                base = "Cancelado por bloqueo de turnos"
            else:
                base = "Cancelado por staff"
            if self.cancelacion_motivo:
                return f"{base}: {self.cancelacion_motivo}"
            return base

        return ""
    
    @property
    def ya_paso(self):
        """Verifica si el turno ya pasó (fecha y hora de fin ya pasaron)."""
        from django.utils import timezone
        from datetime import datetime, timedelta
        
        ahora = timezone.now()
        fecha_hora_inicio = timezone.make_aware(
            timezone.datetime.combine(self.fecha, self.hora_inicio)
        )
        fecha_hora_fin = fecha_hora_inicio + timedelta(minutes=self.duracion_minutos)
        
        return ahora > fecha_hora_fin

    @property
    def ya_empezo(self):
        """Verifica si el turno ya empezó (fecha y hora de inicio ya pasaron)."""
        from django.utils import timezone
        from datetime import datetime

        ahora = timezone.now()
        fecha_hora_inicio = timezone.make_aware(
            timezone.datetime.combine(self.fecha, self.hora_inicio)
        )
        return ahora >= fecha_hora_inicio
    
    @property
    def estado_visual(self):
        """
        Retorna el estado visual normalizado del turno:
        1. Jugado: Turno que ya pasó y no fue cancelado
        2. Pagado completo: Cuando se abona completamente
        3. Reservado con seña: Cliente lo reserva y abona seña
        4. Reservado: Staff lo crea sin seña
        5. Bloqueado: Staff bloquea el turno
        6. Cancelado: Turno cancelado
        """
        # Estados normalizados
        if self.estado == self.Estado.JUGADO:
            return 'Jugado'
        elif self.estado == self.Estado.BLOQUEADO:
            return 'Bloqueado'
        elif self.fue_cancelado:
            return 'Cancelado'
        elif self.estado == self.Estado.CONFIRMADO:
            return 'Pagado completo'
        elif self.estado == self.Estado.PENDIENTE_PAGO:
            # Si hay un pago MP en curso, reflejarlo
            if (self.mp_status in ['pending', 'in_process', 'in_mediation']) or (self.mp_amount and not self.senia_completa_pagada):
                return 'En pago'
            if self.senia_pagada > 0:
                return 'Reservado con seña'
            return 'Reservado'
        return 'Desconocido'
    
    @classmethod
    def marcar_turnos_como_jugados(cls):
        """
        Marca automáticamente los turnos que ya pasaron como 'Jugado'.
        Solo marca turnos que no fueron cancelados y que ya pasó su hora de fin.
        """
        from django.utils import timezone
        from datetime import datetime, timedelta
        from django.db.models import Q
        
        ahora = timezone.now()
        hoy = ahora.date()
        turnos_actualizados = 0
        
        # Obtener turnos que no están cancelados ni ya marcados como jugados
        # Optimización: no tiene sentido revisar turnos de fechas futuras.
        # Incluimos turnos de días anteriores y, del día de hoy, solo los que ya empezaron.
        turnos_a_verificar = (
            cls.objects.exclude(
                estado__in=[
                    cls.Estado.CANCELADO_USUARIO,
                    cls.Estado.CANCELADO_ADMIN,
                    cls.Estado.EXPIRADO,
                    cls.Estado.JUGADO,
                ]
            )
            .filter(Q(fecha__lt=hoy) | Q(fecha=hoy, hora_inicio__lte=ahora.time()))
        )
        
        for turno in turnos_a_verificar:
            fecha_hora_inicio = timezone.make_aware(
                timezone.datetime.combine(turno.fecha, turno.hora_inicio)
            )
            fecha_hora_fin = fecha_hora_inicio + timedelta(minutes=turno.duracion_minutos)
            
            # Si ya pasó la hora de fin, marcar como jugado
            if ahora > fecha_hora_fin:
                turno.estado = cls.Estado.JUGADO
                turno.save(update_fields=['estado'])
                turnos_actualizados += 1
        
        return turnos_actualizados
    
    @property
    def esta_pagado_completo(self):
        """Verifica si el turno está pagado completamente."""
        return self.estado == self.Estado.CONFIRMADO
    
    @property
    def senia_completa_pagada(self):
        """Indica si la seña requerida está totalmente cubierta."""
        return self.senia_pagada >= self.senia_requerida
    
    @property
    def saldo_senia_pendiente(self):
        """Cuánto resta para completar la seña (no negativo)."""
        restante = self.senia_requerida - self.senia_pagada
        return restante if restante > 0 else Decimal('0.00')
    
    def save(self, *args, **kwargs):
        # Establecer precios si no están definidos
        if not self.precio_total:
            self.precio_total = self.cancha.precio_hora
        if not self.senia_requerida:
            self.senia_requerida = self.cancha.precio_senia
        if not self.monto_comision:
            try:
                if self.cancha.complejo.preferencias.maneja_comisiones:
                    self.monto_comision = self.cancha.monto_comision or Decimal('0.00')
                else:
                    self.monto_comision = Decimal('0.00')
            except PreferenciasComplejo.DoesNotExist:
                self.monto_comision = Decimal('0.00')
        if not self.duracion_minutos:
            self.duracion_minutos = self.cancha.get_duracion_turno()
        super().save(*args, **kwargs)


class TurnoFijo(models.Model):
    """
    Turno recurrente/fijo.
    Se repite cada semana en el mismo día y hora.
    """
    
    class DiaSemana(models.IntegerChoices):
        LUNES = 0, 'Lunes'
        MARTES = 1, 'Martes'
        MIERCOLES = 2, 'Miércoles'
        JUEVES = 3, 'Jueves'
        VIERNES = 4, 'Viernes'
        SABADO = 5, 'Sábado'
        DOMINGO = 6, 'Domingo'
    
    cancha = models.ForeignKey(
        Cancha,
        on_delete=models.CASCADE,
        related_name='turnos_fijos',
        verbose_name='Cancha'
    )
    cliente = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name='turnos_fijos',
        verbose_name='Cliente'
    )
    
    dia_semana = models.IntegerField(
        choices=DiaSemana.choices,
        verbose_name='Día de la semana'
    )
    hora_inicio = models.TimeField(
        verbose_name='Hora de inicio'
    )
    
    fecha_inicio = models.DateField(
        verbose_name='Fecha de inicio',
        help_text='Desde cuándo aplica el turno fijo'
    )
    fecha_fin = models.DateField(
        blank=True,
        null=True,
        verbose_name='Fecha de fin',
        help_text='Hasta cuándo aplica el turno fijo (dejar vacío para indefinido)'
    )
    
    activo = models.BooleanField(
        default=True,
        verbose_name='Activo'
    )
    
    notas = models.TextField(
        blank=True,
        null=True,
        verbose_name='Notas'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Turno Fijo'
        verbose_name_plural = 'Turnos Fijos'
        ordering = ['dia_semana', 'hora_inicio']
        # Evitar turnos fijos duplicados
        unique_together = ['cancha', 'dia_semana', 'hora_inicio']
        # Índices para optimizar queries frecuentes
        indexes = [
            models.Index(fields=['activo', 'dia_semana'], name='turnofijo_activo_dia_idx'),
            models.Index(fields=['cancha', 'activo'], name='turnofijo_cancha_activo_idx'),
        ]
    
    @property
    def hora_fin(self):
        """Calcula la hora de fin del turno (1 hora después del inicio)."""
        from datetime import datetime, timedelta
        hora_fin = (datetime.combine(datetime.today(), self.hora_inicio) + timedelta(hours=1)).time()
        return hora_fin
    
    def __str__(self):
        return f"{self.cancha} - {self.get_dia_semana_display()} {self.hora_inicio}"


class CreditoCliente(models.Model):
    """
    Sistema de créditos para reembolsos internos.
    Cuando el admin cancela un turno, el cliente recibe créditos
    que puede usar para futuras reservas.
    """
    
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name='creditos',
        verbose_name='Usuario'
    )
    complejo = models.ForeignKey(
        Complejo,
        on_delete=models.CASCADE,
        related_name='creditos_clientes',
        verbose_name='Complejo'
    )
    
    monto = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Monto'
    )
    monto_usado = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Monto usado'
    )
    
    motivo = models.CharField(
        max_length=200,
        verbose_name='Motivo',
        help_text='Ej: Cancelación turno del 25/12/2025'
    )
    turno_origen = models.ForeignKey(
        Turno,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='creditos_generados',
        verbose_name='Turno origen'
    )
    
    activo = models.BooleanField(
        default=True,
        verbose_name='Activo'
    )
    
    # Campos de auditoría
    creado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='creditos_creados',
        verbose_name='Creado por',
        help_text='Usuario que generó este crédito'
    )
    modificado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='creditos_modificados',
        verbose_name='Modificado por',
        help_text='Último usuario que modificó este crédito'
    )
    historial = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Historial',
        help_text='Registro de cambios realizados en este crédito'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Crédito de Cliente'
        verbose_name_plural = 'Créditos de Clientes'
        ordering = ['-created_at']
        # Índices para optimizar queries frecuentes
        indexes = [
            models.Index(fields=['usuario', 'complejo', 'activo'], name='credito_usuario_complejo_idx'),
            models.Index(fields=['activo', 'created_at'], name='credito_activo_created_idx'),
        ]
    
    def __str__(self):
        return f"{self.usuario} - ${self.saldo_disponible} ({self.complejo})"
    
    def clean(self):
        """Validar integridad de datos."""
        from django.core.exceptions import ValidationError
        
        # Verificar que monto_usado no exceda monto
        if self.monto_usado > self.monto:
            raise ValidationError({
                'monto_usado': 'El monto usado no puede ser mayor al monto total del crédito.'
            })
        
        # Verificar que monto_usado no sea negativo
        if self.monto_usado < Decimal('0.00'):
            raise ValidationError({
                'monto_usado': 'El monto usado no puede ser negativo.'
            })
        
        # Si hay turno_origen, validar que pertenece al usuario y complejo
        if self.turno_origen:
            if self.turno_origen.cliente != self.usuario:
                raise ValidationError({
                    'turno_origen': 'El turno origen debe pertenecer al usuario del crédito.'
                })
            
            if self.turno_origen.cancha.complejo != self.complejo:
                raise ValidationError({
                    'turno_origen': 'El turno origen debe pertenecer al mismo complejo del crédito.'
                })
    
    def save(self, *args, **kwargs):
        """Guardar con validaciones y registro de historial."""
        from django.utils import timezone
        
        # Ejecutar validaciones
        self.full_clean()
        
        # Si es una actualización, registrar en historial
        if self.pk:
            try:
                credito_anterior = CreditoCliente.objects.get(pk=self.pk)
                
                # Detectar cambios
                cambios = {}
                if credito_anterior.monto != self.monto:
                    cambios['monto'] = {
                        'anterior': str(credito_anterior.monto),
                        'nuevo': str(self.monto)
                    }
                if credito_anterior.monto_usado != self.monto_usado:
                    cambios['monto_usado'] = {
                        'anterior': str(credito_anterior.monto_usado),
                        'nuevo': str(self.monto_usado)
                    }
                if credito_anterior.activo != self.activo:
                    cambios['activo'] = {
                        'anterior': credito_anterior.activo,
                        'nuevo': self.activo
                    }
                
                # Registrar cambio en historial si hay modificaciones
                if cambios:
                    if not isinstance(self.historial, list):
                        self.historial = []
                    
                    self.historial.append({
                        'accion': 'modificado',
                        'fecha': timezone.now().isoformat(),
                        'cambios': cambios,
                        'modificado_por': self.modificado_por.username if self.modificado_por else 'sistema',
                    })
            except CreditoCliente.DoesNotExist:
                pass  # Es un nuevo crédito
        
        super().save(*args, **kwargs)
    
    @property
    def saldo_disponible(self):
        return self.monto - self.monto_usado
    
    @property
    def esta_agotado(self):
        return self.saldo_disponible <= 0


class IntegracionMercadoPago(models.Model):
    """
    Credenciales de Mercado Pago por complejo.
    Cada complejo tiene sus propias credenciales para recibir pagos.
    """
    
    class Modo(models.TextChoices):
        TEST = 'test', 'Test (Sandbox)'
        PROD = 'prod', 'Producción'
    
    complejo = models.OneToOneField(
        Complejo,
        on_delete=models.CASCADE,
        related_name='mercadopago',
        verbose_name='Complejo'
    )
    
    access_token = models.TextField(
        verbose_name='Access Token',
        help_text='Token de acceso de Mercado Pago (cifrado)'
    )
    refresh_token = models.TextField(
        blank=True,
        null=True,
        verbose_name='Refresh Token',
        help_text='Refresh token de Mercado Pago (cifrado)'
    )
    token_expires_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Vence el'
    )
    public_key = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Public Key',
        help_text='Clave pública (opcional, para checkout JS)'
    )
    
    modo = models.CharField(
        max_length=10,
        choices=Modo.choices,
        default=Modo.TEST,
        verbose_name='Modo'
    )
    mp_user_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='ID usuario MP',
        help_text='Identificador del vendedor en Mercado Pago'
    )
    activo = models.BooleanField(
        default=True,
        verbose_name='Activo'
    )
    connected_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Conectado el'
    )
    revoked_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Desconectado el'
    )
    
    # Webhook URL se genera automáticamente basado en el complejo
    webhook_secret = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Webhook Secret',
        help_text='Secreto para validar webhooks (opcional)'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Integración Mercado Pago'
        verbose_name_plural = 'Integraciones Mercado Pago'
    
    def __str__(self):
        return f"MP - {self.complejo} ({self.get_modo_display()})"

    def set_tokens(self, access_token, refresh_token=None, expires_in=None, mp_user_id=None):
        """Configura tokens cifrados y marca la conexión activa."""
        from django.utils import timezone
        from datetime import timedelta
        from core.utils.crypto import encrypt_string
        self.access_token = encrypt_string(access_token) if access_token else None
        if refresh_token is not None:
            self.refresh_token = encrypt_string(refresh_token) if refresh_token else None
        if expires_in:
            self.token_expires_at = timezone.now() + timedelta(seconds=expires_in)
        if mp_user_id:
            self.mp_user_id = str(mp_user_id)
        self.activo = True
        if not self.connected_at:
            self.connected_at = timezone.now()
        self.revoked_at = None

    @property
    def access_token_plain(self):
        """Devuelve el access token descifrado (o None)."""
        from core.utils.crypto import decrypt_string
        return decrypt_string(self.access_token)

    @property
    def refresh_token_plain(self):
        """Devuelve el refresh token descifrado (o None)."""
        from core.utils.crypto import decrypt_string
        return decrypt_string(self.refresh_token)

    def access_token_masked(self):
        """Token enmascarado para mostrar en admin."""
        token = self.access_token_plain
        if not token:
            return "—"
        if len(token) <= 8:
            return "***"
        return f"{token[:4]}...{token[-4:]}"
    access_token_masked.short_description = "Access token"

    def refresh_token_masked(self):
        token = self.refresh_token_plain
        if not token:
            return "—"
        if len(token) <= 8:
            return "***"
        return f"{token[:4]}...{token[-4:]}"
    refresh_token_masked.short_description = "Refresh token"

    def is_expired(self):
        from django.utils import timezone
        if not self.token_expires_at:
            return False
        return timezone.now() >= self.token_expires_at


class PagoMercadoPago(models.Model):
    """
    Registro básico de pagos/notificaciones de Mercado Pago para auditoría.
    """
    class Estado(models.TextChoices):
        APPROVED = "approved", "Aprobado"
        PENDING = "pending", "Pendiente"
        IN_PROCESS = "in_process", "En proceso"
        IN_MEDIATION = "in_mediation", "En mediación"
        REJECTED = "rejected", "Rechazado"
        CANCELLED = "cancelled", "Cancelado"
        REFUNDED = "refunded", "Reembolsado"
        CHARGED_BACK = "charged_back", "Contra-cargo"
        UNKNOWN = "unknown", "Desconocido"

    complejo = models.ForeignKey(
        'Complejo',
        on_delete=models.CASCADE,
        related_name='pagos_mp',
        verbose_name='Complejo'
    )
    integration = models.ForeignKey(
        IntegracionMercadoPago,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pagos',
        verbose_name='Integración'
    )
    usuario = models.ForeignKey(
        'Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pagos_mp',
        verbose_name='Usuario'
    )

    payment_id = models.CharField(max_length=50, unique=True)
    merchant_order_id = models.CharField(max_length=50, blank=True, null=True)
    preference_id = models.CharField(max_length=80, blank=True, null=True)
    external_reference = models.CharField(max_length=120, blank=True, null=True)

    status = models.CharField(
        max_length=30,
        choices=Estado.choices,
        default=Estado.UNKNOWN
    )
    status_detail = models.CharField(max_length=120, blank=True, null=True)
    currency_id = models.CharField(max_length=10, blank=True, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    source = models.CharField(
        max_length=20,
        default="webhook",
        help_text="Origen del registro (webhook/feedback/manual)"
    )
    raw_payload = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Pago Mercado Pago"
        verbose_name_plural = "Pagos Mercado Pago"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["complejo", "status"], name="pagomp_complejo_status_idx"),
        ]

    def __str__(self):
        return f"Pago MP {self.payment_id} ({self.status})"
