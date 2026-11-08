"""Alinea el modelo con la Figura 2 de la Entrega 1.

* ``Categoria.activa``  -> atributo ``estado`` de CATEGORÍA (CU-05: desactivar).
* ``Votacion.titulo``   -> ``Votacion.nombre`` (atributo ``nombre`` de VOTACIÓN).

El cambio de nombre conserva los datos existentes.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("festival", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(model_name="votacion", old_name="titulo", new_name="nombre"),
        migrations.AlterModelOptions(
            name="votacion",
            options={"ordering": ["fecha_apertura", "nombre"], "verbose_name": "votación", "verbose_name_plural": "votaciones"},
        ),
        migrations.AddField(
            model_name="categoria",
            name="activa",
            field=models.BooleanField(
                default=True,
                help_text="Una categoría inactiva deja de mostrarse al público (CU-05: desactivar).",
                verbose_name="activa",
            ),
        ),
        migrations.AlterField(
            model_name="votacion",
            name="nombre",
            field=models.CharField(max_length=160, verbose_name="nombre"),
        ),
    ]
