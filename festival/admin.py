"""
Django Admin como panel administrativo inicial (RF-02 a RF-05, RF-11, RF-12).

Reglas de la Entrega 1 que se aplican aquí:

* CU-05 A2: al desactivar una categoría con votaciones abiertas se advierte el efecto.
* CU-06 A2: una votación sin opciones no puede abrirse.
* CU-05/06/07 y RF-12: las acciones administrativas quedan en el registro de auditoría
  (``LogEntry``), incluidas las acciones masivas de abrir y cerrar.
* CU-07: los cambios de estado de una votación siguen el orden Borrador → Abierta →
  Cerrada → Resultados publicados.
* CU-08: el registro de auditoría puede consultarse (solo lectura) y no se puede alterar.
* Eliminación restringida: el Eje 1 habla de *desactivar*. Una edición o categoría con
  contenido no puede eliminarse y una votación solo mientras sea borrador, para no
  perder información (y, a futuro, votos).
"""
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.db import models as dj_models
from django.utils import timezone
from django.utils.html import format_html

from .models import Categoria, Edicion, Opcion, Voto, Votacion


class CategoriaInline(admin.TabularInline):
    model = Categoria
    extra = 1

    def has_delete_permission(self, request, obj=None):
        return False  # las categorías se desactivan, no se eliminan


class OpcionInline(admin.TabularInline):
    model = Opcion
    extra = 2
    # Descripción más compacta para que la tabla en línea quepa en pantalla.
    formfield_overrides = {dj_models.TextField: {"widget": forms.Textarea(attrs={"rows": 2, "cols": 40})}}

    def has_delete_permission(self, request, obj=None):
        # Las opciones solo se quitan mientras la votación es borrador.
        if obj is not None and obj.estado != Votacion.Estado.BORRADOR:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Edicion)
class EdicionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "anio", "fecha_inicio", "fecha_fin", "activa")
    list_filter = ("activa",)
    search_fields = ("nombre", "descripcion")
    inlines = [CategoriaInline]

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.categorias.exists():
            return False  # con contenido: desactivar en lugar de eliminar
        return super().has_delete_permission(request, obj)


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "edicion", "orden", "activa")
    list_filter = ("activa", "edicion")
    search_fields = ("nombre",)
    list_select_related = ("edicion",)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.votaciones.exists():
            return False  # con votaciones: desactivar en lugar de eliminar
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # CU-05 A2: advertir (sin bloquear) si se desactiva con votaciones abiertas.
        if change and "activa" in form.changed_data and not obj.activa:
            abiertas = obj.votaciones_abiertas().count()
            if abiertas:
                self.message_user(
                    request,
                    f"Advertencia: la categoría «{obj.nombre}» tiene {abiertas} votación(es) abierta(s) "
                    "que dejarán de mostrarse al público mientras la categoría esté inactiva.",
                    level=messages.WARNING,
                )


