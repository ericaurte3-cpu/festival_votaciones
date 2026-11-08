# Sistema Web de Votaciones · Festival de la Leyenda Vallenata 2027

Desarrollo Web · Fundación Universitaria del Área Andina · **Entrega 3: módulo de votaciones, validaciones y API GET**.

Aplicación **Django + MySQL** (patrón MVT) que continúa el proyecto de la Entrega 2. Esta entrega agrega el proceso de votación completo: consultar categorías y opciones, **registrar un voto real en MySQL**, validar restricciones en el servidor, consultar la participación y exponer una **API GET** con respuesta JSON.

> **Regla central:** cada usuario puede elegir **una sola opción por categoría y edición**. Puede votar en otras categorías, pero no emitir un segundo voto en la misma categoría, aunque esta tenga varios subeventos (votaciones). Se garantiza con una restricción `UNIQUE` en MySQL.

## Qué incluye

| Entrega | Contenido |
|---|---|
| 2 | Modelo **Edición → Categoría → Votación → Opción**, Django Admin, registro e inicio de sesión por correo, interfaz pública responsive (Bootstrap local), gestión de ediciones, auditoría. |
| **3** | Modelo **`Voto`**, votación en dos pasos (selección → confirmación), validaciones de servidor, restricción de unicidad en BD con manejo de concurrencia, historial «Mis votos», consulta administrativa de votos y **`GET /api/categorias/`**. |

## Tecnologías y versiones

| Componente | Versión |
|---|---|
| Python | 3.10 o superior (desarrollado y probado con **3.13**) |
| Django | **5.2 LTS** (`>=5.2,<5.3`) |
| MySQL | 8.x (las pruebas también se ejecutaron en MariaDB 10.11) |
| mysqlclient | `>=2.2` (conector MySQL) |
| python-decouple | `>=3.8` (lectura de `.env`) |
| Interfaz | HTML5, CSS3, JavaScript y Bootstrap 5 (incluido localmente, sin CDN) |

Dependencias exactas en [`requirements.txt`](requirements.txt).

## Instalación y ejecución (Windows, PowerShell)

```powershell
# 1. Clonar y entrar al proyecto
git clone <URL_DEL_REPOSITORIO>
cd festival_votaciones

# 2. Entorno virtual y dependencias
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Crear la base de datos y un usuario en MySQL (cliente mysql, como root)
#    CREATE DATABASE festival_votaciones CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
#    CREATE USER 'festival_user'@'localhost' IDENTIFIED BY 'TU_CONTRASEÑA';
#    GRANT ALL PRIVILEGES ON festival_votaciones.* TO 'festival_user'@'localhost';
#    GRANT ALL PRIVILEGES ON test_festival_votaciones.* TO 'festival_user'@'localhost';  -- para las pruebas
#    FLUSH PRIVILEGES;

# 4. Configuración local (el archivo .env NO se sube a git)
copy .env.example .env
#    Edite .env: ponga su contraseña de MySQL en DB_PASSWORD y una DJANGO_SECRET_KEY propia

# 5. Migraciones (crean las tablas, incluida la de votos y su restricción UNIQUE)
python manage.py migrate

# 6. Datos de prueba ficticios + 3 votantes de prueba + administrador
python manage.py cargar_datos_prueba --votantes 3 --password "UnaClaveDePrueba-2027"
python manage.py createsuperuser

# 7. Servidor de desarrollo
python manage.py runserver
```

En Linux/macOS: `source venv/bin/activate` en lugar de `venv\Scripts\Activate.ps1` y `cp` en lugar de `copy`.

- Sitio público: <http://127.0.0.1:8000/> · Administración: <http://127.0.0.1:8000/admin/>
- Votantes de prueba: `votante1@example.com`, `votante2@example.com`, `votante3@example.com`, con la contraseña indicada en `--password`. Si se omite `--password`, el comando genera una aleatoria y la muestra una sola vez (no hay contraseñas escritas en el código).
- `cargar_datos_prueba --limpiar` reinicia los datos de prueba (también borra los votos).

> Si `pip install mysqlclient` falla en Windows, actualice pip (`python -m pip install -U pip`) para usar la rueda precompilada; en Linux instale antes `libmysqlclient-dev` (o `libmariadb-dev`) y `pkg-config`.

### Variables de entorno (`.env`)

Plantilla sin secretos en [`.env.example`](.env.example). **Nunca** suba el `.env` real: contiene la contraseña de MySQL y la clave secreta. Está en `.gitignore`.

## Cómo probar el módulo de votaciones

