"""
GENERADOR DE ENTRADAS CON QR
==============================
Lee un archivo Excel con los asistentes y genera:
  1. Una entrada PDF personalizada con QR
  2. Envío por email (Gmail)
  3. Link de WhatsApp para enviar manualmente

DEPENDENCIAS (instalar una sola vez):
  pip install qrcode[pil] pillow openpyxl reportlab

CONFIGURACIÓN:
  Completar las variables de la sección CONFIG antes de ejecutar.
"""

import qrcode
import json
import os
import smtplib

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import urllib.parse
import webbrowser
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import openpyxl
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io
import tempfile

# Fuentes elegantes — Palatino > Georgia > Times como fallback
_FONT_REG  = "Times-Roman"
_FONT_BOLD = "Times-Bold"
_FONT_ITAL = "Times-Italic"
try:
    _wf = "C:\\Windows\\Fonts\\"
    pdfmetrics.registerFont(TTFont("Palatino",        _wf + "pala.ttf"))
    pdfmetrics.registerFont(TTFont("Palatino-Bold",   _wf + "palab.ttf"))
    pdfmetrics.registerFont(TTFont("Palatino-Italic", _wf + "palai.ttf"))
    _FONT_REG  = "Palatino"
    _FONT_BOLD = "Palatino-Bold"
    _FONT_ITAL = "Palatino-Italic"
except Exception:
    try:
        _wf = "C:\\Windows\\Fonts\\"
        pdfmetrics.registerFont(TTFont("Georgia",        _wf + "georgia.ttf"))
        pdfmetrics.registerFont(TTFont("Georgia-Bold",   _wf + "georgiab.ttf"))
        pdfmetrics.registerFont(TTFont("Georgia-Italic", _wf + "georgiai.ttf"))
        _FONT_REG  = "Georgia"
        _FONT_BOLD = "Georgia-Bold"
        _FONT_ITAL = "Georgia-Italic"
    except Exception:
        pass

# ============================================================
#  CONFIG — COMPLETAR ANTES DE EJECUTAR
# ============================================================
CONFIG = {
    # Datos del evento
    "nombre_evento": "CONFERENCIA VOZ QUE CLAMA 2026",
    "evento_lema": "LA META ES ÉL",
    "fecha_evento":  "Viernes 23 de octubre 09:00hs al Sábado 24 de octubre 22:30hs",
    "lugar_evento":  "Salón de Conferencias \"Yapire\" - Corrientes, Argentina",

    # Logo del evento (ruta a imagen PNG/JPG, o None para no usar logo)
    "logo_path": "assets/logo.jpeg",
    # Logo de portada (parte superior de la entrada)
    "logo_portada_path": "assets/logoportada.png",

    # Gmail para enviar
    "gmail_usuario": "conferenciavozqueclama@gmail.com",
    # Cargá la contraseña de aplicación con: set GMAIL_PASSWORD=xxxx xxxx xxxx xxxx
    # o definila en un archivo .env (nunca la commitees al repositorio)
    "gmail_password": os.environ.get("GMAIL_PASSWORD", ""),

    # En modo de prueba, solo procesar este email.
    # Si está en None, se procesa todo el Excel.
    "test_email": None,

    # Número WhatsApp del organizador (con código de país, sin + ni espacios)
    # Se usa para el link de contacto en la entrada, NO para el envío
    "whatsapp_organizador": "3794046620",

    # Link de Google Maps del lugar
    "maps_url": "https://maps.app.goo.gl/H1apm6XmL8bmH9Hr6",

    # Archivo Excel con los asistentes
    # Columnas esperadas: nombre_completo | dni | email | celular
    "archivo_excel": "data/asistentes.xlsx",

    # Carpeta donde se guardan las entradas generadas
    "carpeta_salida": "data/entradas_generadas",

    # Color principal de la entrada (RGB)
    "color_primario": (15, 23, 42),    # Negro azulado (diseño del ticket)
}
# ============================================================


