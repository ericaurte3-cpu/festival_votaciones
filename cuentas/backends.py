"""Autenticación por correo electrónico (CU-02), conservando el nombre de usuario.

Los votantes se registran con su correo, que se guarda también como ``username``.
Pero las cuentas creadas con ``createsuperuser`` (u otras) tienen un nombre de usuario
distinto de su correo. Este backend acepta ambos identificadores, por lo que cualquier
cuenta puede ingresar con su correo o con su usuario.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class CorreoOUsuarioBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if username is None or password is None:
            return None
        identificador = username.strip()
        usuario = self._buscar(identificador)
        if usuario is None:
            # Mitiga ataques de temporización (igual que ModelBackend): se simula el hash.
            User().set_password(password)
            return None
        if usuario.check_password(password) and self.user_can_authenticate(usuario):
            return usuario
        return None

    @staticmethod
    def _buscar(identificador):
        # 1) Nombre de usuario exacto tiene prioridad.
        try:
            return User.objects.get(**{User.USERNAME_FIELD: identificador})
        except User.DoesNotExist:
            pass
        # 2) Correo (sin distinguir mayúsculas). Si es ambiguo (correo repetido) no se autentica:
        #    el correo no es único en el modelo base y no se debe adivinar la cuenta.
        coincidencias = list(User.objects.filter(email__iexact=identificador)[:2])
        return coincidencias[0] if len(coincidencias) == 1 else None
