"""
Vistas públicas (capa V del patrón MVT de Django).

Consultan MySQL a través del ORM y entregan el contexto a las plantillas. Todo lo que
se muestra proviene de la base de datos, no de datos estáticos.

Correspondencia con el prototipo de la Entrega 1:
    InicioView            -> pantallas 1 y 4 (inicio con las categorías de la edición vigente)
    EdicionListView       -> ediciones disponibles (consulta de ediciones anteriores)
    EdicionDetailView     -> categorías de una edición
    CategoriaDetailView   -> pantalla 5 (votaciones disponibles)
    VotacionDetailView    -> pantallas 6 y 7 (detalle y opciones)
"""
from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView

from . import servicios
from .models import Categoria, Edicion, Opcion, Voto, Votacion


class VistaPreviaPersonalMixin:
    """Permite al personal con permiso de lectura ver contenido no público (vista previa).

    El público general sigue recibiendo 404 para borradores y elementos inactivos; el
    personal (is_staff + permiso ``view_<modelo>``) los ve con un aviso visible. Es lo que
    hace funcionar el enlace «Ver en el sitio» de Django Admin.
    """

    permiso_vista_previa = ""  # p. ej. "festival.view_votacion"

    def _es_vista_previa(self):
        u = self.request.user
        return u.is_authenticated and u.is_staff and u.has_perm(self.permiso_vista_previa)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["vista_previa"] = self._es_vista_previa() and not self.es_publico(self.object)
        return ctx


def _categorias_con_conteos(queryset):
    """Anota cada categoría con sus votaciones públicas y las que están abiertas ahora."""
    ahora = timezone.now()
    return queryset.filter(activa=True).annotate(
        total_votaciones=Count("votaciones", filter=~Q(votaciones__estado=Votacion.Estado.BORRADOR), distinct=True),
        total_abiertas=Count(
            "votaciones",
            filter=Q(
                votaciones__estado=Votacion.Estado.ABIERTA,
                votaciones__fecha_apertura__lte=ahora,
                votaciones__fecha_cierre__gte=ahora,
            ),
            distinct=True,
        ),
    )


class InicioView(TemplateView):
    """Inicio (CU-01): categorías de la edición vigente.

    Si no hay ediciones activas se muestra un mensaje informativo (CU-01 A1).
    """

    template_name = "festival/inicio.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        vigente = Edicion.objects.vigente()
        ctx["vigente"] = vigente
        ctx["categorias"] = _categorias_con_conteos(vigente.categorias.all()) if vigente else []
        return ctx


class EdicionListView(ListView):
    """Ediciones activas (vigente y anteriores)."""

    template_name = "festival/ediciones.html"
    context_object_name = "ediciones"

    def get_queryset(self):
        return Edicion.objects.filter(activa=True).annotate(
            total_categorias=Count("categorias", filter=Q(categorias__activa=True), distinct=True)
        ).order_by("-anio")


