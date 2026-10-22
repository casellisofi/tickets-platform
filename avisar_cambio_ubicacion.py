"""
AVISO DE CAMBIO DE UBICACIÓN
============================
Envía por email y/o WhatsApp un aviso a las 25 personas cuya entrada fue
generada con la ubicación errónea ("Yapire"). La ubicación correcta es La Lola.

USO:
  python avisar_cambio_ubicacion.py                 -> vista previa (no envía nada)
  python avisar_cambio_ubicacion.py --email         -> envía solo emails
  python avisar_cambio_ubicacion.py --whatsapp      -> envía solo WhatsApp
  python avisar_cambio_ubicacion.py --email --whatsapp
  python avisar_cambio_ubicacion.py --email --whatsapp --solo "Abril"   -> prueba con una sola persona

Para WhatsApp: dejá WhatsApp Web abierto y logueado, y no muevas mouse/teclado.
Los envíos exitosos se registran en data/aviso_ubicacion_enviados.json para
no repetir un aviso si el script se vuelve a correr.
"""

import json
import os
import smtplib
import sys
import time
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import generar_entradas as ge
from generar_entradas import CONFIG

# Evita UnicodeEncodeError con emojis en consolas Windows (cp1252).
sys.stdout.reconfigure(encoding="utf-8")

# Nombre del PDF (sin "Entrada_" ni ".pdf") de cada persona afectada.
AFECTADOS = [
    "Abigail_Martinez",
    "Abril_Steinle",
    "Alan_Lionel_Gonzalez",
    "Analia_Cambiaso",
    "Anderson_da_Rocha_Fernandes",
    "Chapo_Noelia_Adriana",
    "Emanuel_Baukloh",
    "Francini_Gustavo_Daniel",
    "Gustavo_Escobar",
    "Jonatan_Ariel_Gonzalez",
    "Jorge_Jose_Baez",
    "Josias_Correa",
    "Juliana_Cristina_Siqueira_Fernandes",
    "Lourdes_Coronek",
    "Maira_Melanie_Ailen_Benitez",
    "Marcia_Lucrecia_Lourdes_Benitez",
    "Maximiliano_Vallejos",
    "Melina_Isabel_Barbona",
    "Samuel_Siqueira_Fernandes",
    "Silvero_Augusto_Andres",
    "Sofia_Caselli",
    "Sotelo_Maria_Laura",
    "Valentina_Fernandes_Siqueira",
    "Vera_Valeria_Andrea",
    "Ximena_Robledo",
]

LOG_PATH = "data/aviso_ubicacion_enviados.json"
PREVIEW_HTML = "data/aviso_ubicacion_preview.html"
ASUNTO = "📍 Importante: cambio de ubicación — Conferencia VOZ QUE CLAMA 2026"


# ── Mensajes ────────────────────────────────────────────────────

def mensaje_whatsapp(nombre):
    return (
        f"¡Hola {nombre.split()[0]}! 👋\n\n"
        f"Estamos a *7 días* de la *{CONFIG['nombre_evento']}* 🙌\n\n"
        f"Queremos avisarte que hubo una modificación del lugar donde se va a realizar la conferencia. "
        f"El nuevo lugar es:\n\n"
        f"📍 *La Lola Eventos*\n"
        f"Cam. al Perichón, W3400 Corrientes\n"
        f"🗺️ {CONFIG['maps_url']}\n\n"
        f"📅 *Fecha:* {CONFIG['fecha_evento']}\n\n"
        f"Tu entrada y el código QR siguen siendo válidos, no hace falta que hagas nada más. "
        f"¡Te esperamos! 🎉"
    )


