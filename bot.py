import os
import telebot
import mercadopago
import logging
import json
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import threading
import time
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- CONFIGURAÇÃO ---
BOT_TOKEN = "8363865808:AAFM3x0a2aiO7ESwUaQK-H4w5fH0eYOE1UU"
MP_ACCESS_TOKEN = "APP_USR-6797918640127185-112319-1c452a696a8c3b443de9b0fe2baa9c01-318433737"
VALOR_GRUPO = 2.0
ID_GRUPO_VIP = -1002915685276
PAYMENTS_FILE = "payments.json"  # arquivo para persistência

logging.basicConfig(level=logging.INFO)

bot = telebot.TeleBot(BOT_TOKEN)
mp_sdk = mercadopago.SDK(MP_ACCESS_TOKEN)
app = Flask(__name__)

# --- Carrega pagamentos pendentes do arquivo ---
if os.path.exists(PAYMENTS_FILE):
    with open(PAYMENTS_FILE, "r") as f:
        payments = json.load(f)
else:
    payments = {}

# --- Função para salvar pagamentos ---
def save_payments():
    with open(PAYMENTS_FILE, "w") as f:
        json.dump(payments, f)

# --- Função para criar link VIP ---
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

# =======================================
# =========  MENU / START  ==============
# =======================================

@bot.message_handler(commands=['start'])
def start_menu(message):
    user_id = message.from_user.id

    # Se o usuário já usou o teste gratuito → só pode ver o VIP
    if payments.get(str(user_id), {}).get("teste_usado"):
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("💎 ADQUIRIR O VIP", callback_data="adquirir_vip")
        )
        bot.send_message(
            message.chat.id,
            "👋 Olá! Seu teste gratuito já foi utilizado.\nAgora você pode adquirir o VIP:",
            reply_markup=keyboard
        )
        return

    # Caso ainda não tenha usado → mostra os dois botões
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("🔥 QUERO MEU TESTE GRATUITO", callback_data="teste_gratis"),
        InlineKeyboardButton("💎 ADQUIRIR O VIP", callback_data="adquirir_vip")
    )

    bot.send_message(
        message.chat.id,
        "👋 Olá! Escolha uma das opções abaixo:",
        reply_markup=keyboard
    )

# =======================================
# ======== TESTE GRATUITO ===============
# =======================================

@bot.callback_query_handler(func=lambda call: call.data == "teste_gratis")
def handle_teste_gratis(call):
    user_id = call.from_user.id

    # Se já usou uma vez na vida → bloqueia
    if payments.get(str(user_id), {}).get("teste_usado"):
        bot.answer_callback_query(call.id, "❌ Você já usou seu teste gratuito.")
        bot.send_message(user_id, "⛔ O teste gratuito só pode ser utilizado 1 vez.")
        return

    # Criar link de teste
    try:
        link = bot.create_chat_invite_link(
            chat_id=ID_GRUPO_VIP,
            member_limit=1,
            expire_date=int(time.time()) + 5 * 24 * 60 * 60,  # expira em 5 dias
            name=f"Teste Gratuito - {user_id}"
        ).invite_link
    except:
        link = "https://t.me/seu_grupo_padrao"

    expire_date = datetime.now() + timedelta(days=5)

    payments[str(user_id)] = {
        "teste_usado": True,         # PERMANENTE – nunca mais pode pedir teste
        "teste_ativo": True,
        "teste_expira": expire_date.isoformat(),
        "link_teste_entregue": True
    }
    save_payments()

    bot.answer_callback_query(call.id, "Teste ativado!")
    bot.send_message(
        user_id,
        f"🎉 *TESTE GRATUITO ATIVADO!*\n"
        f"⏳ Duração: *5 dias*\n\n"
        f"💡 Após o período, você será removido automaticamente, "
        f"mas poderá retornar adquirindo o VIP.\n\n"
        f"👉 Aqui está seu link de acesso:\n{link}",
        parse_mode="Markdown"
    )

# =======================================
# ========== ADQUIRIR VIP ===============
# =======================================

@bot.callback_query_handler(func=lambda call: call.data == "adquirir_vip")
def adquirir_vip(call):
    message = call.message
    chat_id = message.chat.id
    user_id = call.from_user.id
    user_name = call.from_user.first_name

    # NÃO PERMITE COMPRAR VIP ENQUANTO ESTÁ EM TESTE
    info = payments.get(str(user_id), {})
    if info.get("teste_ativo"):
        bot.answer_callback_query(call.id, "⛔ Aguarde o fim do teste gratuito.")
        bot.send_message(chat_id, "❌ Você só pode adquirir o VIP após o término do seu teste gratuito.")
        return

    # Gera o PIX normalmente
    payment_data = {
        "transaction_amount": VALOR_GRUPO,
        "description": "Assinatura Grupo VIP",
        "payment_method_id": "pix",
        "payer": {"email": f"user_{user_id}@example.com"},
        "external_reference": str(user_id)
    }

    try:
        payment_resp = mp_sdk.payment().create(payment_data)
        if payment_resp["status"] in [200, 201]:
            pix_code = payment_resp["response"]["point_of_interaction"]["transaction_data"]["qr_code"]
            payment_id = str(payment_resp["response"]["id"])
            payments[payment_id] = {"chat_id": chat_id, "link_entregue": False}
            save_payments()

            text = f"""👋 Olá {user_name}!

💰 Valor: R$ {VALOR_GRUPO:,.2f}
📌 PIX Copia e Cola:

\n`{pix_code}`

O pagamento será detectado automaticamente. Assim que confirmado, você receberá seu link VIP.
"""
            bot.send_message(chat_id, text, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "❌ Erro ao gerar PIX. Tente novamente.")
    except Exception as e:
        logging.error(f"Erro ao gerar PIX: {e}")
        bot.send_message(chat_id, "❌ Erro ao gerar PIX. Tente novamente.")

