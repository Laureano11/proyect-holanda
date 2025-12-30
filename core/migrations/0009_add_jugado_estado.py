# Generated manually to add JUGADO state to Turno

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_merge_0007_migrations'),
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
                    ('expirado', 'Expirado'),
                    ('jugado', 'Jugado')
                ],
                default='pendiente_pago',
                max_length=20,
                verbose_name='Estado'
            ),
        ),
    ]

