from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime
from jinja2 import Template
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
import base64
import json
import logging

app = Flask(__name__)

# =======================
# CONFIGURACIÓN
# =======================

CLICKUP_TOKEN = os.environ.get("CLICKUP_TOKEN")
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT")
MAILJET_API_KEY = os.environ.get("API_PUBLICA_MAILJET")
MAILJET_API_SECRET = os.environ.get("API_SECRETA_MAILJET")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO_OWNER = os.environ.get("GITHUB_REPO_OWNER")
GITHUB_REPO_NAME = os.environ.get("GITHUB_REPO_NAME")
TRIGGER_CUSTOM_FIELD = os.environ.get("TRIGGER_CUSTOM_FIELD")

GITHUB_FILES = ["credentials.json", "token.json"]

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

# Diccionario de campos personalizados
selected_custom = {
    "ROB: Nom Escola": "Nombre_Escuela", 
    "ROB: Codi Client": "Codigo_Cliente", 
    "ROB: Responsable Centre": "Resp_Centro", 
    "ROB: Telef. Resp.Centro": "Tel_Resp_Centro", 
    "ROB: Email Responsable": "Email_Resp_Centro", 
    "ROB: Director Centro": "Director_Centro", 
    "ROB: email Director Centro": "Email_Director_Centro", 
    "ROB: Dirección Centro": "Direccion_Centro",
    "ROB: Altres emails contacte": "Otros_Correos", 
    "ROB: AP": "AP_Responsable", 
    "ROB: PM": "PM_Responsable", 
    "ROB: Comercial": "Comercial_Responsable", 
    "ROB: Students": "Num_Estudiantes", 
    "ROB: Ensenyaments": "Ensenyaments", 
    "ROB: Groups": "Num_Grups", 
    "ROB: Eventualidad": "Eventualidad", 
    "ROB: Idioma Contenido": "Idioma_Contenido",
    "ROB: Tipos de Dispositivos": "Tipos_Dispositivos", 
    "ROB: Tipo de Acceso Plataforma": "Tipo_Acceso", 
    "ROB: STATUS_Escola": "Status_Escuela", 
    "ROB: Robots CR": "Numero_CR",
    "ROB: Ratio Robots CR": "Ratio_CR", 
    "ROB: Robots SP": "Numero_SP", 
    "ROB: Ratio Robots SP": "Ratio_SP", 
    "ROB: Rec Addicionals": "Recursos_Adicionales", 
    "ROB: Rotació Material": "Rotacion_Material",
    "ROB: TALLADORA 4.0 xTool m1": "XTool_M1", 
    "ROB: Curs Inicial": "Curso_Inicial", 
    "ROB: Tipus conveni": "Tipo_Convenio", 
    "ROB: Último Convenio": "Ultimo_Convenio",
    "ROB: FI CONVENI": "Vencimiento_Convenio", 
    "Comentarios": "Comentarios"
}

# =======================
# ENDPOINT PRINCIPAL
# =======================
@app.route('/webhook', methods=['POST'])
def webhook():
    task_id = request.args.get('id')
    if not task_id:
        return "Task ID not provided", 400

    print(f"✅ Webhook recibido para task_id: {task_id}")

    task_info = get_task_info(task_id)
    if not task_info:
        return "No se pudo obtener la tarea", 500

    custom_f = generate_txt(task_info)
    uncheck_custom_field(task_id, custom_f, TRIGGER_CUSTOM_FIELD)
    creds = authenticate_gmail_api()
    try:
        service = build('gmail', 'v1', credentials=creds)
        send_email_with_attachment(
            service,
            sender="c360@robotix.es",
            to=EMAIL_RECIPIENT,
            subject= "📩 Exportación de ficha desde ClickUp: "+task_info.get('name'),
            body="Adjunto el archivo generado a partir de los datos de ClickUp.",
            file_path="resultados.txt"
        )
    except Exception as error:
        print(f"Ha ocurrido un error: {error}")

    return jsonify({"status": "Email sent"})

# =======================
# FUNCIONES AUXILIARES
# =======================

def get_task_info(task_id):
    url = f'https://api.clickup.com/api/v2/task/{task_id}'
    headers = {'Authorization': CLICKUP_TOKEN}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    print("Error al consultar la tarea:", response.text)
    return None

from datetime import datetime
from jinja2 import Template