class EdicionDetailView(VistaPreviaPersonalMixin, DetailView):
    """Detalle de una edición con sus categorías activas."""

    template_name = "festival/edicion.html"
    context_object_name = "edicion"
    permiso_vista_previa = "festival.view_edicion"

    @staticmethod
    def es_publico(edicion):
        return edicion.activa

    def get_queryset(self):
        if self._es_vista_previa():
            return Edicion.objects.all()
        return Edicion.objects.filter(activa=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categorias"] = _categorias_con_conteos(self.object.categorias.all())
        return ctx


class CategoriaDetailView(VistaPreviaPersonalMixin, DetailView):
    """Detalle de una categoría con sus votaciones públicas."""

    template_name = "festival/categoria.html"
    context_object_name = "categoria"
    permiso_vista_previa = "festival.view_categoria"

    @staticmethod
    def es_publico(categoria):
        return categoria.activa and categoria.edicion.activa

    def get_queryset(self):
        qs = Categoria.objects.select_related("edicion")
        if self._es_vista_previa():
            return qs
        # Una categoría o edición inactiva no es pública: devuelve 404.
        return qs.filter(activa=True, edicion__activa=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["votaciones"] = self.object.votaciones.publicas().annotate(
            total_opciones=Count("opciones", filter=Q(opciones__activa=True))
        )
        ctx["voto_usuario"] = servicios.voto_del_usuario(self.request.user, self.object)
        return ctx


class VotacionDetailView(VistaPreviaPersonalMixin, DetailView):
    """Detalle de una votación con sus opciones activas (sin emitir votos aún)."""

    template_name = "festival/votacion.html"
    context_object_name = "votacion"
    permiso_vista_previa = "festival.view_votacion"

    @staticmethod
    def es_publico(votacion):
        return (
            votacion.estado != Votacion.Estado.BORRADOR
            and votacion.categoria.activa
            and votacion.categoria.edicion.activa
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        votacion = self.object
        voto = servicios.voto_del_usuario(self.request.user, votacion.categoria)
        ctx["voto_usuario"] = voto
        # La interfaz solo ofrece votar si el servicio lo aceptaría; el servidor lo vuelve a validar al enviar.
        ctx["puede_votar"] = voto is None and servicios.votacion_acepta_votos(votacion)
        return ctx

    def get_queryset(self):
        if self._es_vista_previa():
            qs = Votacion.objects.all()
        else:
            # Los borradores y lo inactivo no son públicos: devuelven 404.
            qs = Votacion.objects.publicas().filter(categoria__activa=True, categoria__edicion__activa=True)
        return (
            qs.select_related("categoria", "categoria__edicion")
            .prefetch_related(
                Prefetch("opciones", queryset=Opcion.objects.filter(activa=True), to_attr="opciones_activas")
            )
        )


# --------------------------------------------------------------------------------------
# Gestión de ediciones (interfaz propia para el personal; respuesta a la observación del
# docente a la Entrega 1: «incorporar una interfaz específica para administrar las
# diferentes ediciones del Festival»). Complementa a Django Admin, que sigue siendo el
# panel para categorías, votaciones y opciones.
# --------------------------------------------------------------------------------------
from django.contrib import messages
from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, UpdateView

from .forms import EdicionForm, VotoForm


class PersonalRequeridoMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Solo usuarios de personal (RF-11). Sin sesión: va al login; sin permiso: 403."""

    def test_func(self):
        return self.request.user.is_staff

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied
        return super().handle_no_permission()


class GestionPermisosMixin(PermissionRequiredMixin):
    """Personal con el permiso de modelo correspondiente (RN-10, RNF-01).

    Un usuario con ``is_staff`` pero sin los permisos del perfil «Administrador» recibe 403.
    Sin sesión se redirige al login.
    """

    def has_permission(self):
        return self.request.user.is_staff and super().has_permission()


def _auditar(request, edicion, bandera, mensaje):
    """RF-12: toda acción de gestión queda en el registro de auditoría."""
    LogEntry.objects.log_actions(request.user.pk, [edicion], bandera, change_message=mensaje)


def _avisar_si_hay_votaciones_abiertas(request, edicion):
    abiertas = Votacion.objects.filter(
        categoria__edicion=edicion, estado=Votacion.Estado.ABIERTA
    ).count()
    if abiertas:
        messages.warning(
            request,
            f"Advertencia: la edición {edicion.anio} tiene {abiertas} votación(es) abierta(s) "
            "que dejarán de mostrarse al público mientras la edición esté inactiva.",
        )


class GestionEdicionListView(GestionPermisosMixin, ListView):
    permission_required = "festival.view_edicion"
    template_name = "festival/gestion/ediciones.html"
    context_object_name = "ediciones"

    def get_queryset(self):
        return Edicion.objects.annotate(
            total_categorias=Count("categorias", distinct=True),
            total_votaciones=Count("categorias__votaciones", distinct=True),
        ).order_by("-anio")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["vigente"] = Edicion.objects.vigente()
        return ctx


class GestionEdicionCreateView(GestionPermisosMixin, CreateView):
    permission_required = "festival.add_edicion"
    form_class = EdicionForm
    template_name = "festival/gestion/edicion_form.html"
    success_url = reverse_lazy("festival:gestion_ediciones")

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        _auditar(self.request, self.object, ADDITION, "Edición creada desde la interfaz de gestión.")
        messages.success(self.request, f"Edición {self.object.anio} creada.")
        return respuesta


class GestionEdicionUpdateView(GestionPermisosMixin, UpdateView):
    permission_required = "festival.change_edicion"
    model = Edicion
    form_class = EdicionForm
    template_name = "festival/gestion/edicion_form.html"
    success_url = reverse_lazy("festival:gestion_ediciones")

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        _auditar(self.request, self.object, CHANGE, "Edición modificada desde la interfaz de gestión.")
        if "activa" in form.changed_data and not self.object.activa:
            _avisar_si_hay_votaciones_abiertas(self.request, self.object)
        messages.success(self.request, f"Edición {self.object.anio} actualizada.")
        return respuesta


class GestionEdicionAlternarView(GestionPermisosMixin, View):
    """Activa o desactiva una edición (solo por POST)."""

    permission_required = "festival.change_edicion"
    http_method_names = ["post"]

    def post(self, request, pk):
        edicion = get_object_or_404(Edicion, pk=pk)
        edicion.activa = not edicion.activa
        edicion.save(update_fields=["activa"])
        estado = "activada" if edicion.activa else "desactivada"
        _auditar(request, edicion, CHANGE, f"Edición {estado}.")
        if not edicion.activa:
            _avisar_si_hay_votaciones_abiertas(request, edicion)
        messages.success(request, f"Edición {edicion.anio} {estado}.")
        return redirect("festival:gestion_ediciones")


class PanelView(PersonalRequeridoMixin, TemplateView):
    """Panel principal del personal (pantalla 10 del prototipo, CU-08).

    Resume el estado del festival y muestra la actividad reciente de la auditoría solo a
    quien tenga el permiso de consulta (CU-08 A2).
    """

    template_name = "festival/gestion/panel.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ahora = timezone.now()
        ctx["vigente"] = Edicion.objects.vigente()
        ctx["total_ediciones"] = Edicion.objects.filter(activa=True).count()
        ctx["total_categorias"] = Categoria.objects.filter(activa=True).count()
        ctx["votaciones_abiertas"] = Votacion.objects.filter(
            estado=Votacion.Estado.ABIERTA, fecha_apertura__lte=ahora, fecha_cierre__gte=ahora).count()
        ctx["votaciones_borrador"] = Votacion.objects.filter(estado=Votacion.Estado.BORRADOR).count()
        ctx["total_votos"] = Voto.objects.count()
        ctx["puede_ver_votos"] = self.request.user.has_perm("festival.view_voto")
        ctx["puede_auditar"] = self.request.user.has_perm("admin.view_logentry")
        if ctx["puede_auditar"]:
            ctx["actividad"] = LogEntry.objects.select_related("user", "content_type")[:10]
        return ctx


# --------------------------------------------------------------------------------------
# Emisión de votos y participación del usuario (Entrega 3)
# --------------------------------------------------------------------------------------
class VotarView(LoginRequiredMixin, View):
    """Emite un voto en dos pasos: selección → confirmación → registro (PRG).

    * Exige sesión: sin ella redirige al inicio de sesión (``LoginRequiredMixin``).
    * Solo acepta POST con token CSRF (``CsrfViewMiddleware``); un GET (p. ej. al volver del
      login) redirige a la página de la votación.
    * Paso 1 (sin ``confirmar``): valida todas las reglas y muestra la pantalla de confirmación.
    * Paso 2 (``confirmar=1``): vuelve a validar y registra el voto en una transacción.
    * Toda regla incumplida (votación cerrada, opción de otra categoría, voto repetido...) se
      informa con un mensaje y no se escribe nada.
    """

    http_method_names = ["get", "post"]

    def get(self, request, pk):
        return redirect("festival:votacion", pk=pk)

    def post(self, request, pk):
        form = VotoForm(request.POST)
        if not form.is_valid():
            for errores in form.errors.values():
                for error in errores:
                    messages.error(request, error)
            return redirect("festival:votacion", pk=pk)

        opcion_id = form.cleaned_data["opcion"]
        try:
            if not form.cleaned_data["confirmar"]:
                votacion, opcion = servicios.validar_voto(usuario=request.user, votacion_id=pk, opcion_id=opcion_id)
                return render(request, "festival/confirmar_voto.html", {"votacion": votacion, "opcion": opcion})
            servicios.registrar_voto(usuario=request.user, votacion_id=pk, opcion_id=opcion_id)
        except servicios.VotoRechazado as rechazo:
            messages.error(request, rechazo.mensaje)
            return redirect("festival:votacion", pk=pk)

        messages.success(request, "¡Tu voto fue registrado correctamente!")
        return redirect("festival:mis_votos")


class MisVotosView(LoginRequiredMixin, ListView):
    """Participación del usuario: categorías en las que ya votó (CP-07)."""

    template_name = "festival/mis_votos.html"
    context_object_name = "votos"

    def get_queryset(self):
        return (
            Voto.objects.filter(usuario=self.request.user)
            .select_related("edicion", "categoria", "votacion", "opcion")
            .order_by("-emitido_en", "-pk")
        )
