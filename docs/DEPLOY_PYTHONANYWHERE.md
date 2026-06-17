# Deploy de la app de check-in en PythonAnywhere

Esta guía te lleva de cero a una web accesible en internet con HTTPS,
login, escáner QR por cámara y verificación contra la lista de asistentes.

> Plan Free de PythonAnywhere alcanza para ~200 asistentes con 1–2 celulares
> escaneando. La URL queda como `https://TU_USUARIO.pythonanywhere.com`.

---

## 1. Crear cuenta en PythonAnywhere

1. Ir a https://www.pythonanywhere.com → **Pricing & signup** → **Create a Beginner account** (gratis).
2. Anotar tu usuario — lo vas a usar como subdominio.

## 2. Clonar el repo desde una consola Bash

En el dashboard de PythonAnywhere → **Consoles** → **New Bash console**:

```bash
git clone https://github.com/casellisofi/tickets-platform.git
cd tickets-platform
```

## 3. Instalar dependencias

```bash
pip3.10 install --user -r requirements.txt
```

> Si te pide otra versión de Python, cambiala (ej. `pip3.11`). Anotá la versión — la
> vas a usar en el paso 5.

## 4. Subir el Excel de asistentes

En el dashboard → **Files** → navegar a `tickets-platform/data/` y subir
`asistentes.xlsx` (el mismo que usás para generar las entradas).

> **Importante:** los IDs en el Excel deben coincidir con los IDs que están
> dentro de los QR generados. La app calcula el ID como `nº de fila - 1`
> (igual que `generar_entradas.py`). Si reordenás filas, los QR viejos dejan
> de funcionar.

## 5. Configurar la Web App

Dashboard → **Web** → **Add a new web app**:

1. **Domain:** dejar el default (`TU_USUARIO.pythonanywhere.com`).
2. **Framework:** elegir **Manual configuration** (NO "Flask", queremos el wizard manual).
3. **Python version:** la misma que usaste en el paso 3 (ej. 3.10).

Cuando termine, abrir la sección **Code** de esa misma pantalla y:

### 5a. Editar el archivo WSGI

Click en el link del archivo WSGI (algo como `/var/www/TU_USUARIO_pythonanywhere_com_wsgi.py`).

Borrar todo el contenido y pegar:

```python
import sys

path = "/home/TU_USUARIO/tickets-platform"
if path not in sys.path:
    sys.path.insert(0, path)

from flask_app import application
```

Reemplazar `TU_USUARIO` por tu usuario real. Guardar.

### 5b. Configurar Source code y Working directory

En la sección **Code** de la página Web:

- **Source code:** `/home/TU_USUARIO/tickets-platform`
- **Working directory:** `/home/TU_USUARIO/tickets-platform`

### 5c. Variables de entorno (opcional pero recomendado)

En la sección **Environment variables** (más abajo en la misma página):

| Variable | Valor |
|---|---|
| `SECRET_KEY` | Una cadena larga y aleatoria (ej. salida de `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `CHECKIN_USERNAME` | El usuario de login (default: `admin`) |
| `CHECKIN_PASSWORD` | La contraseña de login (cambiala — el default es público) |
| `CHECKIN_EVENT_LABEL` | Nombre del evento que aparece en la cabecera |

> **No subas un `.env` al repo.** En PythonAnywhere las variables se definen
> desde el panel y se inyectan al proceso WSGI.

### 5d. Reload

Botón verde grande arriba de la página: **Reload TU_USUARIO.pythonanywhere.com**.

## 6. Probar

Abrir `https://TU_USUARIO.pythonanywhere.com` en el celular:

- Tiene que aparecer el login.
- Loguearse con las credenciales del paso 5c (o `admin` / `evento123` si no las cambiaste).
- El navegador va a pedir permiso para la cámara — aceptar.
- Apuntar a un QR generado por `generar_entradas.py` — debería marcar el ingreso.

## 7. El día del evento

- Repartir la URL y credenciales a las personas que harán check-in.
- Cualquier celular Android con Chrome funciona out-of-the-box.
- iPhone/Safari también funciona (usa jsQR como fallback).
- La lista de presentes se actualiza al refrescar.
- Si alguien intenta entrar dos veces, la app lo rechaza con la hora del primer ingreso.

## 8. Después del evento

Para descargar la lista de presentes:

- **Files** → `tickets-platform/checkin.db` → Download.
- Abrir con [DB Browser for SQLite](https://sqlitebrowser.org/) o exportar a CSV.

---

## Troubleshooting

| Problema | Solución |
|---|---|
| `ModuleNotFoundError: flask` | Volver al paso 3 — chequear que la versión de Python en la consola es la misma que la del Web app |
| La cámara no abre en iPhone | Asegurate que la URL es `https://` (no http). Safari requiere HTTPS para cámara |
| "No existe asistente con entrada #X" | El ID del QR no está en `data/asistentes.xlsx` — verificar que subiste el Excel correcto |
| Cambié el Excel y no se refleja | La app detecta cambios por mtime automáticamente. Si no, **Reload** la web app |
| Errores 500 | **Web** → **Log files** → revisar el `error.log` |
