from email.message import EmailMessage
import smtplib
from flask import current_app


def send_teacher_email(check, report_text):
    msg = EmailMessage()
    msg['Subject'] = f"✅ Новая проверка: {check.original_filename}"
    msg['From'] = current_app.config['MAIL_DEFAULT_SENDER']
    msg['To'] = current_app.config['TEACHER_EMAIL']

    msg.set_content_type('text/html; charset=UTF-8')
    msg.add_alternative(f"""
    <h3>Завершена проверка презентации</h3>
    <p><strong>Файл:</strong> {check.original_filename}</p>
    <p><strong>Оценка:</strong> {check.grade}</p>
    <hr>
    {report_text}
    """, subtype='html')

    with smtplib.SMTP(current_app.config['MAIL_SERVER'], current_app.config['MAIL_PORT']) as server:
        if current_app.config.get('MAIL_USE_TLS'):
            server.starttls()
        if current_app.config.get('MAIL_USERNAME'):
            server.login(current_app.config['MAIL_USERNAME'], current_app.config['MAIL_PASSWORD'])
        server.send_message(msg)
