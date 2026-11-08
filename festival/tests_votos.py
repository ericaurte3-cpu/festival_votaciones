"""
Pruebas del módulo de votaciones (Entrega 3). Cada caso CP-xx corresponde a la tabla de
pruebas funcionales del enunciado; el nombre del método empieza por el código del caso.

Ejecutar:  python manage.py test festival.tests_votos -v 2
"""
import json
import threading
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from . import servicios
from .models import Categoria, Edicion, Opcion, Voto, Votacion

User = get_user_model()
CLAVE = "Clave-Segura-2027"


def crear_escenario(obj):
    """Crea edición, categorías, votaciones y opciones de prueba y los asigna a ``obj``.

    * Categoría A «Acordeonero» con DOS subeventos abiertos (vot_a1: 3 opciones, vot_a2: 2).
    * Categoría B «Piquería» con una votación abierta.
    * Categoría C con votación cerrada; D con votación en borrador; E inactiva; edición inactiva.
    """
    ahora = timezone.now()
    abierta = dict(fecha_apertura=ahora - timedelta(days=1), fecha_cierre=ahora + timedelta(days=1),
                   estado=Votacion.Estado.ABIERTA)

    obj.edicion = Edicion.objects.create(nombre="Festival", anio=2027)
    obj.cat_a = Categoria.objects.create(edicion=obj.edicion, nombre="Acordeonero", orden=1)
    obj.cat_b = Categoria.objects.create(edicion=obj.edicion, nombre="Piquería", orden=2)
    obj.cat_c = Categoria.objects.create(edicion=obj.edicion, nombre="Conjuntos", orden=3)
    obj.cat_d = Categoria.objects.create(edicion=obj.edicion, nombre="Inédita", orden=4)
    obj.cat_e = Categoria.objects.create(edicion=obj.edicion, nombre="Desactivada", orden=5, activa=False)

    obj.vot_a1 = Votacion.objects.create(categoria=obj.cat_a, nombre="Acordeonero · final", **abierta)
    obj.vot_a2 = Votacion.objects.create(categoria=obj.cat_a, nombre="Acordeonero · semifinal", **abierta)
    obj.vot_b = Votacion.objects.create(categoria=obj.cat_b, nombre="Piquería · final", **abierta)
    obj.vot_c = Votacion.objects.create(
        categoria=obj.cat_c, nombre="Conjuntos · final", fecha_apertura=ahora - timedelta(days=3),
        fecha_cierre=ahora - timedelta(days=1), estado=Votacion.Estado.CERRADA)
    obj.vot_d = Votacion.objects.create(
        categoria=obj.cat_d, nombre="Inédita · borrador", fecha_apertura=ahora + timedelta(days=1),
        fecha_cierre=ahora + timedelta(days=2), estado=Votacion.Estado.BORRADOR)
    obj.vot_e = Votacion.objects.create(categoria=obj.cat_e, nombre="Desactivada · final", **abierta)

    obj.ops_a1 = [Opcion.objects.create(votacion=obj.vot_a1, nombre=f"A1-{i}", orden=i) for i in (1, 2, 3)]
    obj.ops_a2 = [Opcion.objects.create(votacion=obj.vot_a2, nombre=f"A2-{i}", orden=i) for i in (1, 2)]
    obj.ops_b = [Opcion.objects.create(votacion=obj.vot_b, nombre=f"B-{i}", orden=i) for i in (1, 2)]
    obj.op_c = Opcion.objects.create(votacion=obj.vot_c, nombre="C-1")
    obj.op_d = Opcion.objects.create(votacion=obj.vot_d, nombre="D-1")
    obj.op_e = Opcion.objects.create(votacion=obj.vot_e, nombre="E-1")
    obj.op_inactiva = Opcion.objects.create(votacion=obj.vot_a1, nombre="A1-inactiva", orden=9, activa=False)

    obj.u1 = User.objects.create_user("u1@example.com", "u1@example.com", CLAVE)
    obj.u2 = User.objects.create_user("u2@example.com", "u2@example.com", CLAVE)


def votar(client, votacion, opcion_id, confirmar=True, extra=None):
    """POST al endpoint de voto (paso 2 si ``confirmar``). ``extra`` agrega campos al formulario."""
    datos = {"opcion": opcion_id, **(extra or {})}
    if confirmar:
        datos["confirmar"] = "1"
    return client.post(reverse("festival:votar", args=[votacion.pk]), datos)


