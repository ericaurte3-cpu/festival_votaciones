from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "cuentas"

urlpatterns = [
    path("registro/", views.RegistroView.as_view(), name="registro"),
    path("ingresar/", views.IngresarView.as_view(), name="login"),
    # Desde Django 5 el cierre de sesión solo acepta POST (evita logout por enlaces maliciosos).
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
]
