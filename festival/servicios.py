"""
Capa de servicio del módulo de votaciones (Entrega 3).

Concentra las reglas de negocio de emitir un voto para que las vistas se limiten a
recibir la solicitud y responder. Así la misma lógica se puede probar, reutilizar y
auditar en un único lugar.

Reglas aplicadas **en el servidor** (el cliente nunca es de fiar):

* RN-03  La votación debe estar abierta (estado, periodo) y su categoría y edición activas.
* RN-02  La opción debe existir, estar activa y pertenecer a la votación indicada
         (y, por tanto, a su categoría y edición).
* RN-02  Un usuario solo puede votar una vez por categoría y edición, aunque la
         categoría tenga varias votaciones (subeventos).

La unicidad la decide **la base de datos** (``Voto.Meta.constraints``). La consulta previa
``exists()`` solo sirve para dar un mensaje amable en el caso normal; ante solicitudes
simultáneas ambas pasan esa consulta y la restricción UNIQUE deja pasar solo a una.
"""
import logging

from django.db import IntegrityError, transaction

from .models import Opcion, Voto, Votacion

logger = logging.getLogger(__name__)

# Nombre de la restricción UNIQUE (se usa para distinguir un duplicado de otro error de integridad).
NOMBRE_RESTRICCION_UNICIDAD = "voto_unico_usuario_categoria_edicion"
# Código de MySQL/MariaDB para «Duplicate entry» (ER_DUP_ENTRY).
MYSQL_ER_DUP_ENTRY = 1062


class VotoRechazado(Exception):
    """Una regla de negocio impide registrar el voto. ``mensaje`` es apto para el usuario."""

    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.mensaje = mensaje


class VotacionNoDisponible(VotoRechazado):
    """La votación no existe, no es pública o no está abierta (RN-03)."""


class OpcionInvalida(VotoRechazado):
    """La opción no existe, está inactiva o no pertenece a la votación (RN-02)."""


class VotoDuplicado(VotoRechazado):
    """El usuario ya votó en esa categoría y edición (RN-02)."""


class UsuarioNoAutorizado(VotoRechazado):
    """El usuario no está autenticado o su cuenta está inactiva."""


def votacion_acepta_votos(votacion):
    """¿Admite votos ahora? Estado/periodo abierto y categoría y edición activas (RN-03)."""
    categoria = votacion.categoria
    return bool(votacion.esta_abierta and categoria.activa and categoria.edicion.activa)


def voto_del_usuario(usuario, categoria):
    """Voto que ``usuario`` ya emitió en ``categoria`` (misma edición), o ``None``."""
    if not getattr(usuario, "is_authenticated", False):
        return None
    return (
        Voto.objects.select_related("opcion", "votacion")
        .filter(usuario=usuario, categoria=categoria, edicion_id=categoria.edicion_id)
        .first()
    )


def validar_voto(*, usuario, votacion_id, opcion_id):
    """Aplica todas las reglas sin escribir nada. Devuelve ``(votacion, opcion)``.

    Se usa tanto en el paso de confirmación como al registrar. Lanza una subclase de
    :class:`VotoRechazado` si alguna regla no se cumple.
    """
    if not (getattr(usuario, "is_authenticated", False) and usuario.is_active):
        raise UsuarioNoAutorizado("Debes iniciar sesión para votar.")

    # Las votaciones en borrador no son públicas: se tratan como inexistentes.
    votacion = (
        Votacion.objects.publicas()
        .select_related("categoria", "categoria__edicion")
        .filter(pk=votacion_id)
        .first()
    )
    if votacion is None:
        raise VotacionNoDisponible("La votación solicitada no existe.")
    if not votacion_acepta_votos(votacion):
        raise VotacionNoDisponible(
            f"La votación «{votacion.nombre}» no está habilitada para recibir votos "
            f"(estado: {votacion.estado_publico_display.lower()})."
        )

    # Filtrar por votación impide votar una opción de otra votación o categoría.
    opcion = Opcion.objects.filter(pk=opcion_id, votacion=votacion, activa=True).first()
    if opcion is None:
        raise OpcionInvalida("La opción seleccionada no es válida para esta votación.")

    anterior = voto_del_usuario(usuario, votacion.categoria)
    if anterior is not None:
        raise VotoDuplicado(
            f"Ya votaste en la categoría «{votacion.categoria.nombre}» "
            f"(opción elegida: «{anterior.opcion.nombre}»). Solo se permite un voto por categoría."
        )
    return votacion, opcion


def _es_violacion_de_unicidad(error):
    """¿El ``IntegrityError`` proviene de la restricción de voto único (y no de otra)?"""
    causa = error.__cause__
    codigo = causa.args[0] if causa is not None and causa.args else None
    return codigo == MYSQL_ER_DUP_ENTRY or NOMBRE_RESTRICCION_UNICIDAD in str(error)


def registrar_voto(*, usuario, votacion_id, opcion_id):
    """Valida y registra el voto de forma atómica. Devuelve el :class:`Voto` creado.

    ``edicion``, ``categoria`` y ``votacion`` se derivan de la opción validada: nunca se
    aceptan del cliente. El ``transaction.atomic()`` interno crea un *savepoint*, de modo
    que un ``IntegrityError`` no deja inutilizable la transacción de la petición
    (``ATOMIC_REQUESTS=True``).
    """
    votacion, opcion = validar_voto(usuario=usuario, votacion_id=votacion_id, opcion_id=opcion_id)
    try:
        with transaction.atomic():
            voto = Voto.objects.create(
                usuario=usuario,
                edicion=votacion.categoria.edicion,
                categoria=votacion.categoria,
                votacion=votacion,
                opcion=opcion,
            )
    except IntegrityError as error:
        if _es_violacion_de_unicidad(error):
            # Carrera: otra solicitud del mismo usuario se registró entre la validación y el INSERT.
            logger.info("Voto duplicado detenido por la base de datos (usuario=%s, categoría=%s).",
                        usuario.pk, votacion.categoria_id)
            raise VotoDuplicado(
                f"Ya votaste en la categoría «{votacion.categoria.nombre}». "
                "Solo se permite un voto por categoría."
            ) from error
        raise  # cualquier otro problema de integridad es un error real y no debe ocultarse
    logger.info("Voto registrado (usuario=%s, categoría=%s, opción=%s).", usuario.pk, votacion.categoria_id, opcion.pk)
    return voto
