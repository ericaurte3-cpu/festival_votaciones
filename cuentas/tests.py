"""Pruebas de registro, inicio y cierre de sesión (identificación por correo, CU-02)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()
CLAVE = "Vallenato2027!seguro"


class AutenticacionTests(TestCase):
    def datos_registro(self, **extra):
        datos = {"nombre": "Ana Pérez", "email": "Votante1@Example.com", "password1": CLAVE,
                 "password2": CLAVE, "acepta_datos": "on"}
        datos.update(extra)
        return datos

    def test_registro_crea_usuario_con_correo_en_minusculas_y_abre_sesion(self):
        r = self.client.post(reverse("cuentas:registro"), self.datos_registro())
        self.assertRedirects(r, reverse("festival:inicio"))
        usuario = User.objects.get(email="votante1@example.com")
        self.assertEqual(usuario.username, "votante1@example.com")
        self.assertEqual(usuario.first_name, "Ana Pérez")
        self.assertNotEqual(usuario.password, CLAVE)  # la contraseña se guarda con hash
        self.assertEqual(int(self.client.session["_auth_user_id"]), usuario.pk)

    def test_registro_exige_consentimiento(self):
        datos = self.datos_registro()
        del datos["acepta_datos"]
        r = self.client.post(reverse("cuentas:registro"), datos)
        self.assertContains(r, "Debes aceptar el tratamiento de datos")
        self.assertFalse(User.objects.exists())

    def test_registro_rechaza_contrasenas_distintas(self):
        r = self.client.post(reverse("cuentas:registro"), self.datos_registro(password2="otra"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_registro_correo_repetido_sugiere_iniciar_sesion(self):
        User.objects.create_user("votante1@example.com", "votante1@example.com", CLAVE)
        r = self.client.post(reverse("cuentas:registro"), self.datos_registro())
        self.assertContains(r, "Este correo ya está registrado")
        self.assertContains(r, reverse("cuentas:login"))  # CU-02 A3
        self.assertEqual(User.objects.count(), 1)

    def test_login_con_correo_correcto_e_incorrecto(self):
        User.objects.create_user("ana@example.com", "ana@example.com", CLAVE)
        malo = self.client.post(reverse("cuentas:login"), {"username": "ana@example.com", "password": "mal"})
        self.assertContains(malo, "El correo o la contraseña no son correctos")  # CU-02 A2
        self.assertNotIn("_auth_user_id", self.client.session)
        bueno = self.client.post(reverse("cuentas:login"), {"username": "ANA@example.com", "password": CLAVE})
        self.assertRedirects(bueno, reverse("festival:inicio"))

    def test_cuenta_con_usuario_distinto_del_correo_ingresa_con_ambos(self):
        """Cuentas como las de createsuperuser: username ≠ correo (CU-02)."""
        User.objects.create_user("hadrisson7", "Hadrisson@Example.com", CLAVE)
        for identificador in ("hadrisson7", "hadrisson@example.com", "HADRISSON@example.com"):
            self.client.logout()
            r = self.client.post(reverse("cuentas:login"), {"username": identificador, "password": CLAVE})
            self.assertRedirects(r, reverse("festival:inicio"), msg_prefix=identificador)
            self.assertIn("_auth_user_id", self.client.session)

    def test_correo_repetido_en_cuentas_distintas_no_autentica(self):
        User.objects.create_user("uno", "mismo@example.com", CLAVE)
        User.objects.create_user("dos", "mismo@example.com", CLAVE)
        r = self.client.post(reverse("cuentas:login"), {"username": "mismo@example.com", "password": CLAVE})
        self.assertContains(r, "El correo o la contraseña no son correctos")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_usuario_inactivo_no_ingresa_con_correo(self):
        User.objects.create_user("baja", "baja@example.com", CLAVE, is_active=False)
        r = self.client.post(reverse("cuentas:login"), {"username": "baja@example.com", "password": CLAVE})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_solo_por_post(self):
        User.objects.create_user("ana@example.com", "ana@example.com", CLAVE)
        self.client.login(username="ana@example.com", password=CLAVE)
        self.assertEqual(self.client.get(reverse("cuentas:logout")).status_code, 405)
        self.client.post(reverse("cuentas:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_admin_exige_staff(self):
        User.objects.create_user("ana@example.com", "ana@example.com", CLAVE)
        self.client.login(username="ana@example.com", password=CLAVE)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)  # RF-11
