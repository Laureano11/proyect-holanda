# Generated manually for multi-tenant by subdominio

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_add_performance_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='complejo',
            name='subdominio',
            field=models.SlugField(
                blank=True,
                help_text='Subdominio para multi-tenant (ej: basanta para basanta.ha.com). Se genera del slug si está vacío.',
                max_length=50,
                null=True,
                unique=True,
                verbose_name='Subdominio'
            ),
        ),
    ]

