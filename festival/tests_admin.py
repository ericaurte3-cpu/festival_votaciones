"""Pruebas de las reglas del panel de administración (CU-05, CU-06) y de la auditoría."""
from datetime import timedelta

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Categoria, Edicion, Opcion, Votacion

User = get_user_model()


class AdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("admin", "admin@example.com", "Clave-Segura-2027")
        ahora = timezone.now()
        ed = Edicion.objects.create(nombre="Festival", anio=2027)
        cat = Categoria.objects.create(edicion=ed, nombre="Piquería")
        cls.sin_opciones = Votacion.objects.create(
            categoria=cat, nombre="Sin opciones",
            fecha_apertura=ahora, fecha_cierre=ahora + timedelta(days=1))
        cls.con_opciones = Votacion.objects.create(
            categoria=cat, nombre="Con opciones",
            fecha_apertura=ahora, fecha_cierre=ahora + timedelta(days=1))
        Opcion.objects.create(votacion=cls.con_opciones, nombre="A")

    def setUp(self):
        self.client.force_login(self.admin)

    def accion(self, nombre, *votaciones):
        return self.client.post(reverse("admin:festival_votacion_changelist"), {
            "action": nombre, "_selected_action": [v.pk for v in votaciones]}, follow=True)

    def test_abrir_omite_votaciones_sin_opciones(self):
        self.accion("abrir", self.sin_opciones, self.con_opciones)
        self.sin_opciones.refresh_from_db()
        self.con_opciones.refresh_from_db()
        self.assertEqual(self.sin_opciones.estado, Votacion.Estado.BORRADOR)  # CU-06 A2
        self.assertEqual(self.con_opciones.estado, Votacion.Estado.ABIERTA)

    def test_cambio_de_estado_queda_en_auditoria(self):
        self.accion("abrir", self.con_opciones)
        self.assertTrue(LogEntry.objects.filter(object_id=str(self.con_opciones.pk), user=self.admin).exists())

    def test_auditoria_es_de_solo_lectura(self):
        self.accion("abrir", self.con_opciones)
        url = reverse("admin:admin_logentry_changelist")
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:admin_logentry_add")).status_code, 403)

    def test_publicar_solo_desde_cerrada(self):
        self.accion("publicar", self.con_opciones)  # está en borrador: no debe publicarse
        self.con_opciones.refresh_from_db()
        self.assertEqual(self.con_opciones.estado, Votacion.Estado.BORRADOR)
        self.accion("abrir", self.con_opciones)
        self.accion("cerrar", self.con_opciones)
        self.accion("publicar", self.con_opciones)
        self.con_opciones.refresh_from_db()
        self.assertEqual(self.con_opciones.estado, Votacion.Estado.PUBLICADA)

    def test_no_se_reabre_una_votacion_cerrada(self):
        self.accion("abrir", self.con_opciones)
        self.accion("cerrar", self.con_opciones)
        self.accion("abrir", self.con_opciones)
        self.con_opciones.refresh_from_db()
        self.assertEqual(self.con_opciones.estado, Votacion.Estado.CERRADA)

    def test_clean_rechaza_transicion_invalida(self):
        from django.core.exceptions import ValidationError
        self.con_opciones.estado = Votacion.Estado.PUBLICADA  # borrador -> publicada
        with self.assertRaises(ValidationError):
            self.con_opciones.full_clean()

    def test_edicion_con_categorias_no_se_elimina(self):
        ed = Edicion.objects.get(anio=2027)
        r = self.client.post(reverse("admin:festival_edicion_delete", args=[ed.pk]), {"post": "yes"})
        self.assertIn(r.status_code, (403, 200))
        self.assertTrue(Edicion.objects.filter(pk=ed.pk).exists())

    def test_votacion_no_borrador_no_se_elimina(self):
        self.accion("abrir", self.con_opciones)
        r = self.client.post(reverse("admin:festival_votacion_delete", args=[self.con_opciones.pk]), {"post": "yes"})
        self.assertIn(r.status_code, (403, 200))
        self.assertTrue(Votacion.objects.filter(pk=self.con_opciones.pk).exists())

    def test_borrador_si_se_elimina(self):
        self.client.post(reverse("admin:festival_votacion_delete", args=[self.sin_opciones.pk]), {"post": "yes"})
        self.assertFalse(Votacion.objects.filter(pk=self.sin_opciones.pk).exists())
