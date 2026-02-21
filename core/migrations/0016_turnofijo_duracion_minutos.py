from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_add_terms_acceptance'),
    ]

    operations = [
        migrations.AddField(
            model_name='turnofijo',
            name='duracion_minutos',
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name='Duración en minutos',
                help_text='Si está vacío, se usa la duración configurada en la cancha.'
            ),
        ),
    ]
