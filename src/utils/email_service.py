# email_service.py
# Servicio de email (Gmail SMTP) con adjuntos y resolución robusta de rutas.
# Requiere variables de entorno:
#   EMAIL_USER, EMAIL_PASSWORD
# Opcionales:
#   EMAIL_DEFAULT_TO (para pruebas), STATIC_UPLOAD_REPORTES_DIR (ruta absoluta a /static/uploads/reportes)

import os
import smtplib
import logging
import mimetypes
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.utils import formatdate, make_msgid
from email import encoders

# Intentamos importar current_app de Flask, pero sólo si está disponible
try:
    from flask import current_app
except Exception:  # Flask no necesariamente instalado en todos los entornos
    current_app = None  # type: ignore

logging.basicConfig(level=logging.INFO)

class EmailService:
    def __init__(self):
        # Configuración SMTP (Gmail)
        self.smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        self.email_usuario = os.environ.get("EMAIL_USER", "")
        self.email_password = os.environ.get("EMAIL_PASSWORD", "")

        # Destinatario por defecto (útil en staging)
        self.default_to = os.environ.get("EMAIL_DEFAULT_TO", "")

        if not self.email_usuario:
            logging.warning("EMAIL_USER no está configurado.")
        if not self.email_password:
            logging.warning("EMAIL_PASSWORD no está configurado (no se podrá autenticar).")

    # ---------- API pública ----------

    def enviar_reporte_ciudadano(self, datos: dict, fotos_paths: list | None = None,
                                 destinatarios: list | None = None,
                                 cc: list | None = None, bcc: list | None = None,
                                 reply_to: str | None = None) -> bool:
        """
        Envía un correo con la información del reporte ciudadano y adjunta fotos si existen.
        - datos: dict con claves sugeridas: descripcion, nombre_lugar, latitud, longitud, fecha_creacion (ISO)
        - fotos_paths: lista de rutas (URLs o relativas/absolutas). Se resolverán a rutas de filesystem.
        - destinatarios: lista de emails. Si None, usa EMAIL_DEFAULT_TO si existe.
        """

        to_list = destinatarios or ([self.default_to] if self.default_to else None)
        if not to_list:
            logging.error("Sin destinatarios: define destinatarios o EMAIL_DEFAULT_TO.")
            return False

        asunto = self._armar_asunto(datos)
        cuerpo_html, cuerpo_txt = self._armar_cuerpo(datos)

        msg = self._crear_mensaje_base(
            remitente=self.email_usuario,
            destinatarios=to_list,
            asunto=asunto,
            cuerpo_html=cuerpo_html,
            cuerpo_texto=cuerpo_txt,
            cc=cc,
            bcc=bcc,
            reply_to=reply_to
        )

        # Adjuntar fotos si existen (resolviendo rutas)
        adjuntos_ok = 0
        for p in (fotos_paths or []):
            ruta_fs = self._resolver_ruta_archivo(p)
            if ruta_fs and os.path.isfile(ruta_fs):
                if self._adjuntar_archivo(msg, ruta_fs):
                    adjuntos_ok += 1
            else:
                logging.warning(f"No existe adjunto en filesystem: {p} -> {ruta_fs}")

        logging.info(f"Adjuntos agregados: {adjuntos_ok}")

        # Envío SMTP
        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                if not self.email_password:
                    logging.error("EMAIL_PASSWORD vacío: no se puede autenticar en SMTP.")
                    return False

                server.login(self.email_usuario, self.email_password)
                server.send_message(msg)
                logging.info(f"Email enviado a: {to_list}")
                return True

        except Exception as e:
            logging.error(f"Error enviando email: {e}")
            return False

    # ---------- Helpers de composición ----------

    def _armar_asunto(self, datos: dict) -> str:
        lugar = (datos or {}).get("nombre_lugar") or "Reporte ciudadano"
        fecha = (datos or {}).get("fecha_creacion")
        if not fecha:
            fecha = datetime.utcnow().isoformat(timespec="seconds")
        return f"[Reporte ciudadano] {lugar} — {fecha}"

    def _armar_cuerpo(self, datos: dict) -> tuple[str, str]:
        descripcion = (datos or {}).get("descripcion") or "-"
        lugar = (datos or {}).get("nombre_lugar") or "-"
        lat = (datos or {}).get("latitud")
        lon = (datos or {}).get("longitud")
        fecha = (datos or {}).get("fecha_creacion") or datetime.utcnow().isoformat(timespec="seconds")

        coords = f"{lat}, {lon}" if (lat is not None and lon is not None) else "-"

        html = f"""
        <html>
          <body>
            <h2>Nuevo reporte ciudadano</h2>
            <table border="1" cellpadding="6" cellspacing="0">
              <tr><th align="left">Lugar</th><td>{self._esc(lugar)}</td></tr>
              <tr><th align="left">Descripción</th><td>{self._esc(descripcion)}</td></tr>
              <tr><th align="left">Coordenadas</th><td>{self._esc(coords)}</td></tr>
              <tr><th align="left">Fecha</th><td>{self._esc(fecha)}</td></tr>
            </table>
            <p>Se adjuntan imágenes cuando corresponda.</p>
          </body>
        </html>
        """.strip()

        txt = (
            "Nuevo reporte ciudadano\n"
            f"- Lugar: {lugar}\n"
            f"- Descripción: {descripcion}\n"
            f"- Coordenadas: {coords}\n"
            f"- Fecha: {fecha}\n"
            "Se adjuntan imágenes cuando corresponda."
        )
        return html, txt

    def _crear_mensaje_base(self, remitente: str, destinatarios: list,
                            asunto: str, cuerpo_html: str, cuerpo_texto: str,
                            cc: list | None = None, bcc: list | None = None,
                            reply_to: str | None = None) -> MIMEMultipart:
        msg = MIMEMultipart("mixed")
        msg["From"] = remitente
        msg["To"] = ", ".join(destinatarios)
        if cc:
            msg["Cc"] = ", ".join(cc)
        # BCC no se pone en cabeceras visibles
        msg["Subject"] = asunto
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()
        if reply_to:
            msg["Reply-To"] = reply_to

        # Parte alternativa (texto + HTML)
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(cuerpo_texto, "plain", "utf-8"))
        alt.attach(MIMEText(cuerpo_html, "html", "utf-8"))
        msg.attach(alt)

        # Para send_message() con BCC
        all_rcpts = destinatarios + (cc or []) + (bcc or [])
        msg["X-Recipients-Internal"] = ";".join(all_rcpts)  # sólo informativo/logs

        return msg

    # ---------- Helpers de adjuntos/rutas ----------

    def _resolver_ruta_archivo(self, path: str | os.PathLike | None) -> str | None:
        """
        Recibe rutas tipo:
          - absoluta en filesystem (/var/.../file.jpg)
          - relativa (uploads/reportes/file.jpg)
          - URL o ruta web (/static/uploads/reportes/file.jpg)
        Intenta normalizarlas al filesystem real y devuelve una ruta existente o None.
        """
        if not path:
            return None

        path_str = str(path)

        # 1) Si ya es una ruta absoluta existente, devuélvela.
        if os.path.isabs(path_str) and os.path.isfile(path_str):
            return path_str

        # 2) Si es una ruta 'web' bajo /static/uploads/reportes, intentamos mapear a FS.
        candidatos = []

        # a) Variable de entorno preferida
        base_env = os.environ.get("STATIC_UPLOAD_REPORTES_DIR")  # e.g., /app/static/uploads/reportes
        if base_env:
            candidatos.append(os.path.join(base_env, os.path.basename(path_str)))

        # b) Flask current_app si existe
        if current_app and current_app.static_folder:
            candidatos.append(os.path.join(current_app.static_folder, "uploads", "reportes", os.path.basename(path_str)))
            # También por si ya viene 'uploads/reportes/archivo.jpg'
            if "uploads/reportes" in path_str:
                tail = path_str.split("uploads/reportes")[-1].lstrip("/\\")
                candidatos.append(os.path.join(current_app.static_folder, "uploads", "reportes", tail))

        # c) Heurística con cwd
        cwd_base = os.path.join(os.getcwd(), "static", "uploads", "reportes")
        candidatos.append(os.path.join(cwd_base, os.path.basename(path_str)))
        if "uploads/reportes" in path_str:
            tail = path_str.split("uploads/reportes")[-1].lstrip("/\\")
            candidatos.append(os.path.join(cwd_base, tail))

        # d) Si la ruta vino como '/static/uploads/reportes/archivo.jpg'
        if path_str.startswith("/static/uploads/reportes/"):
            candidatos.append(os.path.join(cwd_base, os.path.basename(path_str)))

        # 3) Si es relativa, probamos relativa al cwd
        if not os.path.isabs(path_str):
            candidatos.append(os.path.abspath(path_str))

        # Devolvemos el primer candidato que exista
        for c in candidatos:
            if os.path.isfile(c):
                return c

        return None

    def _adjuntar_archivo(self, msg: MIMEMultipart, archivo_path: str) -> bool:
        try:
            ctype, encoding = mimetypes.guess_type(archivo_path)
            if ctype is None or encoding is not None:
                ctype = "application/octet-stream"
            maintype, subtype = ctype.split("/", 1)

            with open(archivo_path, "rb") as f:
                part = MIMEBase(maintype, subtype)
                part.set_payload(f.read())

            encoders.encode_base64(part)
            filename = os.path.basename(archivo_path)
            part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(part)
            return True

        except Exception as e:
            logging.error(f"Error al adjuntar archivo {archivo_path}: {e}")
            return False

    # ---------- Util ----------

    @staticmethod
    def _esc(s: str) -> str:
        if s is None:
            return ""
        # Escape mínimo para HTML
        return (
            str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
