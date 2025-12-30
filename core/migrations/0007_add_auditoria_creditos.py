# Generated manually for auditoría de créditos

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_complejo_direccion_detallada_complejo_instagram_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='creditocliente',
            name='creado_por',
            field=models.ForeignKey(
                blank=True,
                help_text='Usuario que generó este crédito',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='creditos_creados',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Creado por'
            ),
        ),
        migrations.AddField(
            model_name='creditocliente',
            name='modificado_por',
            field=models.ForeignKey(
                blank=True,
                help_text='Último usuario que modificó este crédito',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='creditos_modificados',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Modificado por'
            ),
        ),
        migrations.AddField(
            model_name='creditocliente',
            name='historial',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Registro de cambios realizados en este crédito',
                verbose_name='Historial'
            ),
        ),
    ]

