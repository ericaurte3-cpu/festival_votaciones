"""
Modelos del sistema de votaciones.

Jerarquía definida en el análisis (Entrega 1, Figura 2 - modelo conceptual):

    Edición  1──N  Categoría  1──N  Votación  1──N  Opción

Correspondencia con el modelo conceptual:

* ``estado`` de Edición, Categoría y Opción se implementa como ``activa`` (booleano).
* ``estado`` de Votación se implementa con cuatro valores (ver ``Votacion.Estado``).
* ``Usuario`` es el modelo nativo de Django (nombre, correo, rol mediante ``is_staff``).
* ``Registro_auditoría`` lo cubre ``django.contrib.admin.LogEntry`` (usuario, acción,
  entidad afectada y fecha/hora).
* ``Voto`` (Entrega 3) vincula usuario, edición, categoría, votación y opción sin
  modificar las tablas anteriores. La regla «un voto por usuario, categoría y edición»
  se garantiza con una restricción de unicidad en MySQL (ver ``Voto.Meta.constraints``).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

# Mínimo de opciones para abrir una votación. El valor definitivo está
# PENDIENTE DE VALIDACIÓN con la Fundación (Entrega 1, CU-06 A2).
MIN_OPCIONES_PARA_ABRIR = 1


class EdicionQuerySet(models.QuerySet):
    def vigente(self):
        """Edición vigente: la activa de año más reciente.

        Criterio provisional, PENDIENTE DE VALIDACIÓN con la Fundación (Entrega 1,
        pregunta 9). Devuelve ``None`` si no hay ediciones activas.
        """
        return self.filter(activa=True).order_by("-anio").first()


class Edicion(models.Model):
    """Edición anual del Festival (RF-02). Agrupa las categorías (RN-01)."""

    nombre = models.CharField("nombre", max_length=120)
    anio = models.PositiveSmallIntegerField("año", unique=True)
    descripcion = models.TextField("descripción", blank=True)
    fecha_inicio = models.DateField("fecha de inicio", null=True, blank=True)
    fecha_fin = models.DateField("fecha de fin", null=True, blank=True)
    activa = models.BooleanField(
        "activa", default=True,
        help_text="Solo las ediciones activas se muestran en la interfaz pública (RF-02: desactivar).",
    )
    creada_en = models.DateTimeField("creada en", auto_now_add=True)

    objects = EdicionQuerySet.as_manager()

    class Meta:
        verbose_name = "edición"
        verbose_name_plural = "ediciones"
        ordering = ["-anio"]

    def __str__(self):
        return f"{self.nombre} ({self.anio})"

    def get_absolute_url(self):
        return reverse("festival:edicion", args=[self.pk])

    def clean(self):
        if self.fecha_inicio and self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError({"fecha_fin": "La fecha de fin no puede ser anterior a la de inicio."})


class Categoria(models.Model):
    """Categoría o concurso dentro de una edición (RF-03)."""

    edicion = models.ForeignKey(
        Edicion, verbose_name="edición", on_delete=models.CASCADE, related_name="categorias"
    )
    nombre = models.CharField("nombre", max_length=120)
    descripcion = models.TextField("descripción", blank=True)
    orden = models.PositiveSmallIntegerField("orden", default=0)
    activa = models.BooleanField(
        "activa", default=True,
        help_text="Una categoría inactiva deja de mostrarse al público (CU-05: desactivar).",
    )

    class Meta:
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        ordering = ["edicion", "orden", "nombre"]
        constraints = [
            # Una edición no puede tener dos categorías con el mismo nombre.
            models.UniqueConstraint(fields=["edicion", "nombre"], name="categoria_unica_por_edicion"),
        ]

    def __str__(self):
        return f"{self.nombre} · {self.edicion.anio}"

    def get_absolute_url(self):
        return reverse("festival:categoria", args=[self.pk])

    def votaciones_abiertas(self):
        """Votaciones de la categoría con el estado «abierta» (abiertas o por abrir)."""
        return self.votaciones.filter(estado=Votacion.Estado.ABIERTA)


class VotacionQuerySet(models.QuerySet):
    def publicas(self):
        """Votaciones visibles al público: todo menos los borradores (RF-01)."""
        return self.exclude(estado=Votacion.Estado.BORRADOR)


class Votacion(models.Model):
    """Proceso de votación asociado a una categoría (RF-04, RF-10, RN-02)."""

    class Estado(models.TextChoices):
        BORRADOR = "borrador", "Borrador"
        ABIERTA = "abierta", "Abierta"
        CERRADA = "cerrada", "Cerrada"
        PUBLICADA = "publicada", "Resultados publicados"

    # Transiciones válidas de estado (CU-07: el cambio debe ser «coherente con las reglas»).
    # No se permite reabrir una votación cerrada: depende de la decisión del cliente ante
    # fallas (pregunta 14 / RN-12, pendiente de validación).
    TRANSICIONES = {
        "borrador": {"abierta"},
        "abierta": {"cerrada"},
        "cerrada": {"publicada"},
        "publicada": set(),
    }

    # Estado que ve el público (CU-01): combina el estado administrativo con las fechas.
    ETIQUETAS_PUBLICAS = {
        "borrador": "Borrador",
        "proximamente": "Próximamente",
        "abierta": "Abierta",
        "cerrada": "Cerrada",
        "publicada": "Resultados publicados",
    }

    categoria = models.ForeignKey(
        Categoria, verbose_name="categoría", on_delete=models.CASCADE, related_name="votaciones"
    )
    nombre = models.CharField("nombre", max_length=160)
    descripcion = models.TextField("descripción", blank=True)
    fecha_apertura = models.DateTimeField("fecha de apertura")
    fecha_cierre = models.DateTimeField("fecha de cierre")
    estado = models.CharField("estado", max_length=10, choices=Estado.choices, default=Estado.BORRADOR)
    creada_en = models.DateTimeField("creada en", auto_now_add=True)

    objects = VotacionQuerySet.as_manager()

    class Meta:
        verbose_name = "votación"
        verbose_name_plural = "votaciones"
        ordering = ["fecha_apertura", "nombre"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(fecha_cierre__gt=models.F("fecha_apertura")),
                name="votacion_cierre_posterior_a_apertura",
            ),
        ]

    def __str__(self):
        return self.nombre

    def get_absolute_url(self):
        return reverse("festival:votacion", args=[self.pk])

    def clean(self):
        # Validación a nivel de formulario/admin; la restricción CHECK la refuerza en MySQL.
        if self.fecha_apertura and self.fecha_cierre and self.fecha_cierre <= self.fecha_apertura:
            raise ValidationError({"fecha_cierre": "El cierre debe ser posterior a la apertura."})
        # CU-07: el cambio de estado debe seguir las transiciones válidas.
        if self.pk:
            original = Votacion.objects.filter(pk=self.pk).values_list("estado", flat=True).first()
            if original and original != self.estado and self.estado not in self.TRANSICIONES[original]:
                raise ValidationError({
                    "estado": f"No se puede pasar de «{self.Estado(original).label}» a «{self.get_estado_display()}». "
                              "Orden permitido: Borrador → Abierta → Cerrada → Resultados publicados."
                })

    def puede_cambiar_a(self, nuevo_estado):
        """¿Es válida la transición desde el estado actual al indicado? (CU-07)"""
        return nuevo_estado in self.TRANSICIONES[self.estado]

    # --- Estado efectivo -------------------------------------------------
    @property
    def estado_publico(self):
        """Estado que se muestra al público (CU-01, CU-07 A2).

        * ``abierta`` en el periodo configurado; ``proximamente`` si aún no abre.
        * Si llega la fecha de cierre deja de aceptar votos aunque el administrador no
          la cierre manualmente (RN-03): se muestra como ``cerrada``.
        """
        if self.estado == self.Estado.ABIERTA:
            ahora = timezone.now()
            if ahora < self.fecha_apertura:
                return "proximamente"
            if ahora > self.fecha_cierre:
                return "cerrada"
            return "abierta"
        return self.estado

    @property
    def estado_publico_display(self):
        return self.ETIQUETAS_PUBLICAS[self.estado_publico]

    @property
    def esta_abierta(self):
        """RN-03: acepta votos solo con estado 'abierta' y dentro de su periodo."""
        return self.estado_publico == "abierta"

    # --- Reglas de apertura (CU-06 A2) -----------------------------------
    @property
    def total_opciones_activas(self):
        return self.opciones.filter(activa=True).count()

    @property
    def puede_abrirse(self):
        """No se puede abrir una votación sin opciones (mínimo pendiente de validación)."""
        return self.total_opciones_activas >= MIN_OPCIONES_PARA_ABRIR


class Opcion(models.Model):
    """Alternativa o participante por la que se puede votar (RF-05, RN-02)."""

    votacion = models.ForeignKey(
        Votacion, verbose_name="votación", on_delete=models.CASCADE, related_name="opciones"
    )
    nombre = models.CharField("nombre", max_length=160)
    descripcion = models.TextField("descripción", blank=True)
    orden = models.PositiveSmallIntegerField("orden", default=0)
    activa = models.BooleanField("activa", default=True)

    class Meta:
        verbose_name = "opción"
        verbose_name_plural = "opciones"
        ordering = ["votacion", "orden", "nombre"]
        constraints = [
            models.UniqueConstraint(fields=["votacion", "nombre"], name="opcion_unica_por_votacion"),
        ]

    def __str__(self):
        return self.nombre


class Voto(models.Model):
    """Voto emitido por un usuario autenticado (Entrega 3).

    Regla central (RN-02): cada usuario puede elegir **una sola opción por categoría y
    edición**, aunque la categoría tenga varias votaciones (subeventos). Puede votar en
    otras categorías.

    * ``edicion`` y ``categoria`` se guardan en el propio voto (están implícitas en la
      opción, pero se desnormalizan) porque una restricción UNIQUE de MySQL solo puede
      usar columnas de la misma tabla. Es lo que permite que **la base de datos** impida
      el segundo voto incluso ante solicitudes simultáneas.
    * La coherencia entre ``opcion``, ``votacion``, ``categoria`` y ``edicion`` la
      garantiza el servicio ``festival.servicios.registrar_voto`` (que las deriva de la
      opción, nunca del cliente) y la verifica ``clean()``.
    * Todas las claves foráneas son ``PROTECT``: un voto emitido no se pierde por borrar
      en cascada una opción, categoría o edición, ni al eliminar un usuario.
    """

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="usuario", on_delete=models.PROTECT, related_name="votos"
    )
    edicion = models.ForeignKey(Edicion, verbose_name="edición", on_delete=models.PROTECT, related_name="votos")
    categoria = models.ForeignKey(Categoria, verbose_name="categoría", on_delete=models.PROTECT, related_name="votos")
    votacion = models.ForeignKey(Votacion, verbose_name="votación", on_delete=models.PROTECT, related_name="votos")
    opcion = models.ForeignKey(Opcion, verbose_name="opción", on_delete=models.PROTECT, related_name="votos")
    emitido_en = models.DateTimeField("emitido en", auto_now_add=True)

    class Meta:
        verbose_name = "voto"
        verbose_name_plural = "votos"
        ordering = ["-emitido_en", "-pk"]
        constraints = [
            # Garantía de integridad en la base de datos (no depende de la aplicación).
            models.UniqueConstraint(
                fields=["usuario", "categoria", "edicion"],
                name="voto_unico_usuario_categoria_edicion",
                violation_error_message="Ya registraste un voto en esta categoría para esta edición.",
            ),
        ]

    def __str__(self):
        return f"{self.usuario} → {self.opcion} ({self.categoria})"

    def clean(self):
        """Coherencia opción ⊂ votación ⊂ categoría ⊂ edición (no se puede expresar como CHECK en MySQL)."""
        if not all([self.opcion_id, self.votacion_id, self.categoria_id, self.edicion_id]):
            return
        errores = {}
        if self.opcion.votacion_id != self.votacion_id:
            errores["opcion"] = "La opción no pertenece a la votación indicada."
        if self.votacion.categoria_id != self.categoria_id:
            errores["votacion"] = "La votación no pertenece a la categoría indicada."
        if self.categoria.edicion_id != self.edicion_id:
            errores["categoria"] = "La categoría no pertenece a la edición indicada."
        if errores:
            raise ValidationError(errores)
