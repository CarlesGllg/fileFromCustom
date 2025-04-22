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

@app.route('/webhook/<task_id>', methods=['POST'])
def webhook(task_id):
    print(f"Primer punto!!")
    if not task_id:
        print(f"ERROR 1!!!")
        return jsonify({"error": "No task_id in URL"}), 400

    print(f"✅ Webhook recibido para task_id: {task_id}")

    task_info = get_task_info(task_id)
    filled_txt = generate_txt(task_info)
    send_email_with_attachment(filled_txt)

    return jsonify({"status": "Email sent"})

def get_task_info(task_id):
    headers = {
        "Authorization": CLICKUP_TOKEN
    }
    url = f"https://api.clickup.com/api/v2/task/{task_id}"
    response = requests.get(url, headers=headers)
    if response.result == 200:
        print("Task = {task_id}.")
        response.raise_for_status()
        return response.json()
    else:
        print("No hi ha info de task.")
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
