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

- Escaneo QR con la cámara del dispositivo (usa `BarcodeDetector` del navegador)
- Ingreso manual del JSON del QR como fallback
- Muestra nombre, DNI y número de entrada antes de confirmar
- Previene doble check-in de la misma entrada
- Lista de asistentes marcados en tiempo real
- Registro guardado en `checkin.db` (SQLite local)

---

## Problemas frecuentes

| Error | Solución |
|---|---|
| `SMTPAuthenticationError` | Verificar la contraseña de aplicación en `.env` |
| `ModuleNotFoundError` | Ejecutar `pip install -r requirements.txt` |
| QR no se escanea | Verificar que reportlab esté instalado y el PDF no esté corrupto |
| Número WhatsApp inválido | El celular debe tener 10 dígitos locales (ej: `3794123456`) |
| Cámara no disponible | Usar el ingreso manual de JSON en la app de check-in |