def mensajes(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


class VotosBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        crear_escenario(cls)

    def setUp(self):
        self.client.force_login(self.u1)


class CP01VotoValidoTests(VotosBase):
    def test_cp01_voto_valido_se_registra_en_bd(self):
        """CP-01: usuario autenticado selecciona una opción válida → se registra un voto."""
        r = votar(self.client, self.vot_a1, self.ops_a1[0].pk)
        self.assertRedirects(r, reverse("festival:mis_votos"))
        voto = Voto.objects.get()
        self.assertEqual((voto.usuario, voto.opcion, voto.votacion), (self.u1, self.ops_a1[0], self.vot_a1))
        # La edición y la categoría se derivan de la opción en el servidor.
        self.assertEqual((voto.categoria, voto.edicion), (self.cat_a, self.edicion))
        self.assertIsNotNone(voto.emitido_en)

    def test_cp01_primer_paso_muestra_confirmacion_y_no_guarda(self):
        """La selección no registra nada: primero se muestra la pantalla de confirmación."""
        r = votar(self.client, self.vot_a1, self.ops_a1[1].pk, confirmar=False)
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "festival/confirmar_voto.html")
        self.assertContains(r, "A1-2")
        self.assertEqual(Voto.objects.count(), 0)

    def test_cp01_la_pagina_de_votacion_ofrece_el_formulario(self):
        r = self.client.get(self.vot_a1.get_absolute_url())
        self.assertContains(r, 'name="opcion"')
        self.assertContains(r, "csrfmiddlewaretoken")

    def test_cp01_campos_manipulados_se_ignoran(self):
        """El cliente no puede imponer edición, categoría ni votación: se derivan de la opción."""
        votar(self.client, self.vot_a1, self.ops_a1[0].pk,
              extra={"categoria": self.cat_b.pk, "edicion": 999, "votacion": self.vot_b.pk, "usuario": self.u2.pk})
        voto = Voto.objects.get()
        self.assertEqual((voto.usuario, voto.categoria, voto.votacion), (self.u1, self.cat_a, self.vot_a1))


