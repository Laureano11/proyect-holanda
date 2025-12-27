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


class Complejo(models.Model):
    """
    Complejo deportivo que contiene canchas.
    El slug se usa para identificar el complejo en URLs.
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
    direccion = models.CharField(
        max_length=255,
        verbose_name='Dirección'
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
        """La seña es el precio dividido 4."""
        return self.precio_hora / 4
    
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
        CANCELADO_USUARIO = 'cancelado_usuario', 'Cancelado por Usuario'
        CANCELADO_ADMIN = 'cancelado_admin', 'Cancelado por Admin'
        EXPIRADO = 'expirado', 'Expirado'
    
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
    
    # Referencia de pago (Mercado Pago)
    pago_referencia = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Referencia de pago'
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
        # Evitar turnos duplicados en la misma cancha/fecha/hora
        unique_together = ['cancha', 'fecha', 'hora_inicio']
    
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
    def estado_visual(self):
        """
        Retorna el estado visual del turno:
        - Reservado: Pendiente de pago sin seña
        - Reservado con seña: Pendiente de pago con seña pagada
        - Abonado completo: Confirmado (pagado completamente)
        - Cancelado: Cualquier estado de cancelación
        """
        if self.fue_cancelado:
            return 'Cancelado'
        elif self.estado == self.Estado.CONFIRMADO:
            return 'Abonado completo'
        elif self.estado == self.Estado.PENDIENTE_PAGO:
            if self.senia_pagada > 0:
                return 'Reservado con seña'
            else:
                return 'Reservado'
        return 'Desconocido'
    
    @property
    def esta_pagado_completo(self):
        """Verifica si el turno está pagado completamente."""
        return self.estado == self.Estado.CONFIRMADO
    
    def save(self, *args, **kwargs):
        # Establecer precios si no están definidos
        if not self.precio_total:
            self.precio_total = self.cancha.precio_hora
        if not self.senia_requerida:
            self.senia_requerida = self.cancha.precio_senia
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
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Crédito de Cliente'
        verbose_name_plural = 'Créditos de Clientes'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.usuario} - ${self.saldo_disponible} ({self.complejo})"
    
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
    
    access_token = models.CharField(
        max_length=255,
        verbose_name='Access Token',
        help_text='Token de acceso de Mercado Pago'
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
    activo = models.BooleanField(
        default=True,
        verbose_name='Activo'
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
