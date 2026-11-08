"""Pruebas automatizadas de modelos y vistas públicas."""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Categoria, Edicion, Opcion, Votacion


class BaseDatos(TestCase):
    """Crea una jerarquía completa Edición → Categoría → Votación → Opción."""

    @classmethod
    def setUpTestData(cls):
        ahora = timezone.now()
        cls.edicion = Edicion.objects.create(nombre="Festival", anio=2027)
        cls.categoria = Categoria.objects.create(edicion=cls.edicion, nombre="Piquería", orden=1)
        cls.abierta = Votacion.objects.create(
            categoria=cls.categoria, nombre="Abierta",
            fecha_apertura=ahora - timedelta(days=1), fecha_cierre=ahora + timedelta(days=1),
            estado=Votacion.Estado.ABIERTA,
        )
        cls.borrador = Votacion.objects.create(
            categoria=cls.categoria, nombre="Borrador",
            fecha_apertura=ahora + timedelta(days=1), fecha_cierre=ahora + timedelta(days=2),
        )
        cls.op1 = Opcion.objects.create(votacion=cls.abierta, nombre="A", orden=1)
        cls.op_inactiva = Opcion.objects.create(votacion=cls.abierta, nombre="B", orden=2, activa=False)


class ModelosTests(BaseDatos):
    def test_relaciones_en_cascada(self):
        self.assertEqual(self.edicion.categorias.count(), 1)
        self.assertEqual(self.categoria.votaciones.count(), 2)
        self.edicion.delete()
        self.assertEqual(Opcion.objects.count(), 0)  # se eliminó toda la jerarquía

    def test_anio_unico(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Edicion.objects.create(nombre="Otra", anio=2027)

    def test_categoria_duplicada_en_edicion(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Categoria.objects.create(edicion=self.edicion, nombre="Piquería")

    def test_opcion_duplicada_en_votacion(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Opcion.objects.create(votacion=self.abierta, nombre="A")

    def test_cierre_debe_ser_posterior_a_apertura_en_clean_y_en_bd(self):
        ahora = timezone.now()
        malo = Votacion(categoria=self.categoria, nombre="X", fecha_apertura=ahora, fecha_cierre=ahora)
        with self.assertRaises(ValidationError):
            malo.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            malo.save()  # la restricción CHECK de la BD lo impide aunque se omita clean()

    def test_estado_publico_proximamente_y_cerrada(self):
        ahora = timezone.now()
        futura = Votacion(categoria=self.categoria, nombre="F", estado=Votacion.Estado.ABIERTA,
                          fecha_apertura=ahora + timedelta(days=1), fecha_cierre=ahora + timedelta(days=2))
        self.assertEqual(futura.estado_publico, "proximamente")
        self.assertEqual(futura.estado_publico_display, "Próximamente")
        vencida = Votacion(categoria=self.categoria, nombre="V", estado=Votacion.Estado.ABIERTA,
                           fecha_apertura=ahora - timedelta(days=2), fecha_cierre=ahora - timedelta(days=1))
        self.assertEqual(vencida.estado_publico, "cerrada")

    def test_puede_abrirse_requiere_opciones(self):
        self.assertTrue(self.abierta.puede_abrirse)
        self.assertFalse(self.borrador.puede_abrirse)  # CU-06 A2: sin opciones no se abre

    def test_edicion_vigente(self):
        Edicion.objects.create(nombre="Anterior", anio=2026)
        self.assertEqual(Edicion.objects.vigente(), self.edicion)
        Edicion.objects.all().update(activa=False)
        self.assertIsNone(Edicion.objects.vigente())

    def test_esta_abierta(self):
        self.assertTrue(self.abierta.esta_abierta)
        self.assertFalse(self.borrador.esta_abierta)
        self.abierta.fecha_cierre = timezone.now() - timedelta(minutes=1)
        self.assertFalse(self.abierta.esta_abierta)  # estado abierta pero fuera de periodo (RN-03)


class VistasTests(BaseDatos):
    def test_inicio_muestra_edicion_vigente_con_categorias(self):
        Edicion.objects.create(nombre="Oculta", anio=2030, activa=False)
        r = self.client.get(reverse("festival:inicio"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Edición vigente")
        self.assertContains(r, "Piquería")
        self.assertNotContains(r, "Oculta")

    def test_inicio_sin_ediciones_activas(self):
        Edicion.objects.all().update(activa=False)
        r = self.client.get(reverse("festival:inicio"))
        self.assertContains(r, "no hay una edición activa")  # CU-01 A1

    def test_listado_de_ediciones(self):
        Edicion.objects.create(nombre="Oculta", anio=2020, activa=False)
        r = self.client.get(reverse("festival:ediciones"))
        self.assertContains(r, "Festival")
        self.assertNotContains(r, "Oculta")

    def test_categoria_inactiva_devuelve_404(self):
        self.categoria.activa = False
        self.categoria.save()
        self.assertEqual(self.client.get(reverse("festival:categoria", args=[self.categoria.pk])).status_code, 404)

    def test_votacion_proximamente_no_ofrece_votar(self):
        """Entrega 3: una votación que aún no abre no muestra el formulario de voto."""
        self.borrador.estado = Votacion.Estado.ABIERTA
        self.borrador.save()
        r = self.client.get(reverse("festival:votacion", args=[self.borrador.pk]))
        self.assertContains(r, "Próximamente")
        self.assertContains(r, "La votación aún no está abierta")
        self.assertNotContains(r, 'name="opcion"')

    def test_edicion_y_categoria(self):
        r = self.client.get(reverse("festival:edicion", args=[self.edicion.pk]))
        self.assertContains(r, "Piquería")
        r = self.client.get(reverse("festival:categoria", args=[self.categoria.pk]))
        self.assertContains(r, "Abierta")
        self.assertNotContains(r, "Borrador")  # los borradores no son públicos

    def test_votacion_muestra_solo_opciones_activas(self):
        r = self.client.get(reverse("festival:votacion", args=[self.abierta.pk]))
        self.assertContains(r, "<strong>A</strong>", html=True)
        self.assertNotContains(r, "<strong>B</strong>", html=True)

    def test_borrador_devuelve_404(self):
        r = self.client.get(reverse("festival:votacion", args=[self.borrador.pk]))
        self.assertContains(r, "Página no encontrada", status_code=404)  # usa la plantilla 404.html

    def test_edicion_inactiva_devuelve_404(self):
        self.edicion.activa = False
        self.edicion.save()
        r = self.client.get(reverse("festival:edicion", args=[self.edicion.pk]))
        self.assertEqual(r.status_code, 404)
