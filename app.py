from flask import Flask, request, jsonify
import requests
import os
from jinja2 import Template
import smtplib
from email.message import EmailMessage

app = Flask(__name__)

CLICKUP_TOKEN = os.environ.get("CLICKUP_TOKEN")
EMAIL_SENDER = "c360@robotix.es"
EMAIL_PASSWORD = "Worc3st3r45+"
EMAIL_RECIPIENT = "cgallego@robotix.es"

@app.route('/webhook', methods=['POST'])
def webhook():
    # Extract task_id from URL query parameters
    task_id = request.args.get('id')
    
    if not task_id:
        return "Task ID not provided", 400  # Respond with an error if no task_id is provided

    print(f"Received task_id: {task_id}")
    print(f"✅ Webhook recibido para task_id: {task_id}")

    task_info = get_task_info(task_id)
    filled_txt = generate_txt(task_info)
    send_email_with_attachment(filled_txt)

    return jsonify({"status": "Email sent"})

def get_task_info(task_id):

    # Set the headers for the API request, including the Authorization token
    HEADERS = {
        'Authorization': CLICKUP_TOKEN
    }
    url_global = f'https://api.clickup.com/api/v2/task/{task_id}'
    response = requests.get(url_global, headers=HEADERS)
    if response.status_code == 200:
        # If the request was successful, parse the JSON response
        task_data = response.json()
        print(f"DADES_TASK: {task_data}")
        custom_fields = task_data.get('custom_fields', [])
    
        #print("CUSTOM: ", custom_fields)
    
        return custom_fields
    else:
        return null
                   

def generate_txt(task_data):
    with open("template.txt", "r", encoding="utf-8") as f:
        template = Template(f.read())

    # Map custom fields
    fields = {
        cf['name']: cf.get('value', '') for cf in task_data.get('custom_fields', [])
    }

    # Añadir campos estándar de ClickUp
    fields['Nombre_Tarea'] = task_data.get("name")

    output = template.render(**fields)

    filename = "resultados.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(output)

    return filename

def send_email_with_attachment(filename):
    msg = EmailMessage()
    msg['Subject'] = "Exportación desde ClickUp"
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECIPIENT
    msg.set_content("Adjunto el fichero generado a partir de la tarea de ClickUp.")

    with open(filename, "rb") as f:
        msg.add_attachment(f.read(), maintype="text", subtype="plain", filename=filename)

    with smtplib.SMTP_SSL("smtp.ionos.es", 465) as smtp:
        smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtp.send_message(msg)
