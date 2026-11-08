/* Comportamiento del cliente (JavaScript). Sin dependencias adicionales a Bootstrap.
   1. Validación de formularios con estilos de Bootstrap.
   2. Mostrar / ocultar la contraseña.
   3. Cuenta regresiva hasta la apertura o el cierre de una votación.
   4. Cierre automático de los mensajes informativos. */
(function () {
  "use strict";

  // 1. Validación en el navegador (la validación definitiva se hace siempre en el servidor).
  document.querySelectorAll("form.needs-validation").forEach(function (form) {
    form.addEventListener("submit", function (evento) {
      if (!form.checkValidity()) {
        evento.preventDefault();
        evento.stopPropagation();
      }
      form.classList.add("was-validated");
    });
  });

  // 2. Mostrar / ocultar contraseña.
  document.querySelectorAll("[data-toggle-password]").forEach(function (boton) {
    boton.addEventListener("click", function () {
      var campo = document.getElementById(boton.dataset.togglePassword);
      if (!campo) { return; }
      var visible = campo.type === "text";
      campo.type = visible ? "password" : "text";
      boton.textContent = visible ? "Mostrar" : "Ocultar";
      boton.setAttribute("aria-pressed", String(!visible));
    });
  });

  // 3. Cuenta regresiva: <span data-countdown="2027-04-28T08:00:00-05:00" data-prefix="Abre en ">
  function formatear(ms) {
    var minutos = Math.floor(ms / 60000);
    var dias = Math.floor(minutos / 1440);
    var horas = Math.floor((minutos % 1440) / 60);
    var min = minutos % 60;
    if (dias > 0) { return dias + " d " + horas + " h " + min + " min"; }
    if (horas > 0) { return horas + " h " + min + " min"; }
    return Math.max(min, 0) + " min";
  }
  var contadores = document.querySelectorAll("[data-countdown]");
  function actualizar() {
    contadores.forEach(function (el) {
      var restante = new Date(el.dataset.countdown).getTime() - Date.now();
      if (isNaN(restante)) { return; }
      el.textContent = restante > 0 ? (el.dataset.prefix || "") + formatear(restante) : (el.dataset.final || "");
    });
  }
  if (contadores.length) {
    actualizar();
    setInterval(actualizar, 30000);
  }

  // 4. Los mensajes de éxito se cierran solos tras unos segundos.
  document.querySelectorAll(".alert[data-autocerrar]").forEach(function (alerta) {
    setTimeout(function () {
      if (window.bootstrap) { bootstrap.Alert.getOrCreateInstance(alerta).close(); }
    }, 6000);
  });
})();
