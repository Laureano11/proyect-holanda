from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_merge_20260110_2339'),
    ]

    operations = [
        migrations.CreateModel(
            name='PagoMercadoPago',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('payment_id', models.CharField(max_length=50, unique=True)),
                ('merchant_order_id', models.CharField(blank=True, max_length=50, null=True)),
                ('preference_id', models.CharField(blank=True, max_length=80, null=True)),
                ('external_reference', models.CharField(blank=True, max_length=120, null=True)),
                ('status', models.CharField(choices=[('approved', 'Aprobado'), ('pending', 'Pendiente'), ('in_process', 'En proceso'), ('in_mediation', 'En mediación'), ('rejected', 'Rechazado'), ('cancelled', 'Cancelado'), ('refunded', 'Reembolsado'), ('charged_back', 'Contra-cargo'), ('unknown', 'Desconocido')], default='unknown', max_length=30)),
                ('status_detail', models.CharField(blank=True, max_length=120, null=True)),
                ('currency_id', models.CharField(blank=True, max_length=10, null=True)),
                ('amount', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('source', models.CharField(default='webhook', help_text='Origen del registro (webhook/feedback/manual)', max_length=20)),
                ('raw_payload', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('complejo', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pagos_mp', to='core.complejo', verbose_name='Complejo')),
                ('integration', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pagos', to='core.integracionmercadopago', verbose_name='Integración')),
                ('usuario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pagos_mp', to='core.usuario', verbose_name='Usuario')),
            ],
            options={
                'verbose_name': 'Pago Mercado Pago',
                'verbose_name_plural': 'Pagos Mercado Pago',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='pagomercadopago',
            index=models.Index(fields=['complejo', 'status'], name='pagomp_complejo_status_idx'),
        ),
    ]
