"""Pruebas de la interfaz de gestión de ediciones (solo personal)."""
from datetime import timedelta

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Categoria, Edicion, Votacion

User = get_user_model()


class GestionEdicionesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user("staff@example.com", "staff@example.com", "Clave-Segura-2027", is_staff=True)
        cls.staff.groups.add(Group.objects.get(name="Administrador"))  # perfil con permisos (RN-10)
        cls.staff_sin_permisos = User.objects.create_user("sp@example.com", "sp@example.com", "Clave-Segura-2027", is_staff=True)
        cls.votante = User.objects.create_user("v@example.com", "v@example.com", "Clave-Segura-2027")
        cls.edicion = Edicion.objects.create(nombre="Festival", anio=2027)

    def test_anonimo_va_al_login(self):
        r = self.client.get(reverse("festival:gestion_ediciones"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("cuentas:login"), r["Location"])

    def test_votante_comun_recibe_403(self):
        self.client.force_login(self.votante)
        self.assertEqual(self.client.get(reverse("festival:gestion_ediciones")).status_code, 403)

    def test_personal_ve_activas_e_inactivas(self):
        Edicion.objects.create(nombre="Antigua", anio=2020, activa=False)
        self.client.force_login(self.staff)
        r = self.client.get(reverse("festival:gestion_ediciones"))
        self.assertContains(r, "2027")
        self.assertContains(r, "Inactiva")

    def test_crear_edicion_queda_en_auditoria(self):
        self.client.force_login(self.staff)
        r = self.client.post(reverse("festival:gestion_edicion_nueva"),
                             {"nombre": "Festival", "anio": 2028, "descripcion": "", "activa": "on"})
        self.assertRedirects(r, reverse("festival:gestion_ediciones"))
        nueva = Edicion.objects.get(anio=2028)
        self.assertTrue(LogEntry.objects.filter(object_id=str(nueva.pk), user=self.staff).exists())

    def test_anio_repetido_se_rechaza(self):
        self.client.force_login(self.staff)
        r = self.client.post(reverse("festival:gestion_edicion_nueva"), {"nombre": "X", "anio": 2027})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Edicion.objects.filter(anio=2027).count(), 1)

    def test_alternar_solo_por_post_y_avisa_si_hay_votaciones_abiertas(self):
        ahora = timezone.now()
        cat = Categoria.objects.create(edicion=self.edicion, nombre="Piquería")
        Votacion.objects.create(categoria=cat, nombre="V", estado=Votacion.Estado.ABIERTA,
                                fecha_apertura=ahora - timedelta(days=1), fecha_cierre=ahora + timedelta(days=1))
        self.client.force_login(self.staff)
        url = reverse("festival:gestion_edicion_alternar", args=[self.edicion.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        r = self.client.post(url, follow=True)
        self.edicion.refresh_from_db()
        self.assertFalse(self.edicion.activa)
        self.assertContains(r, "votación(es) abierta(s)")

    def test_personal_sin_permisos_recibe_403(self):
        """RN-10: ser personal no basta; hacen falta los permisos del perfil Administrador."""
        self.client.force_login(self.staff_sin_permisos)
        for nombre, args in [("festival:gestion_ediciones", []), ("festival:gestion_edicion_nueva", []),
                             ("festival:gestion_edicion_editar", [self.edicion.pk])]:
            self.assertEqual(self.client.get(reverse(nombre, args=args)).status_code, 403)
        r = self.client.post(reverse("festival:gestion_edicion_alternar", args=[self.edicion.pk]))
        self.assertEqual(r.status_code, 403)
        self.edicion.refresh_from_db()
        self.assertTrue(self.edicion.activa)

    def test_grupo_administrador_no_puede_eliminar_ediciones_ni_categorias(self):
        permisos = set(Group.objects.get(name="Administrador").permissions.values_list("codename", flat=True))
        self.assertNotIn("delete_edicion", permisos)
        self.assertNotIn("delete_categoria", permisos)
        self.assertIn("view_logentry", permisos)


class PanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("a@example.com", "a@example.com", "Clave-Segura-2027", is_staff=True)
        cls.admin.groups.add(Group.objects.get(name="Administrador"))
        cls.sin_auditoria = User.objects.create_user("b@example.com", "b@example.com", "Clave-Segura-2027", is_staff=True)
        cls.votante = User.objects.create_user("v@example.com", "v@example.com", "Clave-Segura-2027")

    def test_panel_exige_personal(self):
        self.assertEqual(self.client.get(reverse("festival:gestion_panel")).status_code, 302)
        self.client.force_login(self.votante)
        self.assertEqual(self.client.get(reverse("festival:gestion_panel")).status_code, 403)

    def test_panel_sin_acciones_muestra_mensaje(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("festival:gestion_panel")), "Aún no hay acciones registradas")  # CU-08 A1

    def test_panel_muestra_actividad_reciente(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("festival:gestion_edicion_nueva"), {"nombre": "Festival", "anio": 2030, "activa": "on"})
        r = self.client.get(reverse("festival:gestion_panel"))
        self.assertContains(r, "Creó")
        self.assertContains(r, "2030")

    def test_panel_sin_permiso_de_auditoria(self):
        self.client.force_login(self.sin_auditoria)
        self.assertContains(self.client.get(reverse("festival:gestion_panel")), "No tiene permiso para consultar")  # CU-08 A2


class VistaPreviaPersonalTests(TestCase):
    """«Ver en el sitio» de Django Admin: el personal previsualiza lo no público; el público recibe 404."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user("st@example.com", "st@example.com", "Clave-Segura-2027", is_staff=True)
        cls.staff.groups.add(Group.objects.get(name="Administrador"))
        cls.staff_sin_permisos = User.objects.create_user("sp2@example.com", "sp2@example.com", "Clave-Segura-2027", is_staff=True)
        cls.edicion = Edicion.objects.create(nombre="Festival", anio=2027)
        cls.categoria = Categoria.objects.create(edicion=cls.edicion, nombre="Piquería")
        ahora = timezone.now()
        cls.borrador = Votacion.objects.create(categoria=cls.categoria, nombre="Borrador secreto",
                                               fecha_apertura=ahora + timedelta(days=1),
                                               fecha_cierre=ahora + timedelta(days=5))
        cls.cat_inactiva = Categoria.objects.create(edicion=cls.edicion, nombre="Oculta", activa=False)
        cls.ed_inactiva = Edicion.objects.create(nombre="Antigua", anio=2020, activa=False)

    def urls(self):
        return [
            reverse("festival:votacion", args=[self.borrador.pk]),
            reverse("festival:categoria", args=[self.cat_inactiva.pk]),
            reverse("festival:edicion", args=[self.ed_inactiva.pk]),
        ]

    def test_anonimo_recibe_404(self):
        for url in self.urls():
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_personal_sin_permiso_de_lectura_recibe_404(self):
        self.client.force_login(self.staff_sin_permisos)
        for url in self.urls():
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_personal_con_permiso_ve_vista_previa_con_aviso(self):
        self.client.force_login(self.staff)
        for url in self.urls():
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertContains(r, "Vista previa del personal")

    def test_contenido_publico_no_muestra_aviso_ni_al_personal(self):
        self.client.force_login(self.staff)
        r = self.client.get(reverse("festival:categoria", args=[self.categoria.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Vista previa del personal")
