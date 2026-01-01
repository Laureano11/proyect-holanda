# 🔧 Fix: Página se cae al enviar emails

## 🚨 Problema Original

Cuando un usuario solicita restablecer contraseña, **toda la página se muere** y deja de funcionar.

**Causa:** Django envía emails de forma **síncrona** (bloqueante):
1. Usuario hace clic en "Enviar"
2. Django intenta conectar a SMTP
3. Si hay timeout o falla, **bloquea el worker** de Render
4. Worker se cae → Toda la app se cae
5. Render reinicia el worker → Ciclo infinito

---

## ✅ Solución Implementada: Emails Asíncronos

### **Cambio Principal:**
Ahora los emails se envían en un **thread separado** (background):

1. Usuario hace clic en "Enviar"
2. Django programa el email para envío
3. **Responde inmediatamente** (sin esperar)
4. Email se envía en background
5. Si falla, no afecta la app

---

## 📋 Cambios Realizados

### 1. **Vista personalizada con threading** (`core/email_views.py`)

```python
def send_email_async(subject, email_template_name, context, from_email, to_email):
    """
    Envía email en un thread separado para no bloquear la request.
    """
    def _send():
        try:
            # Enviar email
            email_message.send(fail_silently=False)
        except Exception as e:
            logger.error(f"Error: {str(e)}")
    
    # Enviar en thread separado
    thread = threading.Thread(target=_send)
    thread.daemon = True
    thread.start()
```

**Beneficios:**
- ✅ No bloquea la respuesta HTTP
- ✅ Usuario ve "Email enviado" inmediatamente
- ✅ Si falla el SMTP, no afecta la app
- ✅ Workers de Render no se caen

### 2. **Timeout reducido** (10 segundos)

```python
EMAIL_TIMEOUT = 10  # Falla rápido si hay problemas
```

**Beneficios:**
- ✅ Si hay problema de conexión, falla en 10 seg (no 30)
- ✅ Thread termina rápido
- ✅ No consume recursos

---

## 🧪 Cómo Funciona Ahora

### **Flujo Anterior (Bloqueante):**
```
Usuario → Submit → Django intenta enviar → [ESPERA 30 SEG] → Timeout → Worker se cae ❌
```

### **Flujo Nuevo (Asíncrono):**
```
Usuario → Submit → Django programa envío → Responde "Enviado" ✅
                                          ↓
                                    [Background Thread]
                                          ↓
                                    Intenta enviar
                                          ↓
                                    ✅ Éxito o ❌ Falla
                                    (No afecta la app)
```

---

## 🚀 Deploy

### 1. Commit y Push:
```bash
git add .
git commit -m "Fix: Envío asíncrono de emails para evitar crashes"
git push
```

### 2. Render hará deploy automático

### 3. Probá:
- Ve a tu app en producción
- Intentá recuperar contraseña
- Debería responder **inmediatamente** con "Email enviado"
- La página **NO debería caerse**

---

## 🔍 Verificación

### **Síntomas de que funciona:**
- ✅ Página responde inmediatamente
- ✅ Muestra "Hemos enviado el email..."
- ✅ No se cae la app
- ✅ Logs de Render muestran "Email programado para..."

### **Si el email NO llega:**
- ⚠️ La app sigue funcionando (no se cae)
- ⚠️ Logs muestran error de SMTP
- ⚠️ Pero el usuario ve "Email enviado" (para no exponer info)

---

## 🐛 Troubleshooting

### "La página sigue cayéndose"
```
❌ Problema: Otro componente está fallando
✅ Solución:
1. Revisá logs de Render
2. Buscá errores NO relacionados con email
3. Puede ser problema de BD, memoria, etc.
```

### "Email no llega pero app funciona"
```
✅ Buena noticia: El fix funciona (app no se cae)
❌ Problema: Credenciales SMTP incorrectas

Solución:
1. Revisá logs: "Error al enviar email a..."
2. Verificá EMAIL_HOST_PASSWORD en Render
3. Probá con puerto 465 (SSL) en lugar de 587 (TLS)
4. Considerá cambiar a SendGrid
```

### "Email llega pero tarda mucho"
```
✅ Normal: Los threads pueden tardar 10-30 segundos
⚠️ Si tarda más de 1 minuto, hay problema de conexión

Solución:
1. Verificá EMAIL_TIMEOUT (debería ser 10)
2. Probá con otro puerto (465)
3. Probá con otro servicio (SendGrid)
```

---

## 📊 Comparativa

| Aspecto | Antes (Síncrono) | Ahora (Asíncrono) |
|---------|------------------|-------------------|
| **Tiempo respuesta** | 30+ segundos | < 1 segundo |
| **App se cae si falla** | ✅ Sí | ❌ No |
| **Worker bloqueado** | ✅ Sí | ❌ No |
| **UX** | ❌ Mala (espera) | ✅ Buena (inmediata) |
| **Logs de errores** | ✅ Sí | ✅ Sí |

---

## 🎯 Próximos Pasos

### **Si funciona:**
1. ✅ Dejalo así
2. ✅ Monitoreá logs para ver si emails se envían
3. ✅ Si no llegan, arreglá credenciales SMTP

### **Si sigue cayéndose:**
1. Compartí logs de Render
2. Puede ser otro problema (no email)
3. Revisá memoria, BD, etc.

### **Si querés mejorar más:**
1. Usar Celery + Redis para cola de emails
2. Usar API de Resend (no SMTP)
3. Usar servicio externo de emails

---

## 💡 Notas Técnicas

### **¿Por qué threading y no async/await?**
- Django views no son async por defecto
- Threading es más simple para este caso
- Funciona bien para emails (no es CPU-intensive)

### **¿Es seguro?**
- ✅ Sí, para emails
- ✅ Threads daemon se limpian automáticamente
- ✅ No hay race conditions (cada email es independiente)

### **¿Limitaciones?**
- Si Render reinicia el worker, emails pendientes se pierden
- Para producción seria, usar Celery + Redis
- Pero para MVP, threading es suficiente

---

¿Dudas? Hacé deploy y probá. Si sigue fallando, compartí los logs.

