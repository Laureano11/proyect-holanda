from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_add_terms_acceptance'),
    ]

    operations = [
        migrations.AddField(
            model_name='preferenciascomplejo',
            name='turnos_en_vivo_habilitados',
            field=models.BooleanField(default=True, verbose_name='Turnos en vivo habilitados'),
        ),
    ]
