# email_service.py  (drop-in)
import smtplib, os, logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

logging.basicConfig(level=logging.INFO)

try:
    from flask import current_app
except Exception:
    current_app = None  # opcional

class EmailService:
    def __init__(self):
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.email_usuario = os.environ.get("EMAIL_USER", "cerrolargogobierno@gmail.com")
        self.email_password = os.environ.get("EMAIL_PASSWORD", "")
        self.email_destino = os.environ.get("EMAIL_DEFAULT_TO", "gobcerrolargo@gmail.com")

    def enviar_reporte_ciudadano(self, reporte_data, fotos_paths=None):
        try:
            msg = MIMEMultipart()
            msg["From"] = self.email_usuario
            msg["To"] = self.email_destino
            msg["Subject"] = f"Nuevo Reporte Ciudadano - {reporte_data.get('nombre_lugar','Sin ubicación específica')}"

            cuerpo = self._crear_cuerpo_email(reporte_data)
            msg.attach(MIMEText(cuerpo, "html", "utf-8"))

            # Resolver y adjuntar fotos SIN cambiar lo guardado en DB
            adj_ok = 0
            for original in (fotos_paths or []):
                ruta_fs = self._resolver_ruta_archivo(original)
                if ruta_fs and os.path.isfile(ruta_fs):
                    if self._adjuntar_archivo(msg, ruta_fs):
                        adj_ok += 1
                else:
                    logging.warning(f"No existe adjunto: {original} -> {ruta_fs}")
            logging.info(f"Adjuntos agregados: {adj_ok}")

            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30)
            server.starttls()
            if not self.email_password:
                logging.warning("EMAIL_PASSWORD no configurado. Reporte no enviado.")
                return False
            server.login(self.email_usuario, self.email_password)
            server.sendmail(self.email_usuario, [self.email_destino], msg.as_string())
            server.quit()
            logging.info(f"Reporte enviado a {self.email_destino}")
            return True

        except Exception as e:
            logging.error(f"Error al enviar reporte por email: {e}")
            return False

    def _crear_cuerpo_email(self, data):
        fecha = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        lat, lng = data.get("latitud"), data.get("longitud")
        ubic = (
            f"""<p><strong>📍 Coordenadas:</strong></p>
<ul><li>Latitud: {lat}</li><li>Longitud: {lng}</li>
<li><a href="https://www.google.com/maps?q={lat},{lng}" target="_blank">Ver en Google Maps</a></li></ul>"""
            if lat is not None and lng is not None else ""
        )
        lugar = data.get("nombre_lugar", "No especificado")
        desc = data.get("descripcion", "Sin descripción")
        return f"""<!DOCTYPE html><html><body>
<h2>🏛️ Nuevo Reporte Ciudadano</h2>
<p><strong>📅 Fecha y Hora:</strong> {fecha}</p>
<p><strong>📍 Lugar:</strong> {lugar}</p>
<p><strong>📝 Descripción:</strong></p>
<div style="border:1px solid #ddd;padding:10px;border-radius:6px">{desc}</div>
{ubic}
<p>Las fotos del reporte se adjuntan si existen.</p>
</body></html>"""

    def _resolver_ruta_archivo(self, path):
        """Mapea rutas web/relativas a filesystem real; NO altera lo guardado en DB."""
        if not path:
            return None
        s = str(path)

        # Si ya es absoluta y existe
        if os.path.isabs(s) and os.path.isfile(s):
            return s

        candidatos = []

        # 1) Variable de entorno opcional (ruta absoluta a .../static/uploads/reportes)
        base_env = os.environ.get("STATIC_UPLOAD_REPORTES_DIR")
        if base_env:
            candidatos.append(os.path.join(base_env, os.path.basename(s)))

        # 2) Flask static_folder (si hay app)
        if current_app and getattr(current_app, "static_folder", None):
            static_base = os.path.join(current_app.static_folder, "uploads", "reportes")
            candidatos.append(os.path.join(static_base, os.path.basename(s)))
            if "uploads/reportes" in s:
                tail = s.split("uploads/reportes")[-1].lstrip("/\\")
                candidatos.append(os.path.join(static_base, tail))

        # 3) Heurística con CWD
        cwd_base = os.path.join(os.getcwd(), "static", "uploads", "reportes")
        candidatos.append(os.path.join(cwd_base, os.path.basename(s)))
        if "uploads/reportes" in s:
            tail = s.split("uploads/reportes")[-1].lstrip("/\\")
            candidatos.append(os.path.join(cwd_base, tail))

        # 4) Si vino como /static/uploads/reportes/...
        if s.startswith("/static/uploads/reportes/"):
            candidatos.append(os.path.join(cwd_base, os.path.basename(s)))

        # 5) Relativa -> absoluta
        if not os.path.isabs(s):
            candidatos.append(os.path.abspath(s))

        for c in candidatos:
            if os.path.isfile(c):
                return c
        return None

    def _adjuntar_archivo(self, msg, archivo_path):
        try:
            with open(archivo_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(archivo_path)}"')
            msg.attach(part)
            return True
        except Exception as e:
            logging.error(f"Error al adjuntar {archivo_path}: {e}")
            return False
