# -*- coding: utf-8 -*-
import os
import telebot
import mercadopago
import logging
from flask import Flask, request, jsonify

# --- 1. CONFIGURAÇÃO ---
BOT_TOKEN = "8487273468:AAHqd2NlNCb0HyG6IeJ784YY5A_YI3xemGw"
MP_ACCESS_TOKEN = "APP_USR-6797918640127185-112319-1c452a696a8c3b443de9b0fe2baa9c01-318433737"
VALOR_GRUPO = 2.0  # <-- Alterado para R$ 2,00
ID_GRUPO_VIP = -1002915685276
WEBHOOK_MP = "https://namiradogreenacess.fly.dev/mercadopago_webhook"

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- INICIALIZAÇÃO ---
bot = telebot.TeleBot(BOT_TOKEN)
mp_sdk = mercadopago.SDK(MP_ACCESS_TOKEN)
app = Flask(__name__)

# --- DICIONÁRIO PARA CONTROLE DE PAGAMENTOS ---
payments = {}

# --- FUNÇÃO PARA CRIAR LINK VIP ---
def create_invite_link(user_id):
    try:
        link = bot.create_chat_invite_link(
            chat_id=ID_GRUPO_VIP,
            member_limit=1,
            name=f"Acesso VIP - User ID {user_id}"
        )
        return link.invite_link
    except Exception as e:
        logging.error(f"Erro ao criar link para {user_id}: {e}")
        return "https://t.me/seu_grupo_padrao"

# --- COMANDO /start ---
@bot.message_handler(commands=['start'])
def start_payment(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name

    # --- CRIA PREFERÊNCIA PIX ---
    preference_data = {
        "items": [
            {
                "title": "Assinatura Grupo VIP Oráculo do Green",
                "quantity": 1,
                "unit_price": VALOR_GRUPO
            }
        ],
        "payer": {
            "email": f"user_{user_id}@example.com"
        },
        "payment_methods": {
            "excluded_payment_types": [{"id": "credit_card"}],
            "installments": 1
        },
        "notification_url": WEBHOOK_MP,
        "external_reference": str(user_id)
    }

    preference_response = mp_sdk.preference().create(preference_data)

    if preference_response["status"] == 201:
        pix_info = preference_response["response"]["point_of_interaction"]["transaction_data"]["qr_code"]
        text = f"""👋 Olá {user_name}!

💎 Para acessar o grupo VIP do Oráculo do Green, faça o pagamento via PIX:

💰 Valor: R$ {VALOR_GRUPO:,.2f}
📌 PIX Copia e Cola: 


O pagamento será detectado automaticamente pelo Mercado Pago e você receberá seu link VIP assim que confirmado.
"""
        bot.send_message(chat_id, text, parse_mode="Markdown")
        payments[str(user_id)] = {"chat_id": chat_id, "paid": False}
    else:
        bot.send_message(chat_id, "❌ Ocorreu um erro ao gerar seu PIX. Tente novamente mais tarde.")

# --- WEBHOOK MERCADO PAGO ---
@app.route("/mercadopago_webhook", methods=['POST'])
def mercadopago_webhook():
    data = request.json
    try:
        if data.get('topic') == 'payment':
            payment_id = data.get('resource', '').split('/')[-1]
            payment_resp = mp_sdk.payment().get(payment_id)
            if payment_resp['status'] == 200:
                payment_data = payment_resp['response']
                status = payment_data.get('status')
                if status == 'approved':
                    external_ref = payment_data.get('external_reference')
                    if external_ref and external_ref in payments and not payments[external_ref]["paid"]:
                        chat_id = payments[external_ref]["chat_id"]
                        link = create_invite_link(external_ref)
                        bot.send_message(chat_id, f"🎉 Pagamento confirmado! Aqui está seu link VIP:\n{link}")
                        payments[external_ref]["paid"] = True
                        logging.info(f"Link enviado para {external_ref}")
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        logging.error(f"Erro webhook MP: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

# --- WEBHOOK TELEGRAM ---
@app.route("/telegram_webhook", methods=['POST'])
def telegram_webhook():
    json_data = request.get_json()
    if json_data:
        update = telebot.types.Update.de_json(json_data)
        bot.process_new_updates([update])
    return "OK", 200

# --- INDEX ---
@app.route("/")
def index():
    return "Bot Telegram rodando via Webhook - Fly.io"

# --- INICIALIZAÇÃO ---
if __name__ == "__main__":
    print("Bot pronto para rodar via webhook no Fly.io.")
