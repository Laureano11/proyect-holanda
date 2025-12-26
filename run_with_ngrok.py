#!/usr/bin/env python3
"""
Script para levantar Django + ngrok automáticamente.
Ejecutar: python3 run_with_ngrok.py
"""

import os
import sys
import time
import subprocess
import threading

def run_django():
    """Ejecuta el servidor Django."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        subprocess.run([sys.executable, 'manage.py', 'runserver'], check=True)
    except KeyboardInterrupt:
        print("\n✅ Servidor Django detenido")

def run_ngrok():
    """Ejecuta ngrok."""
    try:
        # Esperar un poco para que Django arranque
        time.sleep(2)
        subprocess.run(['ngrok', 'http', '8000'], check=True)
    except KeyboardInterrupt:
        print("\n✅ ngrok detenido")
    except FileNotFoundError:
        print("\n❌ ERROR: ngrok no está instalado")
        print("Instalá ngrok con: brew install ngrok/ngrok/ngrok")
        print("O descargalo desde: https://ngrok.com/download")
        sys.exit(1)

def main():
    print("\n" + "="*60)
    print("🚀 LEVANTANDO DJANGO + NGROK")
    print("="*60)
    print("\n📝 Pasos:")
    print("   1. Asegurate de tener ngrok instalado y autenticado")
    print("   2. El servidor Django se levantará en http://localhost:8000")
    print("   3. ngrok generará un link público (ej: https://abc123.ngrok-free.app)")
    print("   4. Copiá ese link y compartilo con tus amigos")
    print("\n⚠️  Para detener: Presioná Ctrl+C")
    print("="*60 + "\n")
    
    # Verificar que ngrok esté instalado
    try:
        subprocess.run(['ngrok', 'version'], 
                      stdout=subprocess.DEVNULL, 
                      stderr=subprocess.DEVNULL, 
                      check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("❌ ERROR: ngrok no está instalado o no está en el PATH")
        print("\n📥 Instalá ngrok:")
        print("   brew install ngrok/ngrok/ngrok")
        print("\n🔑 Luego autenticate:")
        print("   ngrok config add-authtoken TU_TOKEN")
        print("   (El token lo encontrás en: https://dashboard.ngrok.com/get-started/your-authtoken)")
        sys.exit(1)
    
    # Ejecutar Django en un thread
    django_thread = threading.Thread(target=run_django, daemon=True)
    django_thread.start()
    
    # Ejecutar ngrok en el thread principal
    try:
        run_ngrok()
    except KeyboardInterrupt:
        print("\n\n✅ Todo detenido correctamente")

if __name__ == '__main__':
    main()

