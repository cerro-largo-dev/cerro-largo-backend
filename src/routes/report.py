from flask import Blueprint, request, jsonify, send_file, session
from src.models.zone_state import ZoneState
from datetime import datetime
import os
import tempfile
import json

# Importar el generador de PDF
try:
    from src.pdf_generator import ReporteEstadoMunicipios
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print("Warning: PDF generator not available. Install reportlab to enable PDF reports.")

report_bp = Blueprint('report', __name__)

def require_admin_auth(f):
    """Decorador para requerir autenticación de administrador"""
    def decorated_function(*args, **kwargs):
        if not session.get('admin_authenticated', False):
            return jsonify({
                'success': False,
                'message': 'Acceso no autorizado'
            }), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@report_bp.route('/download', methods=['GET'])
def download_report():
    """Generar y descargar reporte de estados de zonas en PDF - disponible para todos los usuarios"""
    try:
        # Obtener todos los estados de las zonas
        states = ZoneState.get_all_states()
        
        # Si no hay estados, crear datos por defecto para los municipios
        if not states:
            municipios = [
                'ACEGUÁ', 'ARBOLITO', 'BAÑADO DE MEDINA', 'CERRO DE LAS CUENTAS',
                'FRAILE MUERTO', 'ISIDORO NOBLÍA', 'LAGO MERÍN', 'LAS CAÑAS',
                'MELO', 'PLÁCIDO ROSAS', 'RÍO BRANCO', 'TOLEDO', 'TUPAMBAÉ',
                'ARÉVALO', 'NOBLÍA', 'Melo (GBB)'
            ]
            
            for municipio in municipios:
                ZoneState.update_zone_state(municipio, 'green', 'sistema')
            
            states = ZoneState.get_all_states()
        
        # Si el generador de PDF está disponible, generar PDF
        if PDF_AVAILABLE:
            # Convertir estados a formato para el PDF
            municipios = []
            for zone_name, zone_data in states.items():
                state = zone_data.get('state', 'green')
                
                # Mapear estados a formato legible
                estado_map = {
                    'green': 'Habilitado',
                    'yellow': 'Precaución', 
                    'red': 'Suspendido'
                }
                
                color_map = {
                    'green': 'Verde',
                    'yellow': 'Amarillo',
                    'red': 'Rojo'
                }
                
                alerta_map = {
                    'green': 'Sin restricciones',
                    'yellow': 'Posible cierre de caminería',
                    'red': 'Prohibido el tránsito pesado por lluvias'
                }
                
                municipios.append({
                    'nombre': zone_name,
                    'estado': estado_map.get(state, 'Sin estado'),
                    'color': color_map.get(state, 'Sin color'),
                    'alerta': alerta_map.get(state, 'Sin información')
                })
            
            # Crear generador de PDF con logo
            logo_path = os.path.join(os.path.dirname(__file__), '..', 'alexlogo.png')
            generador = ReporteEstadoMunicipios(logo_path=logo_path)
            
            # Crear archivo temporal para el PDF
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                archivo_pdf = generador.generar_pdf(tmp_file.name, municipios)
                
                # Enviar el archivo PDF como respuesta
                return send_file(
                    archivo_pdf,
                    as_attachment=True,
                    download_name=f'reporte_camineria_cerro_largo_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf',
                    mimetype='application/pdf'
                )
        
        # Si no hay PDF disponible, generar reporte en texto
        else:
            return download_text_report(states)
        
    except Exception as e:
        print(f"Error generating PDF report: {str(e)}")
        # En caso de error con PDF, generar reporte en texto
        try:
            states = ZoneState.get_all_states()
            return download_text_report(states)
        except Exception as text_error:
            return jsonify({
                'success': False,
                'message': f'Error generando reporte: {str(text_error)}'
            }), 500

def download_text_report(states):
    """Generar reporte en formato texto como fallback"""
    # Crear archivo temporal
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='w', encoding='utf-8')
    
    # Escribir contenido del reporte
    now = datetime.now()
    temp_file.write("REPORTE DE ESTADOS DE CAMINERÍA - CERRO LARGO\n")
    temp_file.write("=" * 50 + "\n\n")
    temp_file.write(f"Generado el: {now.strftime('%d/%m/%Y %H:%M:%S')}\n\n")
    
    # Resumen
    total_zones = len(states)
    green_count = sum(1 for zone_data in states.values() if zone_data.get('state') == 'green')
    yellow_count = sum(1 for zone_data in states.values() if zone_data.get('state') == 'yellow')
    red_count = sum(1 for zone_data in states.values() if zone_data.get('state') == 'red')
    
    temp_file.write("RESUMEN GENERAL\n")
    temp_file.write("-" * 20 + "\n")
    temp_file.write(f"Total de Zonas: {total_zones}\n")
    temp_file.write(f"🟩 Habilitadas: {green_count}\n")
    temp_file.write(f"🟨 En Alerta: {yellow_count}\n")
    temp_file.write(f"🟥 Suspendidas: {red_count}\n\n")
    
    # Detalle por zona
    temp_file.write("DETALLE POR ZONA/MUNICIPIO\n")
    temp_file.write("-" * 30 + "\n")
    
    for zone_name, zone_data in sorted(states.items()):
        state = zone_data.get('state', 'green')
        state_label = {
            'green': '🟩 Habilitado',
            'yellow': '🟨 Alerta',
            'red': '🟥 Suspendido'
        }.get(state, 'Sin estado')
        
        updated_at = zone_data.get('updated_at', 'N/A')
        if updated_at != 'N/A':
            try:
                if isinstance(updated_at, str):
                    dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                else:
                    dt = updated_at
                updated_at = dt.strftime("%d/%m/%Y %H:%M")
            except:
                updated_at = 'N/A'
        
        updated_by = zone_data.get('updated_by', 'N/A')
        
        temp_file.write(f"\nZona: {zone_name}\n")
        temp_file.write(f"Estado: {state_label}\n")
        temp_file.write(f"Última Actualización: {updated_at}\n")
        temp_file.write(f"Actualizado Por: {updated_by}\n")
        temp_file.write("-" * 40 + "\n")
    
    temp_file.write(f"\n\nSistema de Gestión de Caminería - Cerro Largo\n")
    temp_file.write(f"Departamento de Cerro Largo - Uruguay\n")
    temp_file.close()
    
    # Enviar archivo
    return send_file(
        temp_file.name,
        as_attachment=True,
        download_name=f'reporte_camineria_cerro_largo_{now.strftime("%Y%m%d_%H%M%S")}.txt',
        mimetype='text/plain'
    )

@report_bp.route('/generate-data', methods=['GET'])
def generate_report_data():
    """Generar datos del reporte para el frontend - disponible para todos"""
    try:
        states = ZoneState.get_all_states()
        
        # Contar estados
        state_counts = {'green': 0, 'yellow': 0, 'red': 0}
        for zone_data in states.values():
            state = zone_data.get('state', 'green')
            state_counts[state] = state_counts.get(state, 0) + 1
        
        report_data = {
            'generated_at': datetime.utcnow().isoformat(),
            'total_zones': len(states),
            'state_summary': state_counts,
            'zones': states
        }
        
        return jsonify({
            'success': True,
            'report': report_data
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al generar datos del reporte: {str(e)}'
        }), 500
