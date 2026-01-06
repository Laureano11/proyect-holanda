from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_add_jugado_estado'),
    ]

    operations = [
        migrations.AlterField(
            model_name='integracionmercadopago',
            name='access_token',
            field=models.TextField(help_text='Token de acceso de Mercado Pago (cifrado)', verbose_name='Access Token'),
        ),
        migrations.AddField(
            model_name='integracionmercadopago',
            name='refresh_token',
            field=models.TextField(blank=True, help_text='Refresh token de Mercado Pago (cifrado)', null=True, verbose_name='Refresh Token'),
        ),
        migrations.AddField(
            model_name='integracionmercadopago',
            name='token_expires_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Vence el'),
        ),
        migrations.AddField(
            model_name='integracionmercadopago',
            name='mp_user_id',
            field=models.CharField(blank=True, help_text='Identificador del vendedor en Mercado Pago', max_length=100, null=True, verbose_name='ID usuario MP'),
        ),
        migrations.AddField(
            model_name='integracionmercadopago',
            name='connected_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Conectado el'),
        ),
        migrations.AddField(
            model_name='integracionmercadopago',
            name='revoked_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Desconectado el'),
        ),
    ]

