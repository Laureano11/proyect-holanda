from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_cancha_monto_comision_cancha_monto_senia_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="usuario",
            name="terms_version_accepted",
            field=models.PositiveIntegerField(default=0, verbose_name="Versión de términos aceptada"),
        ),
        migrations.AddField(
            model_name="usuario",
            name="terms_accepted_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Aceptó términos en"),
        ),
    ]