1. Inicie sesión como `votante1@example.com`.
2. Abra una categoría con votación abierta (por ejemplo «Acordeonero profesional»), elija una opción y pulse **Continuar y confirmar voto**; revise el resumen y pulse **Confirmar voto**.
3. Intente votar otra vez en la misma categoría (otra opción, o en el subevento «Semifinal»): el sistema lo rechaza.
4. Vote en otra categoría («Canción vallenata inédita»): se permite.
5. Consulte **Mis votos**. Como administrador, vea **Administración → Votos** (solo lectura).
6. Abra <http://127.0.0.1:8000/api/categorias/> para ver el JSON.

## API GET

`GET /api/categorias/` devuelve, en JSON, las categorías públicas (categoría y edición activas) con sus votaciones (sin borradores) y las opciones activas, leídas de MySQL. No requiere sesión y no expone datos de usuarios ni de votos.

```json
{
  "total": 7,
  "categorias": [
    {
      "id": 1,
      "nombre": "Acordeonero profesional",
      "descripcion": "Concurso central del Festival de música tradicional.",
      "edicion": {"id": 1, "nombre": "Festival de la Leyenda Vallenata", "anio": 2027},
      "total_opciones": 7,
      "votaciones": [
        {
          "id": 1,
          "nombre": "Votación del público · Acordeonero profesional 2027",
          "estado": "abierta",
          "acepta_votos": true,
          "fecha_apertura": "2026-11-04T13:32:31-05:00",
          "fecha_cierre": "2026-11-10T13:32:31-05:00",
          "opciones": [
            {"id": 1, "nombre": "Participante de prueba 1", "descripcion": "...", "orden": 1}
          ]
        }
      ]
    }
  ]
}
```

- Parámetro opcional `?edicion=<id>` filtra por edición (valor no numérico → `400` con JSON de error).
- Solo acepta `GET` (otros métodos → `405`; un `POST` sin token CSRF recibe `403` antes de llegar a la vista). Usa 3 consultas SQL sin importar el volumen (`select_related`/`prefetch_related`).
- Si la API se ejecuta en `localhost`, solo es accesible desde el equipo que ejecuta el servidor.

## Dónde está cada cosa (para la revisión)

| Requisito | Archivo |
|---|---|
| Modelo `Voto` y **restricción de unicidad** (`voto_unico_usuario_categoria_edicion`) | [`festival/models.py`](festival/models.py) (clase `Voto`) |
| Migración de la tabla de votos y su UNIQUE | [`festival/migrations/0003_voto.py`](festival/migrations/0003_voto.py) |
| **Control de duplicados**, validaciones y manejo de `IntegrityError` | [`festival/servicios.py`](festival/servicios.py) |
| Vistas de votación (POST + CSRF + login) e historial | [`festival/views.py`](festival/views.py) (`VotarView`, `MisVotosView`) |
| Formulario de voto | [`festival/forms.py`](festival/forms.py) (`VotoForm`) |
| **API GET `/api/categorias/`** | [`festival/api.py`](festival/api.py) |
| Rutas | [`festival/urls.py`](festival/urls.py) |
| Consulta administrativa de votos (solo lectura) | [`festival/admin.py`](festival/admin.py) (`VotoAdmin`) |
| Plantillas de votación | `templates/festival/votacion.html`, `confirmar_voto.html`, `mis_votos.html` |
| Pruebas CP-01 a CP-10 | [`festival/tests_votos.py`](festival/tests_votos.py) |
| Datos de prueba | [`festival/management/commands/cargar_datos_prueba.py`](festival/management/commands/cargar_datos_prueba.py) |

## Diseño: cómo se garantiza un voto por categoría y edición

1. **Base de datos (garantía definitiva):** `UniqueConstraint(usuario, categoria, edicion)` en la tabla `festival_voto`. Edición y categoría se guardan en el propio voto porque una restricción `UNIQUE` solo puede usar columnas de la misma tabla.
2. **Servidor (mensajes claros):** `servicios.validar_voto` comprueba antes de escribir que la votación esté abierta (estado y periodo), que su categoría y edición estén activas, que la opción exista, esté activa y **pertenezca a la votación**, y que el usuario no haya votado ya en la categoría.
3. **Concurrencia:** si dos solicitudes pasan la validación a la vez, ambas intentan el `INSERT` y MySQL admite solo una; la otra recibe `IntegrityError`, que se captura y se informa como voto duplicado (sin error 500). El `transaction.atomic()` interno crea un *savepoint* para no invalidar la transacción de la petición (`ATOMIC_REQUESTS=True`).
4. **Confianza cero en el cliente:** la edición, categoría y votación **no** se leen del formulario; se derivan de la opción validada.
5. **Integridad histórica:** las claves foráneas de `Voto` son `PROTECT`; un voto no desaparece por borrar en cascada una opción, categoría, edición o usuario.

## Pruebas

