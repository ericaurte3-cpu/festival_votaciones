from django.apps import AppConfig
from django.db.models.signals import post_migrate

# Permisos del perfil «Administrador» (RN-10, RNF-01). Sin «eliminar» en ediciones ni
# categorías: el Eje 1 habla de *desactivar*, no de borrar. Votaciones y opciones solo
# pueden eliminarse mientras estén en borrador (regla aplicada en el admin).
PERMISOS_ADMINISTRADOR = [
    ("festival", [
        "view_edicion", "add_edicion", "change_edicion",
        "view_categoria", "add_categoria", "change_categoria",
        "view_votacion", "add_votacion", "change_votacion", "delete_votacion",
        "view_opcion", "add_opcion", "change_opcion", "delete_opcion",
        "view_voto",  # Entrega 3: consulta (solo lectura) de los votos registrados
    ]),
    ("admin", ["view_logentry"]),  # CU-08: consultar la auditoría
]


def crear_grupo_administrador(sender, using="default", **kwargs):
    """Crea el grupo «Administrador» con sus permisos (solo la primera vez).

    Si el grupo ya existe no se tocan sus permisos, para respetar los ajustes manuales.
    """
    from django.apps import apps
    from django.contrib.auth.management import create_permissions
    from django.contrib.auth.models import Group, Permission

    for etiqueta in ("festival", "admin"):
        create_permissions(apps.get_app_config(etiqueta), using=using, verbosity=0)
    grupo, creado = Group.objects.using(using).get_or_create(name="Administrador")
    if creado:
        permisos = []
        for etiqueta, codigos in PERMISOS_ADMINISTRADOR:
            permisos += list(Permission.objects.using(using).filter(
                content_type__app_label=etiqueta, codename__in=codigos))
        grupo.permissions.set(permisos)


class FestivalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "festival"

    def ready(self):
        post_migrate.connect(crear_grupo_administrador, sender=self)
