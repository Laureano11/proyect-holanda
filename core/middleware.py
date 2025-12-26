"""
Middleware de debug para diagnosticar problemas con ALLOWED_HOSTS.
"""

import json
import time
from django.conf import settings

class DebugAllowedHostsMiddleware:
    """Middleware para loguear información sobre ALLOWED_HOSTS."""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Loggear información del request
        try:
            with open('/Users/lauri11/Documents/project-holanda/.cursor/debug.log', 'a') as f:
                log_entry = {
                    "sessionId": "debug-session",
                    "timestamp": int(time.time() * 1000),
                    "location": "middleware.py",
                    "hypothesisId": "A",
                    "message": "Request recibido",
                    "data": {
                        "host": request.get_host(),
                        "allowed_hosts": list(settings.ALLOWED_HOSTS),
                        "path": request.path,
                        "method": request.method,
                    }
                }
                f.write(json.dumps(log_entry) + '\n')
        except: pass
        
        response = self.get_response(request)
        return response