def generate_txt(task_data):
    with open("template.txt", "r", encoding="utf-8") as f:
        template = Template(f.read())

    custom_fields = task_data.get('custom_fields', [])
    fields = {}

    # Añadir fecha actual en formato dd/mm/yyyy
    fields['Fecha_Informe'] = datetime.today().strftime('%d/%m/%Y')

    # Añadir datos adicionales
    fields['Datos_Adicionales'] = task_data.get('description')
    
    # Procesar los campos personalizados
    for cf in custom_fields:
        original_name = cf.get('name')
        field_type = cf.get('type')
        value = cf.get('value')
        alias = selected_custom.get(original_name)

        if alias:  # Solo si el campo está en el diccionario de campos seleccionados
            if field_type == 'drop_down':
                selected_name = ''
                options = cf.get('type_config', {}).get('options', [])

                # Caso: el valor es un diccionario (raro, pero podría pasar)
                if isinstance(value, dict):
                    selected_name = value.get('name', '')

                # Caso: el valor es un string (ID de la opción seleccionada)
                elif isinstance(value, str):
                    for opt in options:
                        if opt.get('id') == value:
                            selected_name = opt.get('name', '')
                            break

                # Caso: el valor es un entero (orderindex de la opción seleccionada)
                elif isinstance(value, int):
                    for opt in options:
                        if opt.get('orderindex') == value:
                            selected_name = opt.get('name', '')
                            break

                fields[alias] = selected_name

            else:
                # Cualquier otro tipo de campo
                fields[alias] = str(value) if value is not None else ''

    # Agregar nombre de la tarea también
    fields['Nombre_Tarea'] = task_data.get("name", "Sin nombre")

    print("📄 Campos usados para generar resultados.txt:", fields)

    output = template.render(**fields)
    with open("resultados.txt", "w", encoding="utf-8") as f:
        f.write(output)
    return custom_fields

def download_secret_file_from_github(filename, repo_owner, repo_name, github_token):
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3.raw"
    }

    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{filename}"

    print(f"🔍 Buscando '{filename}' en el repositorio: {repo_owner}/{repo_name}")
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        content = response.content
        with open(filename, 'wb') as f:
            f.write(content)
        print(f"✅ Archivo '{filename}' descargado correctamente.")
    else:
        print(f"❌ Error descargando '{filename}': {response.status_code} - {response.text}")
        raise FileNotFoundError(f"No se pudo descargar '{filename}' desde GitHub.")

# Función para desmarcar el custom field 'ROB: Generar Informe'
def uncheck_custom_field(task_id, custom_fields, custom_field_name):
    # Buscar el custom field por nombre
    for field in custom_fields:
        if field.get('name') == custom_field_name:
            custom_field_id = field.get('id')
            break

    if not custom_field_id:
        print(f"❌ No se encontró el campo personalizado {custom_field_name} en la tarea.")
        return

    headers = {
        'Authorization': CLICKUP_TOKEN
    }

    data = {"value": False}

    # Ahora, realizar una solicitud para actualizar el custom field
    url = f'https://api.clickup.com/api/v2/task/{task_id}/field/{custom_field_id}'
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        print(f"✅ El campo personalizado {custom_field_name} ha sido desmarcado correctamente en la tarea {task_id}.")
    else:
        print(f"❌ Error al actualizar el campo personalizado: {response.text}")


def authenticate_gmail_api():
    repo_owner = os.getenv("GITHUB_REPO_OWNER")
    repo_name = os.getenv("GITHUB_REPO_NAME")
    github_token = os.getenv("GITHUB_PAT")

    # Descargamos los archivos desde el repositorio privado
    download_secret_file_from_github("credentials.json", repo_owner, repo_name, github_token)
    download_secret_file_from_github("token.json", repo_owner, repo_name, github_token)
    
    if not os.path.exists("credentials.json"):
        raise FileNotFoundError("El archivo 'credentials.json' no se encuentra en el directorio.")

    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", 'w') as token:
            token.write(creds.to_json())

    return creds

def create_message_with_attachment(sender, to, subject, body, file_path):
    message = MIMEMultipart()
    message['From'] = sender
    message['To'] = to
    message['Subject'] = subject
    message.attach(MIMEText(body, 'plain'))

    try:
        with open(file_path, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(file_path)}')
            message.attach(part)
    except Exception as e:
        print(f"Error al adjuntar el archivo: {e}")
        return None

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    return {'raw': raw_message}

def send_email_with_attachment(service, sender, to, subject, body, file_path):
    try:
        message = create_message_with_attachment(sender, to, subject, body, file_path)
        if message:
            sent = service.users().messages().send(userId="me", body=message).execute()
            print(f"📨 Correo enviado con ID: {sent['id']}")
        else:
            print("⚠️ No se pudo crear el mensaje.")
    except HttpError as error:
        print(f"❌ Error al enviar el correo: {error}")
        raise
