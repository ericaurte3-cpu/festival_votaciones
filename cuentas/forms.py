"""
Formularios de registro e inicio de sesión (CU-02, pantallas 2 y 3 del prototipo).

El votante se identifica con su correo electrónico: al registrarse, el correo (en
minúsculas) se guarda también como nombre de usuario de Django. Los datos solicitados y
el texto de tratamiento de datos están PENDIENTES DE VALIDACIÓN con la Fundación
(Entrega 1: RN-07, RNF-07 y preguntas 1, 2 y 11).
"""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db.models import Q

User = get_user_model()


def _estilo_bootstrap(form):
    """Aplica las clases de Bootstrap a los widgets del formulario."""
    for campo in form.fields.values():
        if isinstance(campo.widget, forms.CheckboxInput):
            campo.widget.attrs["class"] = "form-check-input"
        else:
            campo.widget.attrs["class"] = "form-control"


class RegistroForm(UserCreationForm):
    nombre = forms.CharField(label="Nombre", max_length=150, widget=forms.TextInput(attrs={"autocomplete": "name"}))
    email = forms.EmailField(label="Correo electrónico", widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    acepta_datos = forms.BooleanField(
        label="Acepto el tratamiento de mis datos personales (texto por definir)",
        error_messages={"required": "Debes aceptar el tratamiento de datos para crear la cuenta."},
    )

    field_order = ["nombre", "email", "password1", "password2", "acepta_datos"]

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ()  # el nombre de usuario se genera a partir del correo

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"
        _estilo_bootstrap(self)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exists():
            # CU-02 A3: el sistema sugiere iniciar sesión (la plantilla muestra el enlace).
            raise forms.ValidationError("Este correo ya está registrado.", code="duplicado")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["nombre"]
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    """Inicio de sesión con correo electrónico (CU-02 A2: credenciales incorrectas)."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "El correo o la contraseña no son correctos. Revisa los datos e inténtalo de nuevo.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Correo electrónico"
        self.fields["username"].widget.attrs.update({"autocomplete": "email", "autofocus": True})
        self.fields["password"].widget.attrs["autocomplete"] = "current-password"
        _estilo_bootstrap(self)

    def clean_username(self):
        usuario = self.cleaned_data["username"].strip()
        # Los correos se guardan en minúsculas; los usuarios internos (p. ej. administradores) se respetan.
        return usuario.lower() if "@" in usuario else usuario
