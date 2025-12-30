# Generated manually to merge conflicting migrations

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_add_auditoria_creditos'),
        ('core', '0007_turno_unique_active_constraint'),
    ]

    operations = [
        # Esta migración solo une las dos ramas, no realiza cambios en la BD
    ]