def crear_carpeta_salida():
    Path(CONFIG["carpeta_salida"]).mkdir(exist_ok=True)


def leer_excel():
    """Lee el Excel y devuelve lista de dicts con los asistentes."""
    wb = openpyxl.load_workbook(CONFIG["archivo_excel"])
    ws = wb.active

    # Leer encabezados (primera fila)
    headers = [str(cell.value).strip().lower() if cell.value else "" for cell in ws[1]]

    # Mapear columnas flexiblemente
    col_map = {}
    for i, h in enumerate(headers):
        if any(x in h for x in ["nombre", "name"]):
            col_map["nombre"] = i
        elif "dni" in h or "documento" in h:
            col_map["dni"] = i
        elif "email" in h or "mail" in h or "gmail" in h or "correo" in h:
            col_map["email"] = i
        elif "celular" in h or "telefono" in h or "phone" in h or "whatsapp" in h:
            col_map["celular"] = i

    asistentes = []
    for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not any(row):  # Fila vacía
            continue
        asistente = {
            "id": row_num - 1,  # ID correlativo
            "nombre": str(row[col_map.get("nombre", 0)] or "").strip(),
            "dni":    str(row[col_map.get("dni", 1)] or "").strip(),
            "email":  str(row[col_map.get("email", 2)] or "").strip(),
            "celular": str(row[col_map.get("celular", 3)] or "").strip(),
        }
        if asistente["nombre"]:  # Solo procesar filas con nombre
            asistentes.append(asistente)

    print(f"✅ {len(asistentes)} asistentes encontrados en el Excel")
    return asistentes


def generar_datos_qr(asistente):
    """Genera el string JSON que irá codificado en el QR."""
    datos = {
        "id":     asistente["id"],
        "nombre": asistente["nombre"],
        "dni":    asistente["dni"],
        "evento": CONFIG["nombre_evento"],
    }
    return json.dumps(datos, ensure_ascii=False)