@admin.register(Votacion)
class VotacionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "categoria", "estado", "estado_actual", "fecha_apertura", "fecha_cierre", "total_opciones")
    list_filter = ("estado", "categoria__edicion")
    search_fields = ("nombre", "descripcion")
    list_select_related = ("categoria", "categoria__edicion")
    inlines = [OpcionInline]
    actions = ["abrir", "cerrar", "publicar"]

    @admin.display(description="Estado público")
    def estado_actual(self, obj):
        return obj.estado_publico_display

    @admin.display(description="Opciones activas")
    def total_opciones(self, obj):
        return obj.total_opciones_activas

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.estado != Votacion.Estado.BORRADOR:
            return False  # solo se elimina un borrador
        return super().has_delete_permission(request, obj)

    def save_related(self, request, form, formsets, change):
        """CU-06 A2: tras guardar las opciones, una votación sin opciones no queda abierta."""
        super().save_related(request, form, formsets, change)
        votacion = form.instance
        if votacion.estado == Votacion.Estado.ABIERTA and not votacion.puede_abrirse:
            Votacion.objects.filter(pk=votacion.pk).update(estado=Votacion.Estado.BORRADOR)
            self.message_user(
                request,
                f"La votación «{votacion.nombre}» no puede abrirse sin opciones activas: "
                "quedó en estado Borrador. Agregue opciones y ábrala de nuevo.",
                level=messages.ERROR,
            )

    def _cambiar_estado(self, request, queryset, nuevo_estado, verbo):
        cambiadas = []
        for votacion in queryset:
            if not votacion.puede_cambiar_a(nuevo_estado) and votacion.estado != nuevo_estado:
                self.message_user(
                    request,
                    f"«{votacion.nombre}» no pasó a «{verbo}»: estaba en «{votacion.get_estado_display()}». "
                    "Orden permitido: Borrador → Abierta → Cerrada → Resultados publicados.",
                    level=messages.WARNING,
                )
                continue
            if nuevo_estado == Votacion.Estado.ABIERTA and not votacion.puede_abrirse:
                self.message_user(
                    request,
                    f"«{votacion.nombre}» no se abrió: no tiene opciones activas.",
                    level=messages.WARNING,
                )
                continue
            if votacion.estado != nuevo_estado:
                votacion.estado = nuevo_estado
                votacion.save(update_fields=["estado"])
                cambiadas.append(votacion)
        if cambiadas:
            # RF-12: las acciones masivas también quedan en el registro de auditoría.
            LogEntry.objects.log_actions(
                request.user.pk, cambiadas, CHANGE, change_message=f"Estado cambiado a «{verbo}» (acción masiva)."
            )
        if cambiadas:
            self.message_user(request, f"{len(cambiadas)} votación(es) cambiada(s) a «{verbo}».")

    @admin.action(description="Abrir votaciones seleccionadas")
    def abrir(self, request, queryset):
        self._cambiar_estado(request, queryset, Votacion.Estado.ABIERTA, "Abierta")

    @admin.action(description="Cerrar votaciones seleccionadas")
    def cerrar(self, request, queryset):
        self._cambiar_estado(request, queryset, Votacion.Estado.CERRADA, "Cerrada")

    @admin.action(description="Publicar resultados de las votaciones seleccionadas")
    def publicar(self, request, queryset):
        self._cambiar_estado(request, queryset, Votacion.Estado.PUBLICADA, "Resultados publicados")


@admin.register(Opcion)
class OpcionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "votacion", "orden", "activa")
    list_filter = ("activa", "votacion__categoria__edicion")
    search_fields = ("nombre",)
    list_select_related = ("votacion",)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.votacion.estado != Votacion.Estado.BORRADOR:
            return False  # las opciones solo se quitan mientras la votación es borrador
        return super().has_delete_permission(request, obj)


@admin.register(Voto)
class VotoAdmin(admin.ModelAdmin):
    """Consulta administrativa de votos (CP-08). Solo lectura: un voto emitido es inmodificable.

    Los votos solo se crean desde el sitio público (``festival.servicios.registrar_voto``),
    que aplica todas las reglas. Permitir agregarlos, editarlos o borrarlos aquí rompería la
    integridad del proceso, por eso el administrador únicamente los consulta y filtra.
    """

    list_display = ("id", "usuario", "categoria", "votacion", "opcion", "fecha_voto")  # la edición va en el filtro y en «categoría»
    list_filter = ("edicion", "categoria", "votacion")
    search_fields = ("usuario__username", "usuario__email", "opcion__nombre")
    list_select_related = ("usuario", "edicion", "categoria", "votacion", "opcion")
    date_hierarchy = None  # en MySQL exige tener cargadas las tablas de zonas horarias
    ordering = ("-emitido_en",)

    @admin.display(description="Emitido en", ordering="emitido_en")
    def fecha_voto(self, obj):
        return timezone.localtime(obj.emitido_en).strftime("%d/%m/%Y %H:%M:%S")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LogEntry)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    """Registro de auditoría (CU-08): fecha, tipo de acción, entidad y usuario. Solo lectura."""

    list_display = ("action_time", "user", "tipo_accion", "entidad", "object_repr")
    list_filter = ("action_flag", "content_type", "user")
    search_fields = ("object_repr", "change_message")
    # Sin date_hierarchy: en MySQL exige tener cargadas las tablas de zonas horarias.
    list_select_related = ("user", "content_type")

    @admin.display(description="Acción")
    def tipo_accion(self, obj):
        return {1: "Creó", 2: "Modificó", 3: "Eliminó"}.get(obj.action_flag, "—")

    @admin.display(description="Entidad afectada")
    def entidad(self, obj):
        return format_html("{}", obj.content_type.name.capitalize()) if obj.content_type else "—"

    # Los registros de auditoría no se crean, modifican ni borran a mano (CU-08 postcondición).
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.has_perm("admin.view_logentry")
