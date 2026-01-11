from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_add_jugado_estado"),
    ]

    operations = [
        migrations.AddField(
            model_name="turno",
            name="cancelacion_origen",
            field=models.CharField(
                blank=True,
                choices=[
                    ("usuario", "Usuario"),
                    ("staff", "Staff"),
                    ("bloqueo", "Bloqueo"),
                    ("sistema", "Sistema"),
                ],
                help_text="Quién/cómo se canceló (usuario, staff, bloqueo, sistema)",
                max_length=20,
                null=True,
                verbose_name="Origen de cancelación",
            ),
        ),
        migrations.AddField(
            model_name="turno",
            name="cancelacion_motivo",
            field=models.CharField(
                blank=True,
                help_text="Motivo breve (p.ej. “Lluvia”, “Mantenimiento”, etc.)",
                max_length=255,
                null=True,
                verbose_name="Motivo de cancelación",
            ),
        ),
        migrations.AddField(
            model_name="turno",
            name="cancelado_en",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Cancelado en"),
        ),
        migrations.AddField(
            model_name="turno",
            name="cancelado_por",
            field=models.ForeignKey(
                blank=True,
                help_text="Usuario que canceló (staff/admin). Vacío si canceló el cliente o el sistema.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="turnos_cancelados",
                to="core.usuario",
                verbose_name="Cancelado por",
            ),
        ),
    ]

