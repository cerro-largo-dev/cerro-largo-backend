import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from src.models.reporte import db, Reporte, FotoReporte
from email import encoders
from datetime import datetime
import logging

class EmailService:
    def __init__(self):
        # Configuración de Gmail SMTP
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.email_usuario = os.environ.get('EMAIL_USER', 'cerrolargogobierno@gmail.com')
        self.email_password = os.environ.get('EMAIL_PASSWORD', '')
        self.email_destino = 'gobcerrolargo@gmail.com'
        
    def enviar_reporte_ciudadano(self, reporte_data, fotos_paths=None):
        """
        Envía un reporte ciudadano por correo electrónico
        
        Args:
            reporte_data (dict): Datos del reporte
            fotos_paths (list): Lista de rutas de archivos de fotos
        """
        try:
            # Crear mensaje
            msg = MIMEMultipart()
            msg['From'] = self.email_usuario
            msg['To'] = self.email_destino
            msg['Subject'] = f"Nuevo Reporte Ciudadano - {reporte_data.get('nombre_lugar', 'Sin ubicación específica')}"
            
            # Crear cuerpo del mensaje
            cuerpo = self._crear_cuerpo_email(reporte_data)
            msg.attach(MIMEText(cuerpo, 'html', 'utf-8'))
            
            # Adjuntar fotos si existen
            if fotos_paths:
                for foto_path in fotos_paths:
                    if os.path.exists(foto_path):
                        self._adjuntar_archivo(msg, foto_path)
            
            # Enviar email
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            
            # Usar contraseña de aplicación si está disponible
            if self.email_password:
                server.login(self.email_usuario, self.email_password)
                text = msg.as_string()
                server.sendmail(self.email_usuario, self.email_destino, text)
                server.quit()
                
                logging.info(f"Reporte enviado exitosamente a {self.email_destino}")
                return True
            else:
                logging.warning("No se configuró contraseña de email. Reporte no enviado.")
                return False
                
        except Exception as e:
            logging.error(f"Error al enviar reporte por email: {str(e)}")
            return False
    
    def _crear_cuerpo_email(self, reporte_data):
        """Crea el cuerpo HTML del email"""
        fecha_formateada = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        
        # Formatear coordenadas si existen
        ubicacion_info = ""
        if reporte_data.get('latitud') and reporte_data.get('longitud'):
            lat = reporte_data['latitud']
            lng = reporte_data['longitud']
            ubicacion_info = f"""
            <p><strong>📍 Coordenadas:</strong></p>
            <ul>
                <li>Latitud: {lat}</li>
                <li>Longitud: {lng}</li>
                <li><a href="https://www.google.com/maps?q={lat},{lng}" target="_blank">Ver en Google Maps</a></li>
            </ul>
            """
        
        nombre_lugar = reporte_data.get('nombre_lugar', 'No especificado')
        descripcion = reporte_data.get('descripcion', 'Sin descripción')
        
        cuerpo = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .header {{ background-color: #2563eb; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                .info-box {{ background-color: #f8f9fa; border-left: 4px solid #2563eb; padding: 15px; margin: 10px 0; }}
                .footer {{ background-color: #f1f5f9; padding: 15px; text-align: center; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Nuevo Reporte Ciudadano</h1>
                <p>Sistema de Reportes - Cerro Largo</p>
            </div>
            
            <div class="content">
                <div class="info-box">
                    <h3>📋 Información del Reporte</h3>
                    <p><strong>📅 Fecha y Hora:</strong> {fecha_formateada}</p>
                    <p><strong>📍 Lugar:</strong> {nombre_lugar}</p>
                    <p><strong>📝 Descripción:</strong></p>
                    <p style="background-color: white; padding: 10px; border-radius: 5px; border: 1px solid #ddd;">
                        {descripcion}
                    </p>
                </div>
                
                {ubicacion_info}
                
                <div class="info-box">
                    <h3>📸 Fotos Adjuntas</h3>
                    <p>Las fotos del reporte se encuentran adjuntas a este correo (si las hay).</p>
                </div>
                
                <div class="info-box">
                    <h3> Acciones Recomendadas</h3>
                    <ul>
                        <li>Revisar la descripción del problema reportado</li>
                        <li>Verificar la ubicación en el mapa</li>
                        <li>Evaluar la prioridad del reporte</li>
                        <li>Asignar personal para inspección si es necesario</li>
                    </ul>
                </div>
            </div>
            
            <div class="footer">
                <p>Este es un mensaje automático del Sistema de Reportes Ciudadanos de Cerro Largo.</p>
                <p>Para más información, contacte al administrador del sistema.</p>
            </div>
        </body>
        </html>
        """
        
        return cuerpo
    
    def _adjuntar_archivo(self, msg, archivo_path):
        """Adjunta un archivo al mensaje de email"""
        try:
            with open(archivo_path, "rb") as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
            
            encoders.encode_base64(part)
            
            filename = os.path.basename(archivo_path)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {filename}',
            )
            
            msg.attach(part)
            
        except Exception as e:
            logging.error(f"Error al adjuntar archivo {archivo_path}: {str(e)}")

