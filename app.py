from flask import Flask, request, jsonify
import requests
import os
from jinja2 import Template
import smtplib
from email.message import EmailMessage
from mailjet_rest import Client

app = Flask(__name__)

CLICKUP_TOKEN = os.environ.get("CLICKUP_TOKEN")
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT")         # Ejemplo: cgallego@robotix.es
MAILJET_API_KEY = os.environ.get("API_PUBLICA_MAILJET")  # Tu API key pública
MAILJET_API_SECRET = os.environ.get("API_SECRETA_MAILJET")  # Tu API key privada

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
    send_email_with_attachment(filled_txt)

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


def send_email_with_attachment(filename):
    with open(filename, "r", encoding="utf-8") as f:
        contenido = f.read()

    # Configura el cliente Mailjet
    mailjet = Client(auth=(MAILJET_API_KEY, MAILJET_API_SECRET), version='v3.1')

    # Prepara el cuerpo del correo
    data = {
        'Messages': [
            {
                "From": {
                    "Email": "example@mailjet.com",  # Usamos el remitente predeterminado de Mailjet
                    "Name": "ClickUp Informe"  # Nombre del remitente
                },
                "To": [
                    {
                        "Email": EMAIL_RECIPIENT,
                        "Name": "Carles Gallego"  # Nombre del destinatario
                    }
                ],
                "Subject": "📩 Exportación informe desde ClickUp",
                "TextPart": "Adjunto el contenido de la tarea:",
                "Attachments": [
                    {
                        "ContentType": "text/plain",
                        "Filename": filename,
                        "Base64Content": contenido.encode("utf-8").decode("utf-8")  # Convierte el contenido a base64
                    }
                ]
            }
        ]
    }

    # Envía el correo
    result = mailjet.send(data=data)
    if result.status_code == 200:
        print("✅ Email enviado con Mailjet")
    else:
        print("❌ Error al enviar con Mailjet:", result.status_code, result.text)
