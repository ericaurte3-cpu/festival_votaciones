"""Formularios: gestión de ediciones (CU-05, RF-02) y emisión de votos (Entrega 3)."""
from django import forms

from .models import Edicion


class EdicionForm(forms.ModelForm):
    class Meta:
        model = Edicion
        fields = ["nombre", "anio", "descripcion", "fecha_inicio", "fecha_fin", "activa"]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 3}),
            "fecha_inicio": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "fecha_fin": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-check-input" if isinstance(campo.widget, forms.CheckboxInput) else "form-control"


class VotoForm(forms.Form):
    """Datos que envía el votante: solo la opción elegida y la confirmación.

    La edición, la categoría y la votación **no** se reciben del cliente: se derivan en el
    servidor a partir de la URL y de la opción (ver ``festival.servicios``). Las reglas de
    negocio se validan en el servicio; aquí solo se comprueba la forma de los datos.
    """

    opcion = forms.IntegerField(min_value=1, error_messages={
        "required": "Selecciona una opción para votar.",
        "invalid": "La opción enviada no es válida.",
        "min_value": "La opción enviada no es válida.",
    })
    confirmar = forms.BooleanField(required=False)
