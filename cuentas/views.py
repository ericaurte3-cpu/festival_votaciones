from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect
from django.views.generic import CreateView

from .forms import LoginForm, RegistroForm


class IngresarView(LoginView):
    """Inicio de sesión con correo electrónico."""

    authentication_form = LoginForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True


class RegistroView(CreateView):
    """Crea la cuenta y deja la sesión iniciada."""

    form_class = RegistroForm
    template_name = "registration/registro.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("festival:inicio")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # CU-02 A3: si el correo ya existe, la plantilla sugiere iniciar sesión.
        form = ctx["form"]
        ctx["correo_duplicado"] = form.is_bound and form.has_error("email", code="duplicado")
        return ctx

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        messages.success(self.request, f"¡Bienvenido, {user.first_name}! Tu cuenta fue creada.")
        return redirect("festival:inicio")
