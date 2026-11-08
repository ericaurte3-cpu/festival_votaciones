"""
API de consulta (solo lectura) del Festival: ``GET /api/categorias/``.

Entrega las categorías públicas con sus votaciones y opciones, leídas de MySQL, en JSON.
No requiere sesión porque expone solo información pública (la misma que muestra el sitio):

* categorías activas de ediciones activas,
* votaciones que no son borrador,
* opciones activas.

Parámetro opcional: ``?edicion=<id>`` filtra por edición.

Rendimiento: 3 consultas SQL en total sin importar el volumen de datos
(``select_related`` + ``prefetch_related``), evitando el problema N+1.

No se publican datos de usuarios ni de votos.
"""
from django.db import transaction
from django.db.models import Prefetch
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import Categoria, Opcion, Votacion


def _fecha(valor):
    """Fecha y hora ISO 8601 en la zona horaria del proyecto (o ``None``)."""
    return timezone.localtime(valor).isoformat() if valor else None


def _serializar_opcion(opcion):
    return {"id": opcion.pk, "nombre": opcion.nombre, "descripcion": opcion.descripcion, "orden": opcion.orden}


def _serializar_votacion(votacion):
    return {
        "id": votacion.pk,
        "nombre": votacion.nombre,
        "estado": votacion.estado_publico,
        "acepta_votos": votacion.esta_abierta,
        "fecha_apertura": _fecha(votacion.fecha_apertura),
        "fecha_cierre": _fecha(votacion.fecha_cierre),
        "opciones": [_serializar_opcion(o) for o in votacion.opciones.all()],
    }


def _serializar_categoria(categoria):
    votaciones = list(categoria.votaciones.all())
    return {
        "id": categoria.pk,
        "nombre": categoria.nombre,
        "descripcion": categoria.descripcion,
        "edicion": {
            "id": categoria.edicion.pk,
            "nombre": categoria.edicion.nombre,
            "anio": categoria.edicion.anio,
        },
        "total_opciones": sum(len(v.opciones.all()) for v in votaciones),
        "votaciones": [_serializar_votacion(v) for v in votaciones],
    }


@require_GET
@transaction.non_atomic_requests  # solo lectura: evita abrir una transacción (ATOMIC_REQUESTS) innecesaria
def categorias(request):
    """``GET /api/categorias/`` → JSON con categorías, votaciones y opciones."""
    consulta = Categoria.objects.filter(activa=True, edicion__activa=True).select_related("edicion")

    edicion = request.GET.get("edicion")
    if edicion is not None:
        if not edicion.isdigit():
            return JsonResponse({"error": "El parámetro «edicion» debe ser un número entero."}, status=400)
        consulta = consulta.filter(edicion_id=int(edicion))

    consulta = consulta.prefetch_related(
        Prefetch(
            "votaciones",
            queryset=Votacion.objects.publicas().prefetch_related(
                Prefetch("opciones", queryset=Opcion.objects.filter(activa=True))
            ),
        )
    ).order_by("-edicion__anio", "orden", "nombre")

    datos = [_serializar_categoria(c) for c in consulta]
    respuesta = JsonResponse(
        {"total": len(datos), "categorias": datos},
        json_dumps_params={"ensure_ascii": False},  # tildes legibles en el navegador y Postman
    )
    respuesta["Cache-Control"] = "no-store"  # los estados cambian con el tiempo
    return respuesta
