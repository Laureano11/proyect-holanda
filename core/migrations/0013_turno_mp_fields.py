from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_pagomercadopago'),
    ]

    operations = [
        migrations.AddField(
            model_name='turno',
            name='mp_preference_id',
            field=models.CharField(blank=True, max_length=120, null=True, verbose_name='Preferencia MP'),
        ),
        migrations.AddField(
            model_name='turno',
            name='mp_payment_id',
            field=models.CharField(blank=True, max_length=120, null=True, verbose_name='Pago MP'),
        ),
        migrations.AddField(
            model_name='turno',
            name='mp_status',
            field=models.CharField(blank=True, max_length=40, null=True, verbose_name='Estado MP'),
        ),
        migrations.AddField(
            model_name='turno',
            name='mp_status_detail',
            field=models.CharField(blank=True, max_length=120, null=True, verbose_name='Detalle estado MP'),
        ),
        migrations.AddField(
            model_name='turno',
            name='mp_amount',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Monto pagado MP'),
        ),
        migrations.AddField(
            model_name='turno',
            name='mp_updated_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='MP actualizado en'),
        ),
    ]