def html_email(nombre, con_imagen=True):
    banner = ""
    if con_imagen and CONFIG.get("logo_path") and os.path.exists(CONFIG["logo_path"]):
        banner = (
            '<div style="text-align:center; margin:0 auto 20px; max-width:600px;">'
            '<img src="cid:banner_img" alt="CONFERENCIA VOZ QUE CLAMA 2026" '
            'style="width:100%; height:auto; border-radius:16px; display:block;"></div>'
        )
    lbl = ('padding: 6px 0; font-size: 11px; font-weight: 700; letter-spacing: 0.12em; '
           'color: #a89e8e; text-transform: uppercase;')
    val = 'padding: 6px 0; font-size: 14px; font-weight: 600; color: #0f172a;'
    return f"""
    <html><body style="font-family: Arial, sans-serif; color: #333; max-width: 640px; margin: auto; background: #f0f2f5; padding: 20px;">
      <div style="background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 24px rgba(0,0,0,0.08);">

        {banner}

        <div style="background: #050a14; padding: 28px 32px 24px;">
          <p style="margin: 0 0 6px; font-size: 11px; font-weight: 700; letter-spacing: 0.15em; color: #c9a84c; text-transform: uppercase;">Aviso importante · 2026</p>
          <h1 style="margin: 0 0 4px; font-size: 22px; font-weight: 700; color: #ffffff; letter-spacing: 0.04em; text-transform: uppercase;">Conferencia Voz que Clama</h1>
          <p style="margin: 0; font-size: 16px; color: #c9a84c; font-style: italic;">"La meta es Él"</p>
        </div>

        <div style="padding: 28px 32px;">
          <p style="margin: 0 0 16px; font-size: 16px; color: #444;">Hola, <strong style="color: #0f172a;">{nombre.split()[0]}</strong>.</p>

          <p style="margin: 0 0 16px; font-size: 15px; color: #444;"><strong>¡Estamos a 7 días de la conferencia!</strong> 🙌</p>

          <p style="margin: 0 0 20px; font-size: 14px; color: #555;">Queremos avisarte que hubo una <strong>modificación del lugar</strong> donde se va a realizar la conferencia. El nuevo lugar es <strong>La Lola Eventos</strong>:</p>

          <div style="background: #f9f7f4; border: 1px solid #ede8e0; border-radius: 12px; padding: 20px 22px; margin-bottom: 20px;">
            <table style="width: 100%; border-collapse: collapse;">
              <tr>
                <td style="{lbl} width: 38%;">Lugar</td>
                <td style="{val}">{CONFIG['lugar_evento']}</td>
              </tr>
              <tr style="border-top: 1px solid #ede8e0;">
                <td style="{lbl}">Fecha</td>
                <td style="{val}">{CONFIG['fecha_evento']}</td>
              </tr>
            </table>
          </div>

          <p style="margin: 0 0 24px; font-size: 14px; color: #555;">Tu entrada y su código QR siguen siendo válidos: no hace falta que hagas nada más. ¡Te esperamos!</p>

          <a href="{CONFIG.get('maps_url','')}" style="display: inline-block; text-decoration: none; background: #050a14; color: #c9a84c; padding: 12px 22px; border-radius: 8px; font-weight: 700; font-size: 13px; letter-spacing: 0.08em;">VER EN GOOGLE MAPS</a>

          <p style="margin: 24px 0 0; color: #aaa; font-size: 12px; border-top: 1px solid #ede8e0; padding-top: 16px;">Disculpá las molestias.</p>
        </div>

      </div>
    </body></html>
    """


# ── Envío ───────────────────────────────────────────────────────

def enviar_email_aviso(asistente):
    msg = MIMEMultipart("related")
    msg["From"] = CONFIG["gmail_usuario"]
    msg["To"] = asistente["email"]
    msg["Subject"] = ASUNTO
    msg.attach(MIMEText(html_email(asistente["nombre"]), "html"))

    if CONFIG.get("logo_path") and os.path.exists(CONFIG["logo_path"]):
        with open(CONFIG["logo_path"], "rb") as f:
            img = MIMEImage(f.read())
        img.add_header("Content-ID", "<banner_img>")
        img.add_header("Content-Disposition", "inline", filename=os.path.basename(CONFIG["logo_path"]))
        msg.attach(img)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as servidor:
        servidor.login(CONFIG["gmail_usuario"], CONFIG["gmail_password"])
        servidor.sendmail(CONFIG["gmail_usuario"], asistente["email"], msg.as_string())


def enviar_whatsapp_aviso(asistente):
    import pywhatkit
    pywhatkit.sendwhatmsg_instantly(
        phone_no=ge._normalizar_numero_wa(asistente["celular"]),
        message=mensaje_whatsapp(asistente["nombre"]),
        wait_time=20,
        tab_close=False,
    )
    time.sleep(8)
    ge._cerrar_pestana()


# ── Selección y registro ────────────────────────────────────────

