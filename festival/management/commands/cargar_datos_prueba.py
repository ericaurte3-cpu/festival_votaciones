"""
Carga datos de PRUEBA (ficticios) para demostrar el sistema.

Uso:  python manage.py cargar_datos_prueba [--limpiar] [--votantes N] [--password CLAVE]

Con ``--votantes N`` también crea N usuarios votantes ficticios (votante1@example.com ...).
La contraseña NO está escrita en el código: se toma de ``--password`` o, si se omite, se
genera una aleatoria y se muestra una sola vez en pantalla.

Las categorías se basan en las del Festival documentadas en la Entrega 1. Los nombres de
las opciones son genéricos ("Participante de prueba N"): no representan personas reales.
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils.crypto import get_random_string
from django.db import transaction
from django.utils import timezone

from festival.models import Categoria, Edicion, Opcion, Voto, Votacion

CATEGORIAS = [
    ("Acordeonero profesional", "Concurso central del Festival de música tradicional."),
    ("Canción vallenata inédita", "Composiciones originales que compiten en el Festival."),
    ("Piquería mayor", "Duelo de versos improvisados entre verseadores."),
    ("Conjuntos típicos", "Agrupaciones tradicionales de acordeón, caja y guacharaca."),
]


class Command(BaseCommand):
    help = "Carga ediciones, categorías, votaciones y opciones de prueba."

    def add_arguments(self, parser):
        parser.add_argument("--limpiar", action="store_true", help="Borra los datos del festival antes de cargar.")
        parser.add_argument("--votantes", type=int, default=0, metavar="N",
                            help="Crea N usuarios votantes de prueba (votante1@example.com, ...).")
        parser.add_argument("--password", help="Contraseña de los votantes de prueba (si se omite, se genera una).")

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts["limpiar"]:
            # Los votos están protegidos (PROTECT): se eliminan primero para poder reiniciar los datos de prueba.
            Voto.objects.all().delete()
            Edicion.objects.all().delete()
            self.stdout.write("Datos anteriores eliminados.")

        ahora = timezone.now()
        edicion27, _ = Edicion.objects.get_or_create(
            anio=2027,
            defaults=dict(
                nombre="Festival de la Leyenda Vallenata",
                descripcion="Edición 60 (datos de prueba para la Entrega 2).",
                fecha_inicio=date(2027, 4, 28),
                fecha_fin=date(2027, 5, 1),
                activa=True,
            ),
        )
        edicion26, _ = Edicion.objects.get_or_create(
            anio=2026,
            defaults=dict(
                nombre="Festival de la Leyenda Vallenata",
                descripcion="Edición 59 (histórica, datos de prueba).",
                fecha_inicio=date(2026, 4, 29),
                fecha_fin=date(2026, 5, 2),
                activa=True,
            ),
        )

        # (edición, índice de categoría, estado, apertura, cierre): cubre todos los estados.
        plan = [
            (edicion27, 0, Votacion.Estado.ABIERTA, ahora - timedelta(days=1), ahora + timedelta(days=5)),
            (edicion27, 1, Votacion.Estado.ABIERTA, ahora - timedelta(days=2), ahora + timedelta(days=3)),
            # «abierta» con apertura futura: el público la ve como «Próximamente».
            (edicion27, 2, Votacion.Estado.ABIERTA, ahora + timedelta(days=10), ahora + timedelta(days=15)),
            (edicion27, 3, Votacion.Estado.BORRADOR, ahora + timedelta(days=10), ahora + timedelta(days=15)),
            (edicion26, 0, Votacion.Estado.PUBLICADA, ahora - timedelta(days=400), ahora - timedelta(days=390)),
            (edicion26, 2, Votacion.Estado.CERRADA, ahora - timedelta(days=400), ahora - timedelta(days=395)),
        ]
        for edicion, idx, estado, apertura, cierre in plan:
            nombre, desc = CATEGORIAS[idx]
            cat, _ = Categoria.objects.get_or_create(
                edicion=edicion, nombre=nombre, defaults=dict(descripcion=desc, orden=idx + 1)
            )
            vot, creada = Votacion.objects.get_or_create(
                categoria=cat,
                nombre=f"Votación del público · {nombre} {edicion.anio}",
                defaults=dict(
                    descripcion="Votación de prueba. Elige a tu favorito entre los participantes.",
                    fecha_apertura=apertura,
                    fecha_cierre=cierre,
                    estado=estado,
                ),
            )
            if creada:
                for i in range(1, 5):
                    Opcion.objects.create(
                        votacion=vot,
                        nombre=f"Participante de prueba {i}",
                        descripcion="Dato de prueba, no corresponde a una persona real.",
                        orden=i,
                    )
        # Segundo subevento en la MISMA categoría: demuestra que el voto único es por categoría
        # y edición, no por votación (CP-02: no se puede votar de nuevo en otro subevento).
        cat_acordeon = Categoria.objects.get(edicion=edicion27, nombre=CATEGORIAS[0][0])
        semifinal, creada = Votacion.objects.get_or_create(
            categoria=cat_acordeon,
            nombre=f"Semifinal · {CATEGORIAS[0][0]} 2027",
            defaults=dict(
                descripcion="Segundo subevento de la categoría (datos de prueba).",
                fecha_apertura=ahora - timedelta(days=1),
                fecha_cierre=ahora + timedelta(days=5),
                estado=Votacion.Estado.ABIERTA,
            ),
        )
        if creada:
            for i in range(1, 4):
                Opcion.objects.create(votacion=semifinal, nombre=f"Semifinalista de prueba {i}",
                                      descripcion="Dato de prueba, no corresponde a una persona real.", orden=i)
        # Una categoría sin votaciones, para mostrar el estado vacío en la interfaz.
        Categoria.objects.get_or_create(
            edicion=edicion27, nombre="Acordeonera menor", defaults=dict(descripcion="Categoría juvenil.", orden=5)
        )
        self.stdout.write(self.style.SUCCESS(
            f"Listo: {Edicion.objects.count()} ediciones, {Categoria.objects.count()} categorías, "
            f"{Votacion.objects.count()} votaciones, {Opcion.objects.count()} opciones."
        ))
        if opts["votantes"] > 0:
            self._crear_votantes(opts["votantes"], opts["password"])

    def _crear_votantes(self, cantidad, password):
        """Crea usuarios votantes ficticios (idempotente: no repite los que ya existen)."""
        User = get_user_model()
        generada = password is None
        password = password or get_random_string(14)
        creados = 0
        for i in range(1, cantidad + 1):
            correo = f"votante{i}@example.com"
            if not User.objects.filter(username=correo).exists():
                User.objects.create_user(username=correo, email=correo, password=password,
                                         first_name=f"Votante {i}")
                creados += 1
        self.stdout.write(self.style.SUCCESS(f"Votantes de prueba: {creados} creado(s) de {cantidad}."))
        if creados and generada:
            self.stdout.write(f"Contraseña generada (anótala, no se vuelve a mostrar): {password}")
