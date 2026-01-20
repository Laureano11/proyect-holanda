"""
Context processors generales de la app core.
"""

from django.conf import settings


def terms_context_processor(request):
    """
    Inyecta banderas para el modal de Términos y Condiciones.
    """
    user = getattr(request, "user", None)
    current_version = getattr(settings, "TERMS_VERSION", 1)

    if user is None or not user.is_authenticated:
        return {
            "show_terms_modal": False,
            "terms_version_current": current_version,
            "terms_version_accepted": None,
        }

    accepted_version = getattr(user, "terms_version_accepted", 0) or 0
    show_modal = accepted_version < current_version

    return {
        "show_terms_modal": show_modal,
        "terms_version_current": current_version,
        "terms_version_accepted": accepted_version,
    }

