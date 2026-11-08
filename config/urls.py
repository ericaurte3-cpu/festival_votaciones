"""Rutas raíz del proyecto: delega en cada aplicación."""
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Festival de la Leyenda Vallenata 2027 · Administración"
admin.site.site_title = "Administración de Votaciones"
admin.site.index_title = "Gestión de ediciones, categorías, votaciones y opciones"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("cuentas/", include("cuentas.urls")),
    path("", include("festival.urls")),
]