def generar_imagen_qr(datos_qr):
    """Genera y retorna la imagen QR como objeto PIL."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=8,
        border=2,
    )
    qr.add_data(datos_qr)
    qr.make(fit=True)

    r, g, b = CONFIG["color_primario"]
    img_qr = qr.make_image(fill_color=(r, g, b), back_color="white")
    return img_qr.convert("RGB")


def generar_entrada_pdf(asistente):
    """Genera el PDF de la entrada y lo guarda. Retorna la ruta del archivo."""
    nombre_archivo = f"entrada_{asistente['id']:03d}_{asistente['nombre'].replace(' ', '_')}.pdf"
    ruta_pdf = os.path.join(CONFIG["carpeta_salida"], nombre_archivo)

    datos_qr = generar_datos_qr(asistente)
    img_qr_pil = generar_imagen_qr(datos_qr)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        img_qr_pil.save(tmp.name)
        qr_tmp_path = tmp.name

    doc = SimpleDocTemplate(
        ruta_pdf,
        pagesize=A4,
        leftMargin=2.5*cm,
        rightMargin=2.5*cm,
        topMargin=2.5*cm,
        bottomMargin=2.5*cm,
    )
    W = A4[0] - 5*cm  # ancho útil del story (~16 cm)

    # Colores del diseño
    C_HDR    = colors.HexColor("#050a14")
    C_GOLD   = colors.HexColor("#c9a84c")
    C_GOLD_D = colors.HexColor("#8a6010")
    C_FOOT   = colors.HexColor("#faf8f5")
    C_CARD   = colors.HexColor("#f9f7f4")
    C_BRDR   = colors.HexColor("#ede8e0")
    C_DARK   = colors.HexColor("#0f172a")
    C_MED    = colors.HexColor("#4a4038")
    C_MUTE   = colors.HexColor("#a89e8e")
    C_DASH   = colors.HexColor("#ddd8ce")

    # Estilos de párrafo
    s_tag   = ParagraphStyle("tag",   fontSize=7,  fontName=_FONT_BOLD, textColor=C_GOLD)
    s_title = ParagraphStyle("title", fontSize=18, fontName=_FONT_BOLD, textColor=colors.white, spaceAfter=2)
    s_sub   = ParagraphStyle("sub",   fontSize=13, fontName=_FONT_ITAL, textColor=C_GOLD)
    s_lbl   = ParagraphStyle("lbl",   fontSize=7,  fontName=_FONT_BOLD, textColor=C_MUTE, spaceAfter=1)
    s_lbl_r = ParagraphStyle("lbl_r", fontSize=7,  fontName=_FONT_BOLD, textColor=C_MUTE,
                              alignment=TA_RIGHT, spaceAfter=1)
    s_name  = ParagraphStyle("name",  fontSize=15, fontName=_FONT_BOLD, textColor=C_DARK)
    s_dni   = ParagraphStyle("dni",   fontSize=12, fontName=_FONT_BOLD, textColor=C_MED,
                              alignment=TA_RIGHT)
    s_gold  = ParagraphStyle("gld",   fontSize=12, fontName=_FONT_BOLD, textColor=C_GOLD_D)
    s_sub2  = ParagraphStyle("sub2",  fontSize=10, fontName=_FONT_REG,  textColor=C_MUTE)
    s_date  = ParagraphStyle("date",  fontSize=10, fontName=_FONT_REG,  textColor=C_MED, leading=15)
    s_ftit  = ParagraphStyle("ftit",  fontSize=8,  fontName=_FONT_BOLD, textColor=C_MUTE, spaceAfter=4)
    s_fnote = ParagraphStyle("fnote", fontSize=10, fontName=_FONT_REG,
                              textColor=colors.HexColor("#6b6055"), leading=16)
    s_pill  = ParagraphStyle("pill",  fontSize=8,  fontName=_FONT_BOLD,
                              textColor=colors.HexColor("#7a5c10"))
    s_av    = ParagraphStyle("av",    fontSize=14, fontName=_FONT_BOLD, textColor=C_GOLD,
                              alignment=TA_CENTER)

    initials = "".join(p[0].upper() for p in asistente["nombre"].split()[:2])
    maps_url = CONFIG.get("maps_url", "")

    # ── ENCABEZADO OSCURO ─────────────────────────────────────────
    hdr = Table([
        [Paragraph("ENTRADA  ·  2026", s_tag)],
        [Paragraph("CONFERENCIA VOZ QUE CLAMA", s_title)],
        [Paragraph('"La meta es Él"', s_sub)],
    ], colWidths=[W])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_HDR),
        ("LEFTPADDING",   (0,0), (-1,-1), 20),
        ("RIGHTPADDING",  (0,0), (-1,-1), 20),
        ("TOPPADDING",    (0,0), (0,0),   18),
        ("BOTTOMPADDING", (0,0), (0,0),    2),
        ("TOPPADDING",    (0,1), (0,1),    4),
        ("BOTTOMPADDING", (0,1), (0,1),    4),
        ("TOPPADDING",    (0,2), (0,2),    2),
        ("BOTTOMPADDING", (0,2), (0,2),   18),
    ]))

    # ── FILA DEL ASISTENTE ────────────────────────────────────────
    AV_SIZE = 1.15*cm
    APAD    = 10
    att_iW  = W - 2*APAD
    COL_AV  = AV_SIZE + 8
    COL_DNI = 3.5*cm
    COL_NOM = att_iW - COL_AV - COL_DNI

    av = Table([[Paragraph(initials, s_av)]], colWidths=[AV_SIZE], rowHeights=[AV_SIZE])
    av.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_DARK),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",   (0,0), (-1,-1), 0),
        ("RIGHTPADDING",  (0,0), (-1,-1), 0),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))

    att_row = Table([[
        av,
        [Paragraph("ASISTENTE", s_lbl), Paragraph(asistente["nombre"], s_name)],
        [Paragraph("DNI", s_lbl_r),     Paragraph(asistente["dni"], s_dni)],
    ]], colWidths=[COL_AV, COL_NOM, COL_DNI])
    att_row.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",   (0,0), (0,-1),   0),
        ("RIGHTPADDING",  (0,0), (0,-1),   8),
        ("LEFTPADDING",   (1,0), (1,-1),   0),
        ("RIGHTPADDING",  (1,0), (1,-1),   8),
        ("LEFTPADDING",   (2,0), (2,-1),   0),
        ("RIGHTPADDING",  (2,0), (2,-1),   0),
        ("TOPPADDING",    (0,0), (-1,-1),  0),
        ("BOTTOMPADDING", (0,0), (-1,-1),  0),
    ]))

    att_box = Table([[att_row]], colWidths=[W])
    att_box.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_CARD),
        ("BOX",           (0,0), (-1,-1), 0.5, C_BRDR),
        ("LEFTPADDING",   (0,0), (-1,-1), APAD),
        ("RIGHTPADDING",  (0,0), (-1,-1), APAD),
        ("TOPPADDING",    (0,0), (-1,-1), APAD),
        ("BOTTOMPADDING", (0,0), (-1,-1), APAD),
    ]))

    # ── TARJETAS DE INFO (LUGAR + FECHAS) ─────────────────────────
    CGAP = 0.2*cm
    CPAD = 10
    half = (W - CGAP) / 2

    lugar_link = (
        f'<a href="{maps_url}" color="#8a6010"><u>Salón "Yapire"</u></a>'
        if maps_url else 'Salón "Yapire"'
    )
    lugar_card = Table([
        [Paragraph("LUGAR", s_lbl)],
        [Paragraph(lugar_link, s_gold)],
        [Paragraph("Corrientes, Argentina", s_sub2)],
    ], colWidths=[half])
    lugar_card.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_CARD),
        ("BOX",           (0,0), (-1,-1), 0.5, C_BRDR),
        ("LEFTPADDING",   (0,0), (-1,-1), CPAD),
        ("RIGHTPADDING",  (0,0), (-1,-1), CPAD),
        ("TOPPADDING",    (0,0), (0,0),   CPAD),
        ("BOTTOMPADDING", (0,-1),(0,-1),  CPAD),
        ("TOPPADDING",    (0,1), (0,-1),   3),
        ("BOTTOMPADDING", (0,0), (0,-2),   1),
    ]))

    fechas_card = Table([
        [Paragraph("FECHAS", s_lbl)],
        [Paragraph("- <b>Vie 23</b> oct  ·  09:00 – 22:30 hs", s_date)],
        [Paragraph("- <b>Sáb 24</b> oct  ·  09:00 – 22:30 hs", s_date)],
    ], colWidths=[half])
    fechas_card.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_CARD),
        ("BOX",           (0,0), (-1,-1), 0.5, C_BRDR),
        ("LEFTPADDING",   (0,0), (-1,-1), CPAD),
        ("RIGHTPADDING",  (0,0), (-1,-1), CPAD),
        ("TOPPADDING",    (0,0), (0,0),   CPAD),
        ("BOTTOMPADDING", (0,-1),(0,-1),  CPAD),
        ("TOPPADDING",    (0,1), (0,-1),   4),
        ("BOTTOMPADDING", (0,0), (0,-2),   2),
    ]))

    grid = Table([[lugar_card, "", fechas_card]], colWidths=[half, CGAP, half])
    grid.setStyle(TableStyle([
        ("LEFTPADDING",   (0,0), (-1,-1), 0),
        ("RIGHTPADDING",  (0,0), (-1,-1), 0),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))

    # ── SEPARADOR PUNTEADO ────────────────────────────────────────
    sep = Table([["- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -"]], colWidths=[W])
    sep.setStyle(TableStyle([
        ("TEXTCOLOR",     (0,0), (-1,-1), C_DASH),
        ("FONTSIZE",      (0,0), (-1,-1), 7),
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))

    # ── PIE CON QR ────────────────────────────────────────────────
    FPAD     = 14
    QR_W     = 2.5*cm
    QR_GAP   = 10
    foot_iW  = W - 2*FPAD
    text_col = foot_iW - QR_W - QR_GAP

    qr_img = RLImage(qr_tmp_path, width=QR_W, height=QR_W)

    foot_inner = Table([[
        qr_img,
        [
            Paragraph("TU ENTRADA DIGITAL", s_ftit),
            Paragraph("Mostrá este código QR a la entrada.<br/>No hace falta imprimir.", s_fnote),
            Spacer(1, 4),
            Paragraph("* PERSONAL E INTRANSFERIBLE", s_pill),
        ],
    ]], colWidths=[QR_W + QR_GAP, text_col])
    foot_inner.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",   (0,0), (0,-1),   0),
        ("RIGHTPADDING",  (0,0), (0,-1),   QR_GAP),
        ("LEFTPADDING",   (1,0), (1,-1),   0),
        ("RIGHTPADDING",  (1,0), (1,-1),   0),
        ("TOPPADDING",    (0,0), (-1,-1),  0),
        ("BOTTOMPADDING", (0,0), (-1,-1),  0),
    ]))

    foot_tbl = Table([[foot_inner]], colWidths=[W])
    foot_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_FOOT),
        ("LEFTPADDING",   (0,0), (-1,-1), FPAD),
        ("RIGHTPADDING",  (0,0), (-1,-1), FPAD),
        ("TOPPADDING",    (0,0), (-1,-1), FPAD),
        ("BOTTOMPADDING", (0,0), (-1,-1), FPAD),
    ]))

    story = [
        hdr,
        Spacer(1, 14),
        att_box,
        Spacer(1, 0.3*cm),
        grid,
        Spacer(1, 14),
        sep,
        foot_tbl,
    ]

    doc.build(story)
    os.unlink(qr_tmp_path)
    return ruta_pdf


def enviar_email(asistente, ruta_pdf):
    """Envía el email con la entrada adjunta."""
    msg = MIMEMultipart("related")
    msg["From"] = CONFIG["gmail_usuario"]
    msg["To"] = asistente["email"]
    msg["Subject"] = f"🎟️ ENTRADA - CONFERENCIA VOZ QUE CLAMA 2026  'LA META ES ÉL' — {asistente['nombre']}"

    banner_html = ""
    if CONFIG.get("logo_path") and os.path.exists(CONFIG["logo_path"]):
        banner_html = (
            f"<div style=\"text-align:center; margin:0 auto 20px; max-width:600px;\">"
            f"<img src=\"cid:banner_img\" alt=\"CONFERENCIA VOZ QUE CLAMA 2026\" style=\"width:100%; height:auto; border-radius: 16px; display:block;\">"
            f"</div>"
        )

    cuerpo_html = f"""
    <html><body style="font-family: Arial, sans-serif; color: #333; max-width: 640px; margin: auto; background: #f0f2f5; padding: 20px;">
      <div style="background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 24px rgba(0,0,0,0.08);">

        {banner_html}

        <!-- CABECERA -->
        <div style="background: #050a14; padding: 28px 32px 24px;">
          <p style="margin: 0 0 6px; font-size: 11px; font-weight: 700; letter-spacing: 0.15em; color: #c9a84c; text-transform: uppercase;">Entrada · 2026</p>
          <h1 style="margin: 0 0 4px; font-size: 22px; font-weight: 700; color: #ffffff; letter-spacing: 0.04em; text-transform: uppercase;">Conferencia Voz que Clama</h1>
          <p style="margin: 0; font-size: 16px; color: #c9a84c; font-style: italic;">"La meta es Él"</p>
        </div>

        <!-- CUERPO -->
        <div style="padding: 28px 32px;">

          <p style="margin: 0 0 22px; font-size: 16px; color: #444;">Hola, <strong style="color: #0f172a;">{asistente['nombre'].split()[0]}</strong>. Tu entrada está lista.</p>

          <!-- BLOQUE TICKET -->
          <div style="background: #f9f7f4; border: 1px solid #ede8e0; border-radius: 12px; padding: 20px 22px; margin-bottom: 20px;">
            <table style="width: 100%; border-collapse: collapse;">
              <tr>
                <td style="padding: 6px 0; font-size: 11px; font-weight: 700; letter-spacing: 0.12em; color: #a89e8e; text-transform: uppercase; width: 38%;">Evento</td>
                <td style="padding: 6px 0; font-size: 14px; font-weight: 600; color: #0f172a;">CONFERENCIA VOZ QUE CLAMA 2026</td>
              </tr>
              <tr style="border-top: 1px solid #ede8e0;">
                <td style="padding: 6px 0; font-size: 11px; font-weight: 700; letter-spacing: 0.12em; color: #a89e8e; text-transform: uppercase;">Titular</td>
                <td style="padding: 6px 0; font-size: 14px; font-weight: 600; color: #0f172a;">{asistente['nombre']}</td>
              </tr>
            </table>
          </div>

          <p style="margin: 0 0 8px; font-size: 14px; color: #555;">Encontrás tu entrada en PDF adjunta a este correo. Presentá el código QR a la entrada del evento — no hace falta imprimir.</p>

          <p style="margin: 0 0 24px; font-size: 14px; color: #555;">¡Te esperamos en la Conferencia Voz Que Clama 2026!</p>

          <a href="{CONFIG.get('maps_url','')}" style="display: inline-block; text-decoration: none; background: #050a14; color: #c9a84c; padding: 12px 22px; border-radius: 8px; font-weight: 700; font-size: 13px; letter-spacing: 0.08em;">VER EN GOOGLE MAPS</a>

          <p style="margin: 24px 0 0; color: #aaa; font-size: 12px; border-top: 1px solid #ede8e0; padding-top: 16px;">Esta entrada es personal e intransferible.</p>
        </div>

      </div>
    </body></html>
    """

    msg.attach(MIMEText(cuerpo_html, "html"))

    if CONFIG.get("logo_path") and os.path.exists(CONFIG["logo_path"]):
        with open(CONFIG["logo_path"], "rb") as img_file:
            img = MIMEImage(img_file.read())
            img.add_header("Content-ID", "<banner_img>")
            img.add_header("Content-Disposition", "inline", filename=os.path.basename(CONFIG["logo_path"]))
            msg.attach(img)

    # Adjuntar PDF
    with open(ruta_pdf, "rb") as f:
        adjunto = MIMEBase("application", "octet-stream")
        adjunto.set_payload(f.read())
    encoders.encode_base64(adjunto)
    adjunto.add_header("Content-Disposition", f"attachment; filename={os.path.basename(ruta_pdf)}")
    msg.attach(adjunto)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as servidor:
        servidor.login(CONFIG["gmail_usuario"], CONFIG["gmail_password"])
        servidor.sendmail(CONFIG["gmail_usuario"], asistente["email"], msg.as_string())


def generar_link_whatsapp(asistente, ruta_pdf):
    """Genera el link de WhatsApp con el mensaje pre-armado."""
    numero = asistente["celular"].replace("+", "").replace(" ", "").replace("-", "")
    # Si el número empieza con 0, reemplazar por código de Argentina
    if numero.startswith("0"):
        numero = "54" + numero[1:]
    # Si no tiene código de país, agregar Argentina
    if not numero.startswith("54") and len(numero) <= 10:
        numero = "54" + numero

    mensaje = (
        f"¡Hola {asistente['nombre'].split()[0]}! 👋\n"
        f"Te enviamos tu entrada para *{CONFIG['nombre_evento']}*.\n\n"
        f"📅 *Fecha:* {CONFIG['fecha_evento']}\n"
        f"📍 *Lugar:* {CONFIG['lugar_evento']}\n"
        f"¡Te esperamos! 🎉"
    )
    link = f"https://wa.me/{numero}?text={urllib.parse.quote(mensaje)}"
    return link


def procesar_asistentes(solo_email=True, abrir_whatsapp=False):
    """
    Procesa todos los asistentes del Excel.
    solo_email=True  → envía emails automáticamente
    abrir_whatsapp=True → abre los links de WA en el navegador (uno por uno)
    """
    crear_carpeta_salida()
    asistentes = leer_excel()

    # Guardar links de WhatsApp en un archivo para usar después
    links_wa_path = os.path.join(CONFIG["carpeta_salida"], "links_whatsapp.txt")

    errores = []

    with open(links_wa_path, "w", encoding="utf-8") as f_wa:
        f_wa.write(f"LINKS DE WHATSAPP — {CONFIG['nombre_evento']}\n")
        f_wa.write("=" * 60 + "\n\n")

        for i, asistente in enumerate(asistentes, 1):
            if CONFIG.get("test_email"):
                if asistente["email"].strip().lower() != CONFIG["test_email"].strip().lower():
                    print(f"  ⏭ Omitiendo {asistente['nombre']} ({asistente['email']}) porque test_email está activo.")
                    continue
            print(f"\n[{i}/{len(asistentes)}] Procesando: {asistente['nombre']}...")

            try:
                # 1. Generar entrada PDF
                print(f"  📄 Generando PDF...")
                ruta_pdf = generar_entrada_pdf(asistente)
                print(f"  ✅ PDF guardado: {ruta_pdf}")

                # 2. Enviar email
                if asistente["email"] and "@" in asistente["email"]:
                    try:
                        print(f"  📧 Enviando email a {asistente['email']}...")
                        enviar_email(asistente, ruta_pdf)
                        print(f"  ✅ Email enviado")
                    except Exception as e:
                        print(f"  ⚠️  Error email: {e}")
                        errores.append(f"{asistente['nombre']}: email falló — {e}")
                else:
                    print(f"  ⚠️  Sin email válido, omitiendo envío")

                # 3. Generar link WhatsApp
                link_wa = generar_link_whatsapp(asistente, ruta_pdf)
                f_wa.write(f"#{asistente['id']:03d} — {asistente['nombre']}\n")
                f_wa.write(f"  Celular: {asistente['celular']}\n")
                f_wa.write(f"  Link: {link_wa}\n\n")

                if abrir_whatsapp:
                    input(f"  Presioná ENTER para abrir WhatsApp de {asistente['nombre'].split()[0]}...")
                    webbrowser.open(link_wa)

            except Exception as e:
                print(f"  ❌ Error general: {e}")
                errores.append(f"{asistente['nombre']}: {e}")

    print("\n" + "="*50)
    print(f"✅ Proceso completado.")
    print(f"📁 Entradas guardadas en: {CONFIG['carpeta_salida']}/")
    print(f"📱 Links de WhatsApp guardados en: {links_wa_path}")
    if errores:
        print(f"\n⚠️  Errores encontrados ({len(errores)}):")
        for e in errores:
            print(f"   - {e}")


# ============================================================
#  PUNTO DE ENTRADA
# ============================================================
if __name__ == "__main__":
    print("=" * 50)
    print(f"  GENERADOR DE ENTRADAS — {CONFIG['nombre_evento']}")
    print("=" * 50)
    print()
    print("¿Qué querés hacer?")
    print("  1. Generar PDFs + Enviar emails (sin WhatsApp)")
    print("  2. Generar PDFs + Enviar emails + Abrir WhatsApp uno por uno")
    print("  3. Solo generar PDFs (sin enviar nada)")
    print()
    opcion = input("Opción (1/2/3): ").strip()

    if opcion == "1":
        procesar_asistentes(solo_email=True, abrir_whatsapp=False)
    elif opcion == "2":
        procesar_asistentes(solo_email=True, abrir_whatsapp=True)
    elif opcion == "3":
        procesar_asistentes(solo_email=False, abrir_whatsapp=False)
    else:
        print("Opción no válida. Ejecutá de nuevo.")