def seleccionar_afectados():
    por_archivo = {"_".join(a["nombre"].split()): a for a in ge.leer_excel()}
    afectados, faltantes = [], []
    for clave in AFECTADOS:
        (afectados if clave in por_archivo else faltantes).append(por_archivo.get(clave, clave))
    return afectados, faltantes


def cargar_log():
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"email": [], "whatsapp": []}


def guardar_log(log):
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def vista_previa(afectados):
    print("\n" + "=" * 60)
    print("  VISTA PREVIA (no se envía nada)")
    print("=" * 60)
    print(f"\nAsunto del email: {ASUNTO}\n")
    print("--- WhatsApp (ejemplo con el primer destinatario) ---\n")
    print(mensaje_whatsapp(afectados[0]["nombre"]))
    with open(PREVIEW_HTML, "w", encoding="utf-8") as f:
        f.write(html_email(afectados[0]["nombre"], con_imagen=False))
    print(f"\n--- Email: abrí {os.path.abspath(PREVIEW_HTML)} en el navegador ---")
    print("\n--- Destinatarios ---")
    for a in afectados:
        ok_e, _ = ge.validar_email(a["email"])
        ok_c, _ = ge.validar_celular(a["celular"])
        print(f"  {a['nombre']:38s} 📧 {'OK ' if ok_e else 'MAL'} {a['email']:35s} 📱 {'OK ' if ok_c else 'MAL'} {a['celular']}")
    print(f"\nTotal: {len(afectados)}")
    print("\nPara enviar: python avisar_cambio_ubicacion.py --email --whatsapp")


def main():
    argv = sys.argv[1:]
    args = set(argv)
    afectados, faltantes = seleccionar_afectados()
    if "--solo" in argv:
        # --solo "texto": limita el envío a quienes tengan ese texto en el nombre.
        texto = argv[argv.index("--solo") + 1].lower()
        afectados = [a for a in afectados if texto in a["nombre"].lower()]
        faltantes = []
        print(f"🔎 --solo '{texto}': {len(afectados)} coincidencia(s)")
    if faltantes:
        print(f"⚠️  No se encontraron en el Excel: {', '.join(faltantes)}")
    if not afectados:
        return

    quiere_email = "--email" in args
    quiere_wa = "--whatsapp" in args
    if not (quiere_email or quiere_wa):
        vista_previa(afectados)
        return

    if quiere_email and not CONFIG["gmail_password"]:
        print("❌ Falta GMAIL_PASSWORD (variable de entorno o .env).")
        return

    log = cargar_log()
    errores = []
    for i, a in enumerate(afectados, 1):
        print(f"\n[{i}/{len(afectados)}] {a['nombre']}")
        clave = "_".join(a["nombre"].split())

        if quiere_email and clave not in log["email"]:
            ok, motivo = ge.validar_email(a["email"])
            if not ok:
                print(f"  ⚠️  Email omitido ({motivo})")
                errores.append(f"{a['nombre']}: email {motivo}")
            else:
                try:
                    enviar_email_aviso(a)
                    log["email"].append(clave)
                    guardar_log(log)
                    print(f"  ✅ Email enviado a {a['email']}")
                except Exception as e:
                    print(f"  ⚠️  Error email: {e}")
                    errores.append(f"{a['nombre']}: email falló — {e}")

        if quiere_wa and clave not in log["whatsapp"]:
            ok, motivo = ge.validar_celular(a["celular"])
            if not ok:
                print(f"  ⚠️  WhatsApp omitido ({motivo})")
                errores.append(f"{a['nombre']}: celular {motivo}")
            else:
                try:
                    enviar_whatsapp_aviso(a)
                    log["whatsapp"].append(clave)
                    guardar_log(log)
                    print(f"  ✅ WhatsApp enviado a {a['celular']}")
                except Exception as e:
                    print(f"  ⚠️  Error WhatsApp: {e}")
                    errores.append(f"{a['nombre']}: WhatsApp falló — {e}")

    print("\n" + "=" * 50)
    print(f"Emails enviados (acumulado): {len(log['email'])}/{len(afectados)}")
    print(f"WhatsApp enviados (acumulado): {len(log['whatsapp'])}/{len(afectados)}")
    if errores:
        print(f"\n⚠️  Errores ({len(errores)}):")
        for e in errores:
            print(f"   - {e}")


if __name__ == "__main__":
    main()
