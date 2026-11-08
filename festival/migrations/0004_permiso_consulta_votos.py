"""Concede al perfil «Administrador» ya existente el permiso de consultar votos.

En una base de datos nueva el grupo se crea después de migrar (señal ``post_migrate``) y
ya incluye ``view_voto``. En una base que ya tenía el grupo (Entrega 2) no se vuelven a
asignar permisos, así que esta migración de datos agrega solo el de lectura de votos.
"""
from django.db import migrations


def agregar_permiso(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    grupo = Group.objects.filter(name="Administrador").first()
    if grupo is None:
        return  # base nueva: lo hará post_migrate
    tipo, _ = ContentType.objects.get_or_create(app_label="festival", model="voto")
    permiso, _ = Permission.objects.get_or_create(
        content_type=tipo, codename="view_voto", defaults={"name": "Can view voto"}
    )
    grupo.permissions.add(permiso)


class Migration(migrations.Migration):

    dependencies = [
        ("festival", "0003_voto"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(agregar_permiso, migrations.RunPython.noop)]
