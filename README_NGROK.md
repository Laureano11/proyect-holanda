# 🌐 Compartir tu App con ngrok

## ¿Qué es ngrok?
ngrok crea un túnel seguro que expone tu servidor local a internet, generando un link público que podés compartir con cualquiera.

---

## 🚀 Opción 1: ngrok Cloud (Más Fácil - Recomendado)

### 1. Crear cuenta en ngrok
1. Andá a https://ngrok.com y creá una cuenta gratis
2. Verificá tu email

### 2. Instalar ngrok
```bash
# En Mac con Homebrew:
brew install ngrok/ngrok/ngrok

# O descargar desde: https://ngrok.com/download
```

### 3. Autenticarte
```bash
ngrok config add-authtoken TU_TOKEN_AQUI
```
*(El token lo encontrás en: https://dashboard.ngrok.com/get-started/your-authtoken)*

### 4. Levantar tu servidor Django
```bash
source venv/bin/activate
python3 manage.py runserver
```

### 5. En otra terminal, ejecutar ngrok
```bash
ngrok http 8000
```

### 6. Copiar el link
ngrok te mostrará algo como:
```
Forwarding  https://abc123.ngrok-free.app -> http://localhost:8000
```

**Ese link `https://abc123.ngrok-free.app` es el que compartís con tus amigos por WhatsApp!** 📱

---

## 🚀 Opción 2: ngrok con Python (Automático)

### 1. Instalar pyngrok
```bash
source venv/bin/activate
pip install pyngrok
```

### 2. Configurar tu authtoken
```bash
ngrok config add-authtoken TU_TOKEN_AQUI
```

### 3. Ejecutar el script
```bash
python3 run_with_ngrok.py
```

Este script levanta Django y ngrok automáticamente.

---

## ⚙️ Configuración de Django

Para que funcione con ngrok, necesitás permitir el dominio de ngrok en `ALLOWED_HOSTS`.

**Opción A: Permitir todos los hosts (solo desarrollo)**
En `config/settings.py`, cambiá:
```python
ALLOWED_HOSTS = ['*']  # Solo para desarrollo con ngrok
```

**Opción B: Agregar el dominio específico**
Cada vez que ngrok genere un link nuevo, agregalo a `ALLOWED_HOSTS` o usá `'*'` para desarrollo.

---

## 📱 Compartir con tus amigos

1. Ejecutá ngrok y copiá el link (ej: `https://abc123.ngrok-free.app`)
2. Compartilo por WhatsApp: "Probá mi app: https://abc123.ngrok-free.app"
3. ¡Listo! Pueden acceder desde cualquier lugar con internet

---

## ⚠️ Importante

- **Solo para desarrollo/testing**: No uses esto en producción
- **Link temporal**: El link cambia cada vez que reiniciás ngrok (a menos que tengas plan pago)
- **Límite de conexiones**: Plan gratis tiene límites, pero suficiente para probar con amigos
- **Seguridad**: Cualquiera con el link puede acceder, solo compartilo con personas de confianza

---

## 🐛 Solución de Problemas

### "Invalid Host header"
Agregá `ALLOWED_HOSTS = ['*']` en `settings.py` (solo para desarrollo)

### "ngrok: command not found"
Instalá ngrok: `brew install ngrok/ngrok/ngrok`

### "Session expired"
Necesitás autenticarte: `ngrok config add-authtoken TU_TOKEN`

---

## 💡 Tips

- **Link fijo**: Con plan pago podés tener un link que no cambia
- **Inspeccionar tráfico**: ngrok tiene un dashboard web para ver las requests
- **HTTPS gratis**: ngrok te da HTTPS automáticamente

