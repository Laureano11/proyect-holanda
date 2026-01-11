# 📧 Configuración de Email - Sistema de Recuperación de Contraseñas

## ✅ Sistema Implementado

El sistema de recuperación de contraseñas está **completamente implementado** usando las vistas nativas de Django.

### URLs disponibles:
- `/password-reset/` - Solicitar recuperación
- `/password-reset/done/` - Confirmación de envío
- `/password-reset/<uidb64>/<token>/` - Establecer nueva contraseña
- `/password-reset/complete/` - Éxito

---

## 🔧 Configuración en Desarrollo

**En desarrollo, los emails se muestran en la consola** (no necesitas configurar nada).

Cuando un usuario solicite recuperar su contraseña:
1. El email se imprimirá en la terminal donde corre el servidor Django
2. Copiá el link del email y pegalo en el navegador
3. ¡Listo! Podés probar todo el flujo sin configurar SMTP

---

## 🚀 Configuración en Producción

Para producción, necesitas configurar un servicio SMTP real. Acá te muestro las mejores opciones:

### Opción 1: Gmail (Solo para Testing)

⚠️ **No recomendado para producción** (límites de envío)

1. Activá la verificación en 2 pasos en tu cuenta de Google
2. Generá una "Contraseña de aplicación":
   - Andá a: https://myaccount.google.com/apppasswords
   - Creá una contraseña para "Correo"
   - Copiá la contraseña de 16 caracteres

3. En tu archivo `.env`:
```bash
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=tu_email@gmail.com
EMAIL_HOST_PASSWORD=xxxx xxxx xxxx xxxx  # La contraseña de app de 16 caracteres
DEFAULT_FROM_EMAIL=noreply@tuapp.com
```

---

### Opción 2: SendGrid (Recomendado) ⭐

**Ventajas:**
- ✅ Profesional y confiable
- ✅ 100 emails gratis por día
- ✅ Excelente deliverability
- ✅ Dashboard con estadísticas

**Configuración:**

1. Creá cuenta en: https://sendgrid.com/
2. Verificá tu dominio (o usá el dominio compartido)
3. Generá una API Key en Settings > API Keys
4. En tu archivo `.env`:

```bash
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  # Tu API Key
DEFAULT_FROM_EMAIL=noreply@tudominio.com
```

**Precio:** Gratis hasta 100 emails/día, luego $14.95/mes

---

### Opción 3: Resend (Moderno) 🔥

**Ventajas:**
- ✅ Muy fácil de configurar
- ✅ Interfaz moderna
- ✅ 3,000 emails gratis por mes
- ✅ Excelente para SaaS

**Configuración:**

1. Creá cuenta en: https://resend.com/
2. Generá una API Key
3. Verificá tu dominio
4. En tu archivo `.env`:

```bash
EMAIL_HOST=smtp.resend.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=resend
EMAIL_HOST_PASSWORD=re_xxxxxxxxxxxxxxxxxxxxxxxx  # Tu API Key
DEFAULT_FROM_EMAIL=noreply@tudominio.com
```

**Precio:** Gratis hasta 3,000 emails/mes, luego $20/mes

---

### Opción 4: AWS SES (Más barato para volumen)

**Ventajas:**
- ✅ Muy económico ($0.10 por 1,000 emails)
- ✅ Escalable
- ✅ Integración con AWS

**Desventajas:**
- ❌ Configuración más compleja
- ❌ Requiere verificar dominio

**Configuración:**

1. Creá cuenta AWS y activá SES
2. Verificá tu dominio
3. Creá credenciales SMTP
4. En tu archivo `.env`:

```bash
EMAIL_HOST=email-smtp.us-east-1.amazonaws.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=tu_smtp_username
EMAIL_HOST_PASSWORD=tu_smtp_password
DEFAULT_FROM_EMAIL=noreply@tudominio.com
```

---

## 🧪 Cómo Probar

### En Desarrollo (Consola):

1. Iniciá el servidor:
```bash
python manage.py runserver
```

2. Andá a: http://localhost:8000/login/
3. Hacé clic en "¿Olvidaste tu contraseña?"
4. Ingresá un email de un usuario existente
5. **Mirá la consola** donde corre Django - el email se imprimirá ahí
6. Copiá el link y pegalo en el navegador

### En Producción (SMTP Real):

1. Configurá las variables de entorno en tu `.env`
2. Reiniciá el servidor
3. El email se enviará realmente al usuario

---

## 📝 Personalización

### Cambiar el contenido del email:

Editá: `templates/auth/password_reset_email.html`

### Cambiar el asunto del email:

Editá: `templates/auth/password_reset_subject.txt`

### Cambiar el tiempo de expiración del link:

En `config/settings.py`:
```python
PASSWORD_RESET_TIMEOUT = 86400  # 24 horas (en segundos)
```

---

## 🔒 Seguridad

✅ Los tokens son únicos y de un solo uso
✅ Los tokens expiran después de 24 horas
✅ Los links incluyen UID encriptado del usuario
✅ Django valida automáticamente la integridad del token

---

## 🐛 Troubleshooting

### "El email no llega"
- Verificá que las credenciales SMTP sean correctas
- Revisá la carpeta de SPAM
- Verificá que el dominio esté verificado (SendGrid/Resend)
- Mirá los logs de Django para errores

### "SMTPAuthenticationError"
- Las credenciales son incorrectas
- Si usás Gmail, necesitas una "Contraseña de aplicación"
- Verificá que EMAIL_HOST_USER y EMAIL_HOST_PASSWORD estén correctos

### "Connection refused"
- Verificá EMAIL_HOST y EMAIL_PORT
- Asegurate que EMAIL_USE_TLS esté en True

---

## 📚 Recursos

- [Documentación Django - Email](https://docs.djangoproject.com/en/4.2/topics/email/)
- [SendGrid Docs](https://docs.sendgrid.com/)
- [Resend Docs](https://resend.com/docs)
- [Gmail App Passwords](https://support.google.com/accounts/answer/185833)

---

## ✨ Próximos Pasos Recomendados

1. **Ahora:** Probá el flujo en desarrollo (consola)
2. **Después:** Configurá SendGrid o Resend para producción
3. **Opcional:** Personalizá los templates de email con tu branding
4. **Opcional:** Agregá rate limiting para prevenir spam

---

¿Dudas? Revisá los templates en `templates/auth/password_reset_*.html`