class CP02VotoDuplicadoTests(VotosBase):
    def setUp(self):
        super().setUp()
        votar(self.client, self.vot_a1, self.ops_a1[0].pk)  # primer voto válido

    def test_cp02_segundo_voto_misma_votacion_otra_opcion(self):
        r = votar(self.client, self.vot_a1, self.ops_a1[1].pk)
        self.assertRedirects(r, self.vot_a1.get_absolute_url())
        self.assertTrue(any("Ya votaste" in m for m in mensajes(r)))
        self.assertEqual(Voto.objects.count(), 1)

    def test_cp02_segundo_voto_mismo_candidato(self):
        votar(self.client, self.vot_a1, self.ops_a1[0].pk)
        self.assertEqual(Voto.objects.count(), 1)

    def test_cp02_segundo_voto_en_otro_subevento_de_la_misma_categoria(self):
        """La regla es por categoría y edición, no por votación."""
        r = votar(self.client, self.vot_a2, self.ops_a2[0].pk)
        self.assertTrue(any("Ya votaste" in m for m in mensajes(r)))
        self.assertEqual(Voto.objects.count(), 1)
        self.assertEqual(Voto.objects.get().votacion, self.vot_a1)

    def test_cp02_el_paso_de_confirmacion_tampoco_deja_continuar(self):
        r = votar(self.client, self.vot_a2, self.ops_a2[0].pk, confirmar=False)
        self.assertEqual(r.status_code, 302)  # vuelve a la votación con un aviso, sin pantalla de confirmación

    def test_cp02_la_bd_rechaza_el_duplicado_aunque_se_salte_la_aplicacion(self):
        """Integridad en MySQL: un INSERT directo con otra opción viola la restricción UNIQUE."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            Voto.objects.create(usuario=self.u1, edicion=self.edicion, categoria=self.cat_a,
                                votacion=self.vot_a2, opcion=self.ops_a2[0])
        self.assertEqual(Voto.objects.count(), 1)

    def test_cp02_si_falla_la_validacion_previa_la_bd_sigue_protegiendo(self):
        """Simula la carrera: la consulta previa «no ve» el voto y el INSERT choca con el UNIQUE."""
        with mock.patch.object(servicios, "voto_del_usuario", return_value=None):
            with self.assertRaises(servicios.VotoDuplicado):
                servicios.registrar_voto(usuario=self.u1, votacion_id=self.vot_a2.pk, opcion_id=self.ops_a2[0].pk)
        self.assertEqual(Voto.objects.count(), 1)

    def test_cp02_la_pagina_informa_que_ya_voto(self):
        r = self.client.get(self.vot_a2.get_absolute_url())
        self.assertContains(r, "Ya votaste en esta categoría")
        self.assertNotContains(r, 'name="opcion"')


class CP03OtraCategoriaTests(VotosBase):
    def test_cp03_voto_en_categoria_diferente_se_permite(self):
        votar(self.client, self.vot_a1, self.ops_a1[0].pk)
        r = votar(self.client, self.vot_b, self.ops_b[0].pk)
        self.assertRedirects(r, reverse("festival:mis_votos"))
        self.assertEqual(Voto.objects.filter(usuario=self.u1).count(), 2)
        self.assertEqual(set(Voto.objects.values_list("categoria", flat=True)), {self.cat_a.pk, self.cat_b.pk})

    def test_cp03_otro_usuario_si_puede_votar_en_la_misma_categoria(self):
        votar(self.client, self.vot_a1, self.ops_a1[0].pk)
        otro = Client()
        otro.force_login(self.u2)
        votar(otro, self.vot_a1, self.ops_a1[0].pk)
        self.assertEqual(Voto.objects.count(), 2)

    def test_cp03_misma_categoria_en_otra_edicion_se_permite(self):
        """La unicidad incluye la edición: la misma categoría de otra edición es otro voto."""
        ahora = timezone.now()
        ed26 = Edicion.objects.create(nombre="Festival", anio=2026)
        cat26 = Categoria.objects.create(edicion=ed26, nombre="Acordeonero")
        vot26 = Votacion.objects.create(
            categoria=cat26, nombre="Acordeonero 2026", fecha_apertura=ahora - timedelta(days=1),
            fecha_cierre=ahora + timedelta(days=1), estado=Votacion.Estado.ABIERTA)
        op26 = Opcion.objects.create(votacion=vot26, nombre="X")
        votar(self.client, self.vot_a1, self.ops_a1[0].pk)
        votar(self.client, vot26, op26.pk)
        self.assertEqual(Voto.objects.filter(usuario=self.u1).count(), 2)


class CP04AutenticacionTests(VotosBase):
    def setUp(self):
        self.client.logout()  # anónimo

    def test_cp04_anonimo_es_redirigido_al_login_y_no_se_guarda_nada(self):
        r = votar(self.client, self.vot_a1, self.ops_a1[0].pk)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith(reverse("cuentas:login")))
        self.assertEqual(Voto.objects.count(), 0)

    def test_cp04_anonimo_no_ve_el_formulario_sino_el_enlace_para_iniciar_sesion(self):
        r = self.client.get(self.vot_a1.get_absolute_url())
        self.assertNotContains(r, 'name="opcion"')
        self.assertContains(r, "inicia sesión")

    def test_cp04_mis_votos_exige_sesion(self):
        r = self.client.get(reverse("festival:mis_votos"))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith(reverse("cuentas:login")))

    def test_cp04_usuario_inactivo_no_puede_votar(self):
        with self.assertRaises(servicios.UsuarioNoAutorizado):
            servicios.registrar_voto(usuario=User(username="x", is_active=False),
                                     votacion_id=self.vot_a1.pk, opcion_id=self.ops_a1[0].pk)

    def test_cp04_get_al_endpoint_de_voto_redirige_a_la_votacion(self):
        self.client.force_login(self.u1)
        r = self.client.get(reverse("festival:votar", args=[self.vot_a1.pk]))
        self.assertRedirects(r, self.vot_a1.get_absolute_url())


class CSRFTests(VotosBase):
    def test_voto_sin_token_csrf_es_rechazado(self):
        """Seguridad básica: el POST sin token CSRF recibe 403 y no registra nada."""
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.u1)
        r = cliente.post(reverse("festival:votar", args=[self.vot_a1.pk]),
                         {"opcion": self.ops_a1[0].pk, "confirmar": "1"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Voto.objects.count(), 0)


class CP05VotacionNoHabilitadaTests(VotosBase):
    def _rechazado(self, votacion, opcion):
        r = votar(self.client, votacion, opcion.pk)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Voto.objects.count(), 0)
        return r

    def test_cp05_votacion_cerrada(self):
        r = self._rechazado(self.vot_c, self.op_c)
        self.assertTrue(any("no está habilitada" in m for m in mensajes(r)))

    def test_cp05_votacion_en_borrador(self):
        self._rechazado(self.vot_d, self.op_d)

    def test_cp05_abierta_pero_fuera_de_periodo(self):
        """RN-03: llegada la fecha de cierre ya no recibe votos aunque el estado siga «abierta»."""
        Votacion.objects.filter(pk=self.vot_b.pk).update(fecha_cierre=timezone.now() - timedelta(minutes=1))
        self._rechazado(self.vot_b, self.ops_b[0])

    def test_cp05_abierta_pero_aun_no_inicia(self):
        Votacion.objects.filter(pk=self.vot_b.pk).update(fecha_apertura=timezone.now() + timedelta(hours=1),
                                                         fecha_cierre=timezone.now() + timedelta(hours=2))
        self._rechazado(self.vot_b, self.ops_b[0])

    def test_cp05_categoria_inactiva(self):
        self._rechazado(self.vot_e, self.op_e)

    def test_cp05_edicion_inactiva(self):
        Edicion.objects.filter(pk=self.edicion.pk).update(activa=False)
        self._rechazado(self.vot_a1, self.ops_a1[0])

    def test_cp05_votacion_inexistente(self):
        r = self.client.post(reverse("festival:votar", args=[999999]), {"opcion": 1, "confirmar": "1"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Voto.objects.count(), 0)


class CP06OpcionInvalidaTests(VotosBase):
    def test_cp06_opcion_de_otra_categoria(self):
        """Se envía a la votación de A una opción que pertenece a la categoría B."""
        r = votar(self.client, self.vot_a1, self.ops_b[0].pk)
        self.assertTrue(any("no es válida" in m for m in mensajes(r)))
        self.assertEqual(Voto.objects.count(), 0)

    def test_cp06_opcion_de_otro_subevento_de_la_misma_categoria(self):
        votar(self.client, self.vot_a1, self.ops_a2[0].pk)
        self.assertEqual(Voto.objects.count(), 0)

    def test_cp06_opcion_inactiva(self):
        votar(self.client, self.vot_a1, self.op_inactiva.pk)
        self.assertEqual(Voto.objects.count(), 0)

    def test_cp06_opcion_inexistente(self):
        votar(self.client, self.vot_a1, 987654)
        self.assertEqual(Voto.objects.count(), 0)

    def test_cp06_sin_opcion_o_con_dato_no_numerico(self):
        for datos in ({"confirmar": "1"}, {"opcion": "abc", "confirmar": "1"}, {"opcion": "-3", "confirmar": "1"}):
            r = self.client.post(reverse("festival:votar", args=[self.vot_a1.pk]), datos)
            self.assertEqual(r.status_code, 302)
        self.assertEqual(Voto.objects.count(), 0)

    def test_cp06_coherencia_del_modelo(self):
        """``Voto.clean()`` detecta combinaciones incoherentes aunque no pasen por el servicio."""
        incoherente = Voto(usuario=self.u1, edicion=self.edicion, categoria=self.cat_a,
                           votacion=self.vot_a1, opcion=self.ops_b[0])
        with self.assertRaises(ValidationError):
            incoherente.full_clean()


class CP07MisVotosTests(VotosBase):
    def test_cp07_lista_solo_las_categorias_votadas_por_el_usuario(self):
        votar(self.client, self.vot_a1, self.ops_a1[2].pk)
        votar(self.client, self.vot_b, self.ops_b[1].pk)
        otro = Client()
        otro.force_login(self.u2)
        votar(otro, self.vot_a1, self.ops_a1[0].pk)

        r = self.client.get(reverse("festival:mis_votos"))
        self.assertEqual(r.status_code, 200)
        votos = list(r.context["votos"])
        self.assertEqual({v.usuario for v in votos}, {self.u1})
        self.assertEqual({(v.categoria.nombre, v.opcion.nombre) for v in votos},
                         {("Acordeonero", "A1-3"), ("Piquería", "B-2")})
        self.assertContains(r, "A1-3")
        self.assertNotContains(r, "A1-1")  # el voto de otro usuario no aparece

    def test_cp07_sin_votos_muestra_mensaje(self):
        self.assertContains(self.client.get(reverse("festival:mis_votos")), "Todavía no has votado")

    def test_cp07_la_categoria_muestra_el_voto_previo(self):
        votar(self.client, self.vot_a1, self.ops_a1[0].pk)
        self.assertContains(self.client.get(self.cat_a.get_absolute_url()), "Ya votaste en esta categoría")


class CP08AdministracionTests(VotosBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin = User.objects.create_superuser("root@example.com", "root@example.com", CLAVE)
        cls.staff = User.objects.create_user("adm@example.com", "adm@example.com", CLAVE, is_staff=True)
        cls.staff.groups.add(Group.objects.get(name="Administrador"))
        cls.staff_sin_permisos = User.objects.create_user("sp@example.com", "sp@example.com", CLAVE, is_staff=True)

    def setUp(self):
        super().setUp()
        votar(self.client, self.vot_a1, self.ops_a1[0].pk)
        otro = Client()
        otro.force_login(self.u2)
        votar(otro, self.vot_b, self.ops_b[1].pk)

    def test_cp08_el_administrador_ve_los_votos_y_coinciden_con_la_bd(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("admin:festival_voto_changelist"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["cl"].result_count, Voto.objects.count())
        for voto in Voto.objects.select_related("usuario", "opcion"):
            self.assertContains(r, voto.usuario.username)
            self.assertContains(r, voto.opcion.nombre)

    def test_cp08_perfil_administrador_puede_consultar(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("admin:festival_voto_changelist")).status_code, 200)

    def test_cp08_personal_sin_permisos_no_puede_consultar(self):
        self.client.force_login(self.staff_sin_permisos)
        self.assertEqual(self.client.get(reverse("admin:festival_voto_changelist")).status_code, 403)

    def test_cp08_los_votos_son_de_solo_lectura(self):
        """Ni siquiera un superusuario puede agregar, editar o borrar votos desde el admin."""
        self.client.force_login(self.admin)
        voto = Voto.objects.first()
        self.assertEqual(self.client.get(reverse("admin:festival_voto_add")).status_code, 403)
        self.assertEqual(self.client.post(reverse("admin:festival_voto_delete", args=[voto.pk]),
                                          {"post": "yes"}).status_code, 403)
        self.assertEqual(Voto.objects.count(), 2)

    def test_cp08_el_panel_muestra_el_total_de_votos(self):
        self.client.force_login(self.staff)
        r = self.client.get(reverse("festival:gestion_panel"))
        self.assertEqual(r.context["total_votos"], 2)
        self.assertContains(r, "Consultar votos")

    def test_cp08_filtros_del_admin(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("admin:festival_voto_changelist"), {"categoria__id__exact": self.cat_a.pk})
        self.assertEqual(r.context["cl"].result_count, 1)


class CP10ApiCategoriasTests(VotosBase):
    url = "/api/categorias/"

    def setUp(self):
        self.client = Client()  # la API es pública: sin sesión

    def _json(self, **params):
        r = self.client.get(self.url, params)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"].split(";")[0], "application/json")
        return json.loads(r.content)

    def test_cp10_devuelve_json_valido_con_categorias_y_opciones_de_mysql(self):
        datos = self._json()
        self.assertEqual(datos["total"], len(datos["categorias"]))
        por_nombre = {c["nombre"]: c for c in datos["categorias"]}

        acordeonero = por_nombre["Acordeonero"]
        self.assertEqual(acordeonero["edicion"], {"id": self.edicion.pk, "nombre": "Festival", "anio": 2027})
        self.assertEqual({v["nombre"] for v in acordeonero["votaciones"]},
                         {"Acordeonero · final", "Acordeonero · semifinal"})
        final = next(v for v in acordeonero["votaciones"] if v["nombre"].endswith("final") and "semi" not in v["nombre"])
        self.assertEqual([o["nombre"] for o in final["opciones"]], ["A1-1", "A1-2", "A1-3"])
        self.assertEqual(acordeonero["total_opciones"], 5)
        self.assertTrue(final["acepta_votos"])
        self.assertEqual(final["estado"], "abierta")

    def test_cp10_los_datos_coinciden_con_la_base_de_datos(self):
        datos = self._json()
        opciones_api = {o["id"] for c in datos["categorias"] for v in c["votaciones"] for o in v["opciones"]}
        opciones_bd = set(Opcion.objects.filter(
            activa=True, votacion__categoria__activa=True, votacion__categoria__edicion__activa=True
        ).exclude(votacion__estado=Votacion.Estado.BORRADOR).values_list("pk", flat=True))
        self.assertEqual(opciones_api, opciones_bd)

    def test_cp10_no_expone_borradores_inactivos_ni_datos_de_usuarios(self):
        votar_cliente = Client()
        votar_cliente.force_login(self.u1)
        votar(votar_cliente, self.vot_a1, self.ops_a1[0].pk)
        crudo = self.client.get(self.url).content.decode()
        self.assertNotIn("D-1", crudo)             # opción de una votación en borrador
        self.assertNotIn("A1-inactiva", crudo)     # opción inactiva
        self.assertNotIn("Desactivada", crudo)     # categoría inactiva
        self.assertNotIn("u1@example.com", crudo)  # ningún dato de usuarios o votos
        self.assertNotIn("emitido", crudo)

    def test_cp10_filtro_por_edicion(self):
        otra = Edicion.objects.create(nombre="Festival", anio=2026)
        Categoria.objects.create(edicion=otra, nombre="Histórica")
        self.assertEqual({c["nombre"] for c in self._json(edicion=otra.pk)["categorias"]}, {"Histórica"})
        self.assertEqual(self._json(edicion=999999)["total"], 0)

    def test_cp10_parametro_invalido_responde_400_json(self):
        r = self.client.get(self.url, {"edicion": "abc"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", json.loads(r.content))

    def test_cp10_solo_acepta_get(self):
        for metodo in ("post", "put", "delete"):
            self.assertEqual(getattr(self.client, metodo)(self.url).status_code, 405)

    def test_cp10_consultas_constantes_sin_n_mas_1(self):
        with self.assertNumQueries(3):  # categorías + votaciones + opciones
            self.client.get(self.url)
        for i in range(5):  # más datos → mismas consultas
            c = Categoria.objects.create(edicion=self.edicion, nombre=f"Extra {i}")
            v = Votacion.objects.create(categoria=c, nombre=f"Extra {i}", fecha_apertura=timezone.now(),
                                        fecha_cierre=timezone.now() + timedelta(days=1),
                                        estado=Votacion.Estado.ABIERTA)
            Opcion.objects.create(votacion=v, nombre="o")
        with self.assertNumQueries(3):
            self.client.get(self.url)

    def test_cp10_texto_con_tildes_legible(self):
        self.assertIn("Piquería", self.client.get(self.url).content.decode("utf-8"))


class CP09ConcurrenciaTests(TransactionTestCase):
    """CP-09: solicitudes simultáneas del mismo usuario a la misma categoría → un solo voto.

    Usa ``TransactionTestCase`` (y no ``TestCase``) para que cada hilo, con su propia
    conexión a MySQL, vea y confirme datos reales; la restricción UNIQUE decide quién gana.
    """

    HILOS = 8

    def setUp(self):
        crear_escenario(self)

    def _disparar(self, objetivos):
        """Envía una solicitud por objetivo ``(votacion, opcion)`` exactamente a la vez."""
        barrera = threading.Barrier(len(objetivos))
        resultados, errores = [], []

        def trabajo(votacion, opcion):
            cliente = Client()
            cliente.force_login(self.u1)
            try:
                barrera.wait(timeout=10)
                r = votar(cliente, votacion, opcion.pk)
                resultados.append((r.status_code, mensajes(r)))
            except Exception as exc:  # noqa: BLE001 - se reporta en la aserción
                errores.append(repr(exc))
            finally:
                connection.close()  # cada hilo usa su propia conexión

        hilos = [threading.Thread(target=trabajo, args=o) for o in objetivos]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=60)
        return resultados, errores

    def test_cp09_solicitudes_simultaneas_a_la_misma_categoria_dejan_un_solo_voto(self):
        objetivos = [(self.vot_a1, self.ops_a1[i % 3]) for i in range(self.HILOS // 2)]
        objetivos += [(self.vot_a2, self.ops_a2[i % 2]) for i in range(self.HILOS // 2)]  # otro subevento
        resultados, errores = self._disparar(objetivos)

        self.assertEqual(errores, [], f"Ninguna solicitud debe terminar en error 500: {errores}")
        self.assertEqual(len(resultados), self.HILOS)
        self.assertEqual(Voto.objects.filter(usuario=self.u1, categoria=self.cat_a).count(), 1)
        # Todas respondieron con una redirección controlada: 1 éxito y el resto rechazadas.
        self.assertTrue(all(codigo == 302 for codigo, _ in resultados))
        exitos = sum(any("registrado correctamente" in m for m in msgs) for _, msgs in resultados)
        self.assertEqual(exitos, 1)

    def test_cp09_votos_simultaneos_en_categorias_distintas_son_todos_validos(self):
        resultados, errores = self._disparar([(self.vot_a1, self.ops_a1[0]), (self.vot_b, self.ops_b[0])])
        self.assertEqual(errores, [])
        self.assertEqual(Voto.objects.filter(usuario=self.u1).count(), 2)
