# Sistema de Entradas con QR — Conferencia Voz Que Clama 2026

Sistema completo para gestionar asistentes a un evento: genera entradas PDF con código QR, las envía por email, y provee una app web de check-in para el día del evento.

---

## Estructura del proyecto

```
entradas-confe/
├── generar_entradas.py      ← Genera PDFs + envía emails + links de WhatsApp
├── checkin_app.py           ← App web de check-in (Flask)
├── crear_excel_ejemplo.py   ← Crea la planilla Excel de ejemplo
│
├── templates/
│   ├── login.html
│   └── checkin.html
├── static/
│   ├── styles.css
│   └── app.js
│
├── docs/
│   └── entrada_voz_que_clama.html   ← Diseño de referencia de la entrada
│
├── logo.jpeg                ← Banner del evento (para el email)
├── logoportada.png          ← Logo de portada (para la entrada PDF)
│
├── .env.example             ← Variables de entorno requeridas (copiar como .env)
├── requirements.txt         ← Dependencias Python
└── README.md
```

> Los archivos `asistentes.xlsx`, `entradas_generadas/` y `checkin.db` se generan en tiempo de ejecución y están en `.gitignore` porque contienen datos personales.

---

## Instalación

```bash
pip install -r requirements.txt
```

### Configurar variables de entorno

```bash
# Copiá el archivo de ejemplo y completá los valores
cp .env.example .env
```

Editá `.env` con tus credenciales reales. Ver la sección de cada script para más detalle.

---

## Módulo 1: Generador de entradas

### 1. Crear la planilla Excel

```bash
python crear_excel_ejemplo.py
```

Esto genera `asistentes.xlsx` con las columnas correctas. Completá los datos de tus asistentes:

| nombre_completo | dni | email | celular |
|---|---|---|---|
| Juan Pérez | 38123456 | juan@gmail.com | 3794123456 |

El script también detecta columnas con nombres alternativos ("name", "documento", "correo", "whatsapp", etc.).

### 2. Configurar el script

Abrí `generar_entradas.py` y completá la sección `CONFIG`:

```python
CONFIG = {
    "nombre_evento": "CONFERENCIA VOZ QUE CLAMA 2026",
    "evento_lema":   "LA META ES ÉL",
    "fecha_evento":  "Viernes 23 de octubre ...",
    "lugar_evento":  "Salón de Conferencias La Lola — Corrientes, Argentina",
    "logo_path":     "logo.jpeg",
    "gmail_usuario": "tuemail@gmail.com",
    # La contraseña va en el archivo .env como GMAIL_PASSWORD
    ...
}
```

### 3. Contraseña de aplicación de Gmail

Gmail no permite usar la contraseña normal desde scripts. Necesitás una **contraseña de aplicación**:

1. Cuenta Google → **Seguridad** → activar **Verificación en dos pasos**
2. Buscar **"Contraseñas de aplicación"**
3. Crear una → seleccionar "Correo"
4. Copiar los 16 caracteres al archivo `.env`:

```
GMAIL_PASSWORD=xxxx xxxx xxxx xxxx
```

### 4. Ejecutar

```bash
python generar_entradas.py
```

Opciones del menú:

```
1. Generar PDFs + Enviar emails (sin WhatsApp)
2. Generar PDFs + Enviar emails + Abrir WhatsApp uno por uno
3. Solo generar PDFs (sin enviar nada)
```

**Recomendación:** primero usá la opción **3** para verificar los PDFs, luego **1** para enviar todo.

Las entradas se guardan en `entradas_generadas/`. También se genera `entradas_generadas/links_whatsapp.txt` con los links de WhatsApp pre-armados.

### Contenido del QR

Cada QR codifica un JSON con los datos del asistente:

```json
{
  "id": 1,
  "nombre": "Juan Pérez",
  "dni": "38123456",
  "evento": "CONFERENCIA VOZ QUE CLAMA 2026"
}
```

---

## Módulo 2: App de check-in

App web que corre en la red local el día del evento. Escanea QRs con la cámara, registra el ingreso y evita doble check-in.

### Iniciar la app

```bash
python checkin_app.py
```

Desde cualquier dispositivo en la misma red Wi-Fi, abrir:

```
http://<IP-del-servidor>:5000
```

### Credenciales

Por defecto: usuario `admin` / contraseña `evento123`. Para cambiarlas, definir en `.env`:

```
CHECKIN_USERNAME=admin
CHECKIN_PASSWORD=tu-contraseña-segura
SECRET_KEY=una-clave-larga-y-aleatoria
```

### Funcionalidades

- **Escáner QR con la cámara** (BarcodeDetector nativo o jsQR incluido en `static/`, sin depender de internet para cargar librerías).
- **Pantalla de resultado tipo semáforo:** verde = ingresó, naranja = ya había ingresado (muestra a qué hora), rojo = entrada no válida / no está en la lista. Con sonido y vibración.
- **Varios celulares a la vez:** el servidor es la única fuente de verdad (SQLite con `UNIQUE` por entrada). Si dos celulares escanean el mismo QR al mismo tiempo, solo uno registra el ingreso y el otro ve "YA INGRESÓ". Todos los celulares se sincronizan cada 5 segundos.
- **Pestaña Lista:** todos los asistentes con buscador (nombre, DNI, congregación), filtros Todos / Ingresaron / Faltan, marcar ingreso a mano (para quien perdió el QR) y anular un ingreso hecho por error.
- Contador de presentes / total con barra de progreso, linterna y cambio de cámara, pantalla siempre encendida mientras se escanea.
- **Escanear con foto:** alternativa que funciona aun sin HTTPS.
- Valida el QR contra el Excel (ID + DNI) y muestra el nombre y la congregación que figuran en la lista. Si cambiás el Excel, la app lo recarga sola.
- Hora de ingreso en horario de Argentina (UTC-3) aunque el servidor esté en UTC.

> **Cámara en vivo = HTTPS.** Los celulares solo permiten la cámara en páginas HTTPS (o `localhost`).
> Con `http://<IP>:5000` en la red local la cámara en vivo NO funciona; ahí se usa «Escanear con foto» o la Lista.
> Para el evento usá el deploy en PythonAnywhere (HTTPS), ver `docs/DEPLOY_PYTHONANYWHERE.md`.

### Antes del evento

1. Cambiá `CHECKIN_PASSWORD` y `SECRET_KEY` en `.env` (por defecto son inseguros).
2. Subí el `asistentes.xlsx` definitivo y **no reordenes filas** después de generar las entradas: el ID del QR es la fila.
3. Borrá `checkin.db` si hiciste pruebas, para arrancar con cero ingresos.
4. Probá con 2 celulares el mismo QR a la vez.

---

## Problemas frecuentes

| Error | Solución |
|---|---|
| `SMTPAuthenticationError` | Verificar la contraseña de aplicación en `.env` |
| `ModuleNotFoundError` | Ejecutar `pip install -r requirements.txt` |
| QR no se escanea | Verificar que reportlab esté instalado y el PDF no esté corrupto |
| Número WhatsApp inválido | El celular debe tener 10 dígitos locales (ej: `3794123456`) |
| Cámara no disponible | Abrir la app por HTTPS (PythonAnywhere); mientras tanto usar «Escanear con foto» o la pestaña Lista |
