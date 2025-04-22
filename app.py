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
GITHUB_REPO_OWNER = "cgallego@robotix.es"         # 🔁 Cambia por tu nombre de usuario de GitHub
GITHUB_REPO_NAME = "myfiles"        # 🔁 Cambia por el nombre de tu repo privado
GITHUB_FILES = ["credentials.json", "token.json"]

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

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

    generate_txt(task_info)

    # Asegurarse de tener credenciales locales descargadas
    download_files_from_github()

    creds = authenticate_gmail_api()
    try:
        service = build('gmail', 'v1', credentials=creds)
        send_email_with_attachment(
            service,
            sender="c360@robotix.es",
            to=EMAIL_RECIPIENT,
            subject="📩 Exportación de ficha desde ClickUp",
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

def generate_txt(task_data):
    with open("template.txt", "r", encoding="utf-8") as f:
        template = Template(f.read())

    custom_fields = task_data.get('custom_fields', [])
    fields = {cf['name']: cf.get('value', '') for cf in custom_fields}
    fields['Nombre_Tarea'] = task_data.get("name", "Sin nombre")

    output = template.render(**fields)
    with open("resultados.txt", "w", encoding="utf-8") as f:
        f.write(output)

def download_files_from_github():
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3.raw"
    }

    for filename in GITHUB_FILES:
        url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{filename}"
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            content = base64.b64decode(response.json()["content"])
            with open(filename, "wb") as f:
                f.write(content)
            print(f"✅ '{filename}' descargado correctamente.")
        else:
            print(f"❌ Error descargando '{filename}': {response.status_code} - {response.text}")

def authenticate_gmail_api():
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
