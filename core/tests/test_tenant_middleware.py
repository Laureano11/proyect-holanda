from django.test import TestCase, RequestFactory
from django.test import override_settings
from django.core.cache import cache

from core.middleware import TenantMiddleware
from core.models import Complejo


class TenantMiddlewareHsDomainTest(TestCase):
    def setUp(self):
        # Evitar interferencia entre tests por caché de defaults
        cache.clear()
        self.factory = RequestFactory()
        self.middleware = TenantMiddleware(lambda r: None)

    def test_resuelve_desde_hs_complejo_tld(self):
        complejo = Complejo.objects.create(
            nombre="Complejo 4",
            slug="complejo4",
            subdominio="complejo4",
            direccion="X",
            activo=True,
        )

        request = self.factory.get("/", HTTP_HOST="hs.complejo4.com")
        self.middleware(request)

        self.assertEqual(request.complejo_actual, complejo)

    def test_resuelve_desde_www_hs_complejo_tld(self):
        complejo = Complejo.objects.create(
            nombre="Complejo 5",
            slug="complejo5",
            subdominio="complejo5",
            direccion="X",
            activo=True,
        )

        request = self.factory.get("/", HTTP_HOST="www.hs.complejo5.com")
        self.middleware(request)

        self.assertEqual(request.complejo_actual, complejo)

    def test_host_sin_hs_usa_fallback_activo(self):
        complejo_activo = Complejo.objects.create(
            nombre="Activo",
            slug="activo",
            subdominio="activo",
            direccion="X",
            activo=True,
        )

        request = self.factory.get("/", HTTP_HOST="otrodominio.com")
        self.middleware(request)

        self.assertEqual(request.complejo_actual, complejo_activo)

    def test_host_local_resuelve_por_slug(self):
        complejo_local = Complejo.objects.create(
            nombre="Local",
            slug="canchita",
            subdominio="canchita",
            direccion="X",
            activo=True,
        )

        request = self.factory.get("/", HTTP_HOST="canchita.local")
        self.middleware(request)

        self.assertEqual(request.complejo_actual, complejo_local)

    def test_sin_activos_toma_primer_existente(self):
        # Crear un complejo inactivo; será el primero existente
        complejo_inactivo = Complejo.objects.create(
            nombre="Inactivo",
            slug="inactivo",
            subdominio="inactivo",
            direccion="X",
            activo=False,
        )

        request = self.factory.get("/", HTTP_HOST="hs.sinmatch.com")
        self.middleware(request)

        self.assertEqual(request.complejo_actual, complejo_inactivo)


@override_settings(TENANT_BASE_DOMAINS=["hasselt.com"])
class TenantMiddlewareBaseDomainTest(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.middleware = TenantMiddleware(lambda r: None)

    def test_resuelve_desde_tenant_hasselt_com(self):
        complejo = Complejo.objects.create(
            nombre="Complejo Hasselt",
            slug="nombrecomplejo",
            subdominio="nombrecomplejo",
            direccion="X",
            activo=True,
        )

        request = self.factory.get("/", HTTP_HOST="nombrecomplejo.hasselt.com")
        self.middleware(request)

        self.assertEqual(request.complejo_actual, complejo)

    def test_resuelve_desde_www_tenant_hasselt_com(self):
        complejo = Complejo.objects.create(
            nombre="Complejo Hasselt 2",
            slug="nombrecomplejo2",
            subdominio="nombrecomplejo2",
            direccion="X",
            activo=True,
        )

        request = self.factory.get("/", HTTP_HOST="www.nombrecomplejo2.hasselt.com")
        self.middleware(request)

        self.assertEqual(request.complejo_actual, complejo)

    def test_host_base_hasselt_com_usa_fallback(self):
        complejo_activo = Complejo.objects.create(
            nombre="Activo",
            slug="activo",
            subdominio="activo",
            direccion="X",
            activo=True,
        )

        request = self.factory.get("/", HTTP_HOST="hasselt.com")
        self.middleware(request)

        self.assertEqual(request.complejo_actual, complejo_activo)


@override_settings(TENANT_DEFAULT_HOSTS=["proyect-holanda.onrender.com"])
class TenantMiddlewareDefaultHostsTest(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.middleware = TenantMiddleware(lambda r: None)

    def test_onrender_host_usa_complejo_default(self):
        # Si hay un único complejo, el default debe ser ese.
        complejo = Complejo.objects.create(
            nombre="Único",
            slug="unico",
            subdominio="unico",
            direccion="X",
            activo=True,
        )

        request = self.factory.get("/", HTTP_HOST="proyect-holanda.onrender.com")
        self.middleware(request)

        self.assertEqual(request.complejo_actual, complejo)

