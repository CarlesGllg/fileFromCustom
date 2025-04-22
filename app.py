from flask import Flask, request, jsonify
import requests
import os
from jinja2 import Template
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import base64
import json
import time
import logging

app = Flask(__name__)

CLICKUP_TOKEN = os.environ.get("CLICKUP_TOKEN")
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT")         # Ejemplo: cgallego@robotix.es
MAILJET_API_KEY = os.environ.get("API_PUBLICA_MAILJET")  # Tu API key pública
MAILJET_API_SECRET = os.environ.get("API_SECRETA_MAILJET")  # Tu API key privada

# Los alcances necesarios para enviar correos
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# Ruta a los archivos de credenciales y token desde las variables de entorno
CRED_FILE = os.getenv("CRED_FILE")  # Se espera que esté en una variable de entorno
TOKEN_FILE = os.getenv("TOK_FILE")  # Se espera que esté en una variable de entorno

@app.route('/webhook', methods=['POST'])
def webhook():
    # Extraer task_id desde la URL (query parameter)
    task_id = request.args.get('id')

    if not task_id:
        return "Task ID not provided", 400

    print(f"✅ Webhook recibido para task_id: {task_id}")

    task_info = get_task_info(task_id)

    if not task_info:
        return "No se pudo obtener la tarea", 500

    filled_txt = generate_txt(task_info)
    
    creds = authenticate_gmail_api()
    
    try:
        # Crear el servicio de Gmail
        service = build('gmail', 'v1', credentials=creds)
        
        sender = "c360@robotix.es"
        recipient = EMAIL_RECIPIENT  # Este es el correo del destinatario
        subject = "📩 Exportación de ficha desde ClickUp"
        body = "Adjunto el archivo generado a partir de los datos de ClickUp."
        file_path = 'resultados.txt'  # Ruta del archivo que quieres adjuntar
        
        # Enviar el correo
        send_email_with_attachment(service, sender, recipient, subject, body, file_path)

    except Exception as error:
        print(f"Ha ocurrido un error: {error}")

    return jsonify({"status": "Email sent"})


def get_task_info(task_id):
    headers = {
        'Authorization': CLICKUP_TOKEN
    }
    url = f'https://api.clickup.com/api/v2/task/{task_id}'
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        task_data = response.json()
        print(f"DADES_TASK: {task_data}")
        return task_data  # 🔁 Ahora retornamos todo el objeto, no solo los custom fields
    else:
        print("Error al consultar la tarea:", response.text)
        return None


def generate_txt(task_data):
    with open("template.txt", "r", encoding="utf-8") as f:
        template = Template(f.read())

    # Obtener los campos personalizados
    custom_fields = task_data.get('custom_fields', [])

    # Mapeo de nombres -> valores
    fields = {
        cf['name']: cf.get('value', '') for cf in custom_fields
    }

    # Agregar campos estándar de la tarea
    fields['Nombre_Tarea'] = task_data.get("name", "Sin nombre")

    output = template.render(**fields)

    filename = "resultados.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(output)

    return filename

def write_secret_file(env_var_value, filename):
    """Escribe el contenido base64 de una variable de entorno en un archivo."""
    if env_var_value:
        content = base64.b64decode(env_var_value.encode('utf-8'))
        with open(filename, 'wb') as f:
            f.write(content)

def authenticate_gmail_api():
    """Autenticarse con Gmail usando los secretos decodificados."""
    write_secret_file(CRED_FILE, "credentials.json")
    write_secret_file(TOKEN_FILE, "token.json")

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
    """Crea un mensaje con un archivo adjunto codificado en base64."""
    # Crear un mensaje MIME
    message = MIMEMultipart()
    message['From'] = sender
    message['To'] = to
    message['Subject'] = subject

    # Añadir el cuerpo del mensaje
    message.attach(body)

    # Leer el archivo y codificarlo en base64
    try:
        with open(file_path, 'rb') as f:
            # Crear el objeto MIMEBase
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
    """Envía un correo electrónico con un archivo adjunto a través de la API de Gmail."""
    try:
        message = create_message_with_attachment(sender, to, subject, body, file_path)
        if message:
            message_sent = service.users().messages().send(userId="me", body=message).execute()
            print(f"Correo enviado con ID: {message_sent['id']}")
        else:
            print("No se pudo crear el mensaje.")
    except HttpError as error:
        print(f"Hubo un error: {error}")
        raise