# =======================================
# ======= WEBHOOK MERCADO PAGO ==========
# =======================================

@app.route("/mercadopago_webhook", methods=["POST"])
def mercadopago_webhook():
    data = request.json
    try:
        if data.get("type") == "payment":
            payment_id = str(data.get("data", {}).get("id"))
            if not payment_id:
                return jsonify({"status": "ok"}), 200

            payment_resp = mp_sdk.payment().get(payment_id)
            payment_info = payment_resp.get("response", {})

            if payment_info.get("status") == "approved":
                user_id_str = payment_info.get("external_reference")
                if not user_id_str:
                    return jsonify({"status": "ok"}), 200

                user_id = int(user_id_str)

                # Renovação
                if payment_id in payments and payments[payment_id]["link_entregue"]:
                    old_end = datetime.fromisoformat(payments[payment_id]["end_date"])
                    payments[payment_id]["end_date"] = (old_end + timedelta(days=30)).isoformat()
                    save_payments()
                    bot.send_message(user_id, "✅ Renovação confirmada! +30 dias de acesso VIP.")
                else:
                    # Envia link novo
                    link = create_invite_link(user_id)
                    bot.send_message(user_id, f"✅ Pagamento confirmado! Aqui está seu link VIP:\n{link}")
                    payments[payment_id]["link_entregue"] = True
                    payments[payment_id]["start_date"] = datetime.now().isoformat()
                    payments[payment_id]["end_date"] = (datetime.now() + timedelta(days=30)).isoformat()
                    save_payments()

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logging.error(f"Erro no webhook MP: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

# =======================================
# ========== WEBHOOK TELEGRAM ===========
# =======================================

@app.route("/telegram_webhook", methods=["POST"])
def telegram_webhook():
    json_data = request.get_json()
    if json_data:
        update = telebot.types.Update.de_json(json_data)
        bot.process_new_updates([update])
    return "OK", 200

# =======================================
# ======== VERIFICAÇÃO PERIÓDICA =========
# =======================================

CHECK_INTERVAL = 60 * 60  # 1 hora

def periodic_check():
    while True:
        now = datetime.now()

        for uid, info in list(payments.items()):

            # TESTE GRATUITO – remover após 5 dias
            if info.get("teste_ativo"):
                exp = datetime.fromisoformat(info["teste_expira"])
                if now > exp:
                    try:
                        bot.kick_chat_member(ID_GRUPO_VIP, int(uid))
                    except:
                        pass
                    info["teste_ativo"] = False
                    save_payments()

            # VIP – avisos e expulsões
            if info.get("end_date"):
                end = datetime.fromisoformat(info["end_date"])
                chat_id = info.get("chat_id")

                # Aviso 3 dias antes
                if "renewal_notified" not in info and (end - now).days == 3:
                    keyboard = InlineKeyboardMarkup()
                    keyboard.add(
                        InlineKeyboardButton("Renovar agora", callback_data=f"renew_{uid}")
                    )
                    bot.send_message(chat_id, "⚠️ Seu acesso VIP irá expirar em 3 dias.", reply_markup=keyboard)
                    info["renewal_notified"] = True
                    save_payments()

                # Expirado
                if now > end:
                    try:
                        bot.kick_chat_member(ID_GRUPO_VIP, int(uid))
                    except:
                        pass
                    del payments[uid]
                    save_payments()

        time.sleep(CHECK_INTERVAL)

threading.Thread(target=periodic_check, daemon=True).start()

# =======================================
# ====== RENOVAÇÃO MANUAL VIA BOT =======
# =======================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("renew_"))
def handle_renew(call):
    uid = call.data.split("_")[1]
    user_id = call.from_user.id

    payment_data = {
        "transaction_amount": VALOR_GRUPO,
        "description": "Renovação Grupo VIP",
        "payment_method_id": "pix",
        "payer": {"email": f"user_{user_id}@example.com"},
        "external_reference": str(user_id)
    }

    payment_resp = mp_sdk.payment().create(payment_data)
    pix_code = payment_resp["response"]["point_of_interaction"]["transaction_data"]["qr_code"]
    bot.send_message(user_id, f"💰 PIX para renovação:\n`{pix_code}`", parse_mode="Markdown")

# =======================================
# ============ INDEX =====================
# =======================================

@app.route("/")
def index():
    return "Bot rodando via Webhook"

if __name__ == "__main__":
    print("Bot pronto para rodar via webhook")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
