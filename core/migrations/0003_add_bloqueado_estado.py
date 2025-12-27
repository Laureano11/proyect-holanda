# Generated manually to add BLOQUEADO state to Turno

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_bloqueo_creditocliente_integracionmercadopago_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='turno',
            name='estado',
            field=models.CharField(
                choices=[
                    ('pendiente_pago', 'Pendiente de Pago'),
                    ('confirmado', 'Confirmado'),
                    ('bloqueado', 'Bloqueado'),
                    ('cancelado_usuario', 'Cancelado por Usuario'),
                    ('cancelado_admin', 'Cancelado por Admin'),
                    ('expirado', 'Expirado')
                ],
                default='pendiente_pago',
                max_length=20,
                verbose_name='Estado'
            ),
        ),
    ]

