# email_service.py
# Servicio SMTP (Gmail) con adjuntos y resolución robusta de rutas.
# Requiere variables de entorno:
#   EMAIL_USER, EMAIL_PASSWORD
# Opcionales:
#   EMAIL_DEFAULT_TO, STATIC_UPLOAD_REPORTES_DIR  (ruta absoluta a /static/uploads/reportes)
#
# Notas:
# - fotos_paths puede venir con valores tipo:
#     ['/static/uploads/reportes/abc.jpg', 'uploads/reportes/xyz.png', '/var/app/.../file.jpg']
#   Este servicio intentará resolver esos strings al filesystem real.

import os
import smtplib
import logging
import mimetypes
from datetime import datetime
from email import encoders
from email.utils import formatdate, make_msgid
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart

# current_app es útil para mapear la carpeta /static
try:
    from flask import current_app
except Exception:
    current_app = None  # type: ignore

logging.basicConfig(level=logging.INFO)

class EmailService:
    def __init__(self):
        # Configuración de Gmail
        self.smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        self.email_usuario = os.environ.get("EMAIL_USER", "cerrolargogobierno@gmail.com")
        self.email_password = os.environ.get("EMAIL_PASSWORD", "")
        # Destino por defecto (puedes cambiarlo por env EMAIL_DEFAULT_TO)
        self.email_destino = os.environ.get("EMAIL_DEFAULT_TO", "gobcerrolargo@gmail.com")

        if not self.email_usuario:
            logging.warning("EMAIL_USER no está definido.")
        if not self.email_password:
            logging.warning("EMAIL_PASSWORD no está definido (no se podrá autenticar en SMTP).")

    # ---------------------------------------------------------------------
    # API pública
    # ---------------------------------------------------------------------
    def enviar_reporte_ciudadano(self, reporte_data: dict, fotos_paths: list | None = None) -> bool:
        """
        Envía un correo con datos del reporte y adjunta imágenes si existen en el filesystem.
        """
        if not self.email_destino:
            logging.error("Sin destinatario: define EMAIL_DEFAULT_TO o ajusta self.email_destino.")
            return False

        # Composición del mensaje
        asunto = self._armar_asunto(reporte_data)
        html, txt = self._armar_cuerpo(reporte_data)
        msg = self._crear_mensaje_base(
            remitente=self.email_usuario,
            destinatarios=[self.email_destino],
            asunto=asunto,
            cuerpo_html=html,
            cuerpo_texto=txt,
        )

        # Adjuntos: resolvemos cada ruta potencial a una ruta real de FS
        adjuntos_ok = 0
        for original in (fotos_paths or []):
            ruta_fs = self._resolver_ruta_archivo(original)
            if ruta_fs and os.path.isfile(ruta_fs):
                if self._adjuntar_archivo(msg, ruta_fs):
                    adjuntos_ok += 1
            else:
                logging.warning(f"No existe adjunto en filesystem: {original} -> {ruta_fs}")
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
                server.send_message(
                    msg,
                    from_addr=self.email_usuario,
                    to_addrs=[self.email_destino],
                )
                logging.info(f"Email enviado a: {self.email_destino}")
                return True

        except Exception as e:
            logging.error(f"Error enviando email: {e}")
            return False

    # ---------------------------------------------------------------------
    # Composición
    # ---------------------------------------------------------------------
    def _armar_asunto(self, datos: dict) -> str:
        lugar = (datos or {}).get("nombre_lugar") or "Reporte ciudadano"
        fecha = (datos or {}).get("fecha_creacion") or datetime.utcnow().isoformat(timespec="seconds")
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
          <body style="font-family: Arial, sans-serif; line-height:1.5; color:#333;">
            <h2 style="margin-bottom:8px;">Nuevo reporte ciudadano</h2>
            <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
              <tr><th align="left">Lugar</th><td>{self._esc(lugar)}</td></tr>
              <tr><th align="left">Descripción</th><td>{self._esc(descripcion)}</td></tr>
              <tr><th align="left">Coordenadas</th><td>{self._esc(coords)}</td></tr>
              <tr><th align="left">Fecha</th><td>{self._esc(fecha)}</td></tr>
            </table>
            <p style="margin-top:10px;">Se adjuntan imágenes cuando corresponda.</p>
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

    def _crear_mensaje_base(self, remitente: str, destinatarios: list, asunto: str,
                            cuerpo_html: str, cuerpo_texto: str) -> MIMEMultipart:
        msg = MIMEMultipart("mixed")
        msg["From"] = remitente
        msg["To"] = ", ".join(destinatarios)
        msg["Subject"] = asunto
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()

        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(cuerpo_texto, "plain", "utf-8"))
        alt.attach(MIMEText(cuerpo_html, "html", "utf-8"))
        msg.attach(alt)
        return msg

    # ---------------------------------------------------------------------
    # Adjuntos y resolución de rutas
    # ---------------------------------------------------------------------
    def _resolver_ruta_archivo(self, path: str | os.PathLike | None) -> str | None:
        """
        Acepta:
          - absoluta (/var/.../file.jpg)
          - relativa (uploads/reportes/file.jpg)
          - web (/static/uploads/reportes/file.jpg)
        Devuelve ruta de filesystem existente o None.
        """
        if not path:
            return None
        path_str = str(path)

        # 1) Si ya es absoluta y existe
        if os.path.isabs(path_str) and os.path.isfile(path_str):
            return path_str

        candidatos: list[str] = []

        # 2) Variable de entorno preferida (si la configuras)
        base_env = os.environ.get("STATIC_UPLOAD_REPORTES_DIR")  # ej: /app/static/uploads/reportes
        if base_env:
            candidatos.append(os.path.join(base_env, os.path.basename(path_str)))

        # 3) Flask static_folder si existe
        if current_app and getattr(current_app, "static_folder", None):
            static_base = os.path.join(current_app.static_folder, "uploads", "reportes")
            candidatos.append(os.path.join(static_base, os.path.basename(path_str)))
            if "uploads/reportes" in path_str:
                tail = path_str.split("uploads/reportes")[-1].lstrip("/\\")
                candidatos.append(os.path.join(static_base, tail))

        # 4) CWD heurístico
        cwd_base = os.path.join(os.getcwd(), "static", "uploads", "reportes")
        candidatos.append(os.path.join(cwd_base, os.path.basename(path_str)))
        if "uploads/reportes" in path_str:
            tail = path_str.split("uploads/reportes")[-1].lstrip("/\\")
            candidatos.append(os.path.join(cwd_base, tail))

        # 5) Si vino como /static/uploads/reportes/...
        if path_str.startswith("/static/uploads/reportes/"):
            candidatos.append(os.path.join(cwd_base, os.path.basename(path_str)))

        # 6) Relativa → absoluta directa
        if not os.path.isabs(path_str):
            candidatos.append(os.path.abspath(path_str))

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

    # ---------------------------------------------------------------------
    @staticmethod
    def _esc(s: str) -> str:
        if s is None:
            return ""
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# Ejemplo mínimo de prueba local (opcional)
if __name__ == "__main__":
    svc = EmailService()
    data = {
        "descripcion": "Bache profundo",
        "nombre_lugar": "18 de Julio y Treinta y Tres",
        "latitud": -32.369,
        "longitud": -54.170,
        "fecha_creacion": datetime.utcnow().isoformat(timespec="seconds"),
    }
    ok = svc.enviar_reporte_ciudadano(data, fotos_paths=[
        "/static/uploads/reportes/ejemplo.jpg",  # el resolver intentará mapearla al FS
    ])
    print("OK:", ok)
