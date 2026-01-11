from django.test import TestCase, RequestFactory
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