```powershell
python manage.py test                       # todo el proyecto (105 pruebas)
python manage.py test festival.tests_votos -v 2   # solo el módulo de votaciones (CP-01 a CP-10)
```

Requiere el permiso `GRANT ... test_festival_votaciones.*` del paso 3 (Django crea y elimina una base de datos de pruebas). Las pruebas de concurrencia (CP-09) usan varios hilos con conexiones reales a MySQL.

| Caso | Qué verifica | Clases/pruebas |
|---|---|---|
| CP-01 | Voto válido se registra en MySQL | `CP01VotoValidoTests` |
| CP-02 | Segundo voto en la misma categoría (otra opción o subevento) se rechaza | `CP02VotoDuplicadoTests` |
| CP-03 | Voto en otra categoría se permite | `CP03OtraCategoriaTests` |
| CP-04 | Usuario no autenticado debe iniciar sesión | `CP04AutenticacionTests` |
| CP-05 | Votación cerrada/borrador/fuera de periodo/categoría inactiva se rechaza | `CP05VotacionNoHabilitadaTests` |
| CP-06 | Opción de otra categoría o inválida se rechaza | `CP06OpcionInvalidaTests` |
| CP-07 | «Mis votos» muestra los registros correctos | `CP07MisVotosTests` |
| CP-08 | Administrador consulta los votos (coinciden con MySQL) | `CP08AdministracionTests` |
| CP-09 | Dos o más solicitudes simultáneas → un solo voto | `CP09ConcurrenciaTests` |
| CP-10 | `GET /api/categorias/` devuelve JSON válido con datos reales | `CP10ApiCategoriasTests` |
| — | Protección CSRF | `CSRFTests` |

## Rutas principales

| Ruta | Descripción |
|---|---|
| `/` | Edición vigente y sus categorías |
| `/ediciones/`, `/ediciones/<id>/` | Ediciones activas y sus categorías |
| `/categorias/<id>/` | Votaciones de una categoría (indica si ya votó) |
| `/votaciones/<id>/` | Opciones y formulario de voto |
| `/votaciones/<id>/votar/` | **POST**: selección → confirmación → registro (requiere sesión y CSRF) |
| `/mis-votos/` | Categorías en las que el usuario ya votó |
| `/api/categorias/` | **API GET** (JSON) |
| `/gestion/`, `/gestion/ediciones/` | Panel y gestión de ediciones (personal) |
| `/cuentas/registro/`, `/cuentas/ingresar/`, `/cuentas/salir/` | Autenticación (el cierre de sesión es por POST) |
| `/admin/` | Django Admin (incluye **Votos**, solo lectura) |

## Perfiles y permisos

Al migrar se crea el grupo **Administrador** (ediciones, categorías, votaciones, opciones, auditoría y **consulta de votos**). Para dar acceso: en `/admin/` cree el usuario, marque *Es staff* y asígnelo a ese grupo. Un usuario *staff* sin el grupo no puede gestionar contenido ni ver votos. Los votos son de solo lectura para todos, incluido el superusuario: solo se crean desde el sitio público.

## Estructura

```
festival_votaciones/
├── manage.py
├── requirements.txt
├── .env.example            # plantilla de configuración (sin secretos)
├── config/                 # settings, urls raíz, wsgi
├── festival/               # modelos (incl. Voto), servicios, vistas, API, admin, pruebas, comandos
├── cuentas/                # registro, login, logout
├── templates/              # base.html, festival/*, registration/*
└── static/                 # css/estilos.css, js/app.js, vendor/bootstrap (local)
```

## Seguridad

- Contraseña de MySQL, `SECRET_KEY` y demás valores sensibles se leen de variables de entorno (`.env`), nunca del código; `.env` está ignorado por git.
- Contraseñas de usuarios con hash PBKDF2; protección **CSRF** activa en todos los formularios (el voto sin token recibe `403`).
- Autenticación obligatoria para votar; validación de datos y de reglas de negocio en el servidor; consultas con el ORM (sin SQL concatenado).
- Todos los datos incluidos son **datos de prueba**; ningún participante corresponde a una persona real.
- `DJANGO_DEBUG` está en `False` por defecto. Antes de desplegar: `DJANGO_SECRET_KEY` propia, `DJANGO_ALLOWED_HOSTS` definido y `DJANGO_HTTPS=True`; verifique con `python manage.py check --deploy`.

## Limitaciones conocidas y pendientes

- La verificación de identidad del votante (correo confirmado, documento) y la publicación de resultados están **pendientes de validación con la Fundación**.
- No hay límite de intentos (rate limiting) en el inicio de sesión ni en el endpoint de voto; se recomienda agregarlo antes de producción (por ejemplo `django-axes` o un limitador en el servidor web).
- La API es de solo lectura (GET); no se implementa API de votación por POST, que no es requerida en esta entrega.
