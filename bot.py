# -*- coding: utf-8 -*-
import os
import telebot
import mercadopago
import logging
from flask import Flask, request, jsonify

# --- 1. CONFIGURAÇÃO ---
BOT_TOKEN = "8487273468:AAHqd2NlNCb0HyG6IeJ784YY5A_YI3xemGw"
MP_ACCESS_TOKEN = "APP_USR-6797918640127185-112319-1c452a696a8c3b443de9b0fe2baa9c01-318433737"
VALOR_GRUPO = 397.0
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
