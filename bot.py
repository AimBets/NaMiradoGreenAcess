# -*- coding: utf-8 -*-
import telebot
import mercadopago
import datetime
import json
import logging
from flask import Flask, request, jsonify
from firebase_admin import initialize_app, firestore, credentials, auth
from google.auth.exceptions import DefaultCredentialsError

# --- 1. CONFIGURAÇÃO DE VARIÁVEIS DE AMBIENTE E SEGREDOS (PLACEHOLDERS) ---

# Preencha com seus tokens REAIS. Use as credenciais de Produção do Mercado Pago.
# Use um valor seguro para o 'SEGREDO_WEBHOOK' para verificar a autenticidade das notificações.
BOT_TOKEN = "8487273468:AAHqd2NlNCb0HyG6IeJ784YY5A_YI3xemGw"
MP_ACCESS_TOKEN = "APP_USR-6797918640127185-112319-1c452a696a8c3b443de9b0fe2baa9c01-318433737"
VALOR_GRUPO = 397.00
SEGREDO_WEBHOOK = "P5F8yNkElytH7tQWgEB6dckYJDqFRk3R"
ID_GRUPO_VIP = -1002915685276

# --- CONFIGURAÇÃO DO FIREBASE (NÃO ALTERAR) ---
# Variáveis injetadas pelo ambiente Canvas
app_id = globals().get('__app_id', 'default-app-id')
firebase_config = globals().get('__firebase_config')
initial_auth_token = globals().get('__initial_auth_token')

# Configuração de Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 2. INICIALIZAÇÃO DE SERVIÇOS ---

# Inicialização do Bot
bot = telebot.TeleBot(BOT_TOKEN)

# Inicialização do Mercado Pago SDK
mp_sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# Inicialização do Firebase/Firestore
db = None
auth_app = None
if firebase_config:
    try:
        # Tenta inicializar com as credenciais do ambiente
        cred = credentials.Certificate(json.loads(firebase_config))
        firebase_app = initialize_app(cred)
        db = firestore.client()
        auth_app = auth.Client(firebase_app)
        logging.info("Firebase inicializado com sucesso.")
    except (ValueError, DefaultCredentialsError) as e:
        logging.error(f"Erro ao inicializar Firebase: {e}. O bot não poderá usar o Firestore.")
else:
    logging.warning("Configuração do Firebase ausente. O gerenciamento de 30 dias não funcionará.")

# --- 3. FUNÇÕES DE UTILIDADE E FIREBASE ---

def get_user_doc_ref(user_id):
    """Retorna a referência do documento do usuário para a coleção de assinaturas."""
    # Coleção pública para que o bot possa consultar todos os usuários (necessário para o cron job)
    # E para manter um mapeamento entre o ID do Telegram (chat_id) e o ID do pagamento.
    return db.collection(f'artifacts/{app_id}/public/data/subscriptions').document(str(user_id))

def save_subscription(user_id, chat_id, payment_id):
    """Salva o status da assinatura no Firestore."""
    if not db: return False
    
    # Define a data de expiração (30 dias a partir de agora)
    expiration_date = datetime.datetime.now() + datetime.timedelta(days=30)
    
    data = {
        'telegram_user_id': user_id,
        'telegram_chat_id': chat_id, # ID do chat privado com o bot
        'payment_id': payment_id,
        'status': 'active',
        'start_date': datetime.datetime.now(),
        'expiration_date': expiration_date.isoformat(),
        'group_id': ID_GRUPO_VIP
    }
    
    get_user_doc_ref(user_id).set(data)
    logging.info(f"Assinatura salva para o usuário {user_id}. Expira em {expiration_date}.")
    return True

def create_unique_invite_link(chat_id, user_id):
    """Cria um link de convite único e de uso limitado (1 membro) para o grupo."""
    try:
        # A API do Telegram permite criar links de convite
        # 'member_limit=1' garante que apenas uma pessoa possa usar o link.
        # 'name' ajuda a identificar quem usou (opcional).
        invite_link = bot.create_chat_invite_link(
            chat_id=ID_GRUPO_VIP,
            member_limit=1,
            name=f"Acesso VIP - User ID: {user_id}"
        )
        return invite_link.invite_link
    except Exception as e:
        logging.error(f"Erro ao criar link de convite único: {e}")
        # Retorna uma mensagem de erro em caso de falha na criação do link
        return "https://t.me/seu_grupo_padrao" 


# --- FUNÇÃO CRON (Necessita de Agendamento Externo) ---

def check_and_remove_expired_users():
    """
    ⚠️ FUNÇÃO PARA SER CHAMADA POR UM SERVIÇO DE CRON EXTERNO (Ex: a cada 24h).
    Verifica no Firestore quem precisa ser notificado (dia 27) ou removido (dia 30).
    """
    if not db:
        logging.warning("Firestore não está disponível. A lógica de 30 dias não pode ser executada.")
        return

    logging.info("Executando verificação de usuários expirados...")
    
    # 1. Busca todos os usuários ativos
    # Nota: Consultar todos os documentos é a maneira mais simples, mas pode ser caro em grande escala.
    # Em produção, você faria uma consulta filtrada por data.
    users_ref = db.collection(f'artifacts/{app_id}/public/data/subscriptions')
    active_users = users_ref.stream()

    today = datetime.datetime.now()
    
    for doc in active_users:
        data = doc.to_dict()
        user_id = data['telegram_user_id']
        chat_id_privado = data['telegram_chat_id']
        
        try:
            exp_date = datetime.datetime.fromisoformat(data['expiration_date'])
            days_left = (exp_date - today).days

            # Lógica de Notificação (Dia 27)
            if days_left == 3: # 30 dias - 3 dias = Dia 27
                message = (
                    "🚨 *Aviso de Renovação!* 🚨\n\n"
                    "Seu acesso ao grupo premium expira em *3 dias* (na data: {exp_date.strftime('%d/%m/%Y')}). "
                    "Para garantir a continuidade dos seus ganhos e manter seu acesso, renove agora mesmo! "
                    "Clique no botão abaixo para seguir com a renovação."
                )
                markup = telebot.types.InlineKeyboardMarkup()
                # Botão de renovação, segue o mesmo processo do ADQUIRA JÁ
                markup.add(telebot.types.InlineKeyboardButton("✨ RENOVAR AGORA ✨", callback_data=f"RENOVAR_{user_id}"))
                bot.send_message(chat_id_privado, message, parse_mode='Markdown', reply_markup=markup)
                logging.info(f"Notificação de renovação enviada para o usuário {user_id}.")

            # Lógica de Remoção (Dia 30 ou expirado)
            elif days_left < 0:
                # Remove o usuário do grupo
                bot.kick_chat_member(ID_GRUPO_VIP, user_id)
                
                # Atualiza o status no Firestore
                users_ref.document(str(user_id)).update({'status': 'expired'})
                
                # Envia mensagem no chat privado
                bot.send_message(chat_id_privado, 
                                 "❌ Seu acesso expirou e você foi removido do grupo. \n\n"
                                 "Para reativar sua assinatura e voltar a ter acesso, inicie a compra novamente com o comando /comecar."
                )
                logging.info(f"Usuário {user_id} removido e status atualizado para 'expired'.")

        except Exception as e:
            logging.error(f"Erro ao processar expiração para o usuário {user_id}: {e}")

    # Este endpoint DEVE ser chamado por um serviço de CRON externo para que a remoção funcione.
    # Ex: Seu provedor de hospedagem precisa fazer um GET para /cron/check_expirations a cada 24 horas.

# --- 4. FLUXO DO BOT (HANDLERS DO TELEGRAM) ---

@bot.message_handler(commands=['start', 'comecar'])
def send_welcome(message):
    """
    Manipula os comandos /start e /comecar, enviando as mensagens de boas-vindas e a CTA.
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # 1. Mensagem de Boas-Vindas e Valor (Textinho genérico criado)
    welcome_message = (
        f"👋 *Olá, {message.from_user.first_name}! Bem-vindo ao Na Mira do Green!* 👋\n\n"
        "Somos especialistas em otimizar seus resultados com análises precisas e estratégias validadas. "
        "Aqui, você encontra a direção certa para transformar seus investimentos.\n\n"
        f"O acesso ao nosso grupo exclusivo tem o valor de *R$ {VALOR_GRUPO:,.2f}* por 30 dias.\n\n"
        "Dúvidas extras, entrar em contato com o suporte em: `@suportemiradogreen`"
    )
    bot.send_message(chat_id, welcome_message, parse_mode='Markdown')

    # 2. Chamada para Ação (CTA)
    cta_message = (
        "🚀 *Pronto para Turbinar Seus Ganhos?*\n\n"
        "Venha fazer parte do nosso time de vencedores e comece a ver os resultados que sempre desejou. "
        "Aproveite a oportunidade e garanta sua vaga agora!"
    )
    
    # 3. Botão ADQUIRA JÁ (Inline Keyboard)
    markup = telebot.types.InlineKeyboardMarkup()
    btn_adquirir = telebot.types.InlineKeyboardButton("💎 ADQUIRA JÁ 💎", callback_data=f"ADQUIRA_JA_{user_id}")
    markup.add(btn_adquirir)
    
    bot.send_message(chat_id, cta_message, parse_mode='Markdown', reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith('ADQUIRA_JA_') or call.data.startswith('RENOVAR_'))
def handle_adquire_renew_button(call):
    """
    Manipula o clique em ADQUIRA JÁ ou RENOVAR, transformando o botão nas opções de pagamento.
    """
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    # Apaga a mensagem original
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except Exception as e:
        # Se não conseguir apagar, apenas edita para a próxima etapa
        logging.warning(f"Não foi possível apagar a mensagem: {e}")

    # Novo teclado com opções de pagamento
    markup = telebot.types.InlineKeyboardMarkup()
    
    # O external_reference é crucial para identificar o usuário no Webhook do MP
    external_reference = f"user_{user_id}_{datetime.datetime.now().timestamp()}"
    
    # 1. Botão PIX
    # O callback_data deve levar todas as informações necessárias
    pix_data = json.dumps({'action': 'PIX', 'ref': external_reference})
    btn_pix = telebot.types.InlineKeyboardButton("💰 PIX (R$ 397,00)", callback_data=pix_data)

    # 2. Botão Cartão de Crédito
    # Para Cartão, vamos gerar um link de Checkout Pro ou simplesmente informar o usuário.
    # Gerar checkout de cartão transparente é muito complexo para o bot. Usaremos o link do Checkout Pro.
    # Para o propósito deste exemplo, usaremos o link de pagamento Pix mais adiante.
    btn_cartao = telebot.types.InlineKeyboardButton("💳 CARTÃO DE CRÉDITO", callback_data="CARTAO")
    
    markup.row(btn_pix)
    markup.row(btn_cartao)
    
    message_text = "✅ *Escolha o método de pagamento*:"
    bot.send_message(chat_id, message_text, parse_mode='Markdown', reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith('{"action": "PIX"'))
def handle_pix_payment(call):
    """
    Manipula o clique no PIX, gera a cobrança via Mercado Pago API e envia QR Code e Copia e Cola.
    """
    data = json.loads(call.data)
    ref = data['ref']
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    try:
        # Edita a mensagem para mostrar "Aguardando..."
        bot.edit_message_text("⏳ *Gerando Pix... Aguarde um momento.*", 
                              chat_id, call.message.message_id, parse_mode='Markdown')
        
        # --- CRIAÇÃO DO PAGAMENTO PIX ---
        payment_data = {
            "transaction_amount": VALOR_GRUPO,
            "description": "Acesso VIP Na Mira do Green (30 dias)",
            "payment_method_id": "pix",
            "payer": {
                "email": f"user_{user_id}@telegram.com", # Email fictício, mas necessário para a API
                "first_name": call.from_user.first_name,
                "last_name": call.from_user.last_name if call.from_user.last_name else "Telegram User",
            },
            # external_reference é fundamental para rastrear a compra
            "external_reference": ref,
            # URL de notificação Webhook (ajuste o domínio de acordo com sua hospedagem)
            "notification_url": "https://SEU_DOMINIO.com/mercadopago_webhook", 
            "metadata": {
                "telegram_user_id": user_id,
                "telegram_chat_id": chat_id
            }
        }

        # Gera o pagamento
        payment_response = mp_sdk.payment().create(payment_data)
        
        if payment_response and payment_response['status'] == 201:
            payment_info = payment_response['response']
            
            # Dados do Pix
            qr_code = payment_info['point_of_interaction']['transaction_data']['qr_code_base64']
            pix_copia_cola = payment_info['point_of_interaction']['transaction_data']['qr_code'] # Este é o código Copia e Cola
            
            # Mensagem de Pix
            pix_message = (
                f"💰 *Pagamento Pix - R$ {VALOR_GRUPO:,.2f}*\n\n"
                "Siga os passos para finalizar a compra:\n"
                "1. Abra o app do seu banco.\n"
                "2. Escolha a opção Pix Copia e Cola.\n"
                "3. Use o código abaixo:\n\n"
                f"```\n{pix_copia_cola}\n```\n\n"
                "Ou escaneie o QR Code anexo (imagem base64). *Seu acesso será liberado automaticamente após a confirmação!*"
            )
            
            # Envia a imagem do QR Code (Base64)
            # Nota: O Telegram pode ter problemas em exibir a imagem base64 diretamente. 
            # É mais robusto enviar o código Copia e Cola e a mensagem.
            
            bot.send_message(chat_id, pix_message, parse_mode='Markdown')
            
            # Log para acompanhamento
            logging.info(f"Pix gerado para o usuário {user_id}. Ref: {ref}")

        else:
            error_message = payment_response['response'].get('message', 'Erro desconhecido na geração do Pix.')
            bot.send_message(chat_id, f"❌ Erro ao gerar o Pix: {error_message}. Tente novamente mais tarde.")

    except Exception as e:
        bot.send_message(chat_id, "❌ Desculpe, ocorreu um erro interno. Tente novamente.")
        logging.error(f"Erro no handle_pix_payment: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'CARTAO')
def handle_card_option(call):
    """
    Apenas informa que o método de cartão exige o Checkout Pro.
    """
    chat_id = call.message.chat.id
    
    # Edita a mensagem original
    try:
        bot.edit_message_text("Aguardando confirmação...", chat_id, call.message.message_id)
    except:
        pass # Ignora erro se a mensagem já foi apagada ou editada
        
    card_message = (
        "💳 *Opção Cartão de Crédito*\n\n"
        "Para a opção de cartão, você será direcionado ao Checkout Pro do Mercado Pago para inserir os dados com segurança. "
        "Esta função requer a criação de uma preferência de pagamento no Mercado Pago. Por enquanto, sugerimos o PIX para acesso instantâneo!"
    )
    bot.send_message(chat_id, card_message, parse_mode='Markdown')


def grant_access(user_id, chat_id, payment_id):
    """
    Executa a lógica final: salva a assinatura e envia o link único.
    """
    # 1. Salva a assinatura e data de expiração no Firestore
    if save_subscription(user_id, chat_id, payment_id):
        # 2. Cria o link de convite único
        invite_link = create_unique_invite_link(ID_GRUPO_VIP, user_id)
        
        # 3. Envia a mensagem de sucesso e o link único
        success_message = (
            "🎉 *Pagamento Aprovado! Parabéns!* 🎉\n\n"
            "Seu acesso ao grupo premium foi liberado. Use o link abaixo *imediatamente*. "
            "Ele é *único* e só pode ser usado por *uma pessoa* para entrar no grupo:\n\n"
            f"🔗 {invite_link}\n\n"
            "⚠️ *Atenção:* Após o uso, o link expira. Salve o link do grupo para evitar perdas de acesso."
        )
        bot.send_message(chat_id, success_message, parse_mode='Markdown')
        logging.info(f"Acesso concedido e link enviado para o usuário {user_id}.")
    else:
        bot.send_message(chat_id, "❌ Erro interno: Seu pagamento foi aprovado, mas não conseguimos registrar seu acesso. Por favor, contate o suporte.")


# --- 5. SERVIDOR WEBHOOK FLASK (PARA MERCADO PAGO) ---

app = Flask(__name__)

@app.route("/mercadopago_webhook", methods=['POST'])
def mercadopago_webhook():
    """
    Endpoint que recebe as notificações (Webhooks) do Mercado Pago.
    """
    try:
        data = request.json
        topic = data.get('topic')
        resource_url = data.get('resource')
        
        # 1. Validação de Assinatura (Segurança)
        # O Mercado Pago envia o header 'x-signature'. 
        # Para simplificar o exemplo, vamos apenas verificar a estrutura do POST, 
        # mas em produção, você DEVE validar a assinatura.
        
        if topic == 'payment' and resource_url:
            # 2. Obter detalhes completos do pagamento na API
            payment_id = resource_url.split('/')[-1]
            payment_response = mp_sdk.payment().get(payment_id)
            
            if payment_response and payment_response['status'] == 200:
                payment_details = payment_response['response']
                
                # 3. Processar Pagamento Aprovado
                if payment_details.get('status') == 'approved':
                    logging.info(f"Webhook recebido: Pagamento {payment_id} APROVADO.")
                    
                    # Recuperar a referência externa para identificar o usuário
                    external_ref = payment_details.get('external_reference')
                    if not external_ref:
                        logging.error(f"Pagamento {payment_id} aprovado, mas sem external_reference.")
                        return jsonify({"status": "error", "message": "Missing reference"}), 200

                    # O user_id é a primeira parte da external_reference (ex: user_123456789_timestamp)
                    telegram_user_id = int(external_ref.split('_')[1])
                    
                    # Tenta recuperar o chat_id do metadata ou do Firestore se precisar
                    # Usaremos o chat_id que foi salvo no metadata.
                    telegram_chat_id = payment_details.get('metadata', {}).get('telegram_chat_id', None)
                    
                    if not telegram_chat_id:
                        # Se não tiver o chat_id, o bot não pode enviar a mensagem!
                        logging.error(f"Chat ID não encontrado para o usuário {telegram_user_id}. Não foi possível enviar o link.")
                        return jsonify({"status": "warning", "message": "Chat ID not found"}), 200

                    grant_access(telegram_user_id, telegram_chat_id, payment_id)

                elif payment_details.get('status') == 'rejected':
                    logging.warning(f"Pagamento {payment_id} REJEITADO.")
                    # Opcional: Enviar mensagem de rejeição ao usuário.
                    pass
                else:
                    logging.info(f"Pagamento {payment_id} com status {payment_details.get('status')}. Ignorando.")

        # O Mercado Pago espera um HTTP 200 OK para confirmar o recebimento do webhook.
        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logging.error(f"Erro no processamento do Webhook: {e}")
        return jsonify({"status": "internal_error"}), 500

@app.route("/cron/check_expirations", methods=['GET'])
def run_cron_check():
    """
    Endpoint para ser chamado pelo seu serviço de agendamento (cron) externo.
    """
    check_and_remove_expired_users()
    return jsonify({"status": "success", "message": "Verificação de expiração concluída."}), 200

@app.route("/")
def index():
    """Endpoint de saúde para verificar se o bot está rodando."""
    return "Bot de Pagamento Telegram - Funcionando via Webhook!"

# --- 6. INICIALIZAÇÃO DO FLASK E DO BOT ---

if __name__ == "__main__":
    # Remove o método get_updates do bot, pois estamos usando Webhook
    # bot.remove_webhook()
    
    # O telebot suporta o modo Webhook usando Flask.
    # Esta parte do código deve ser ajustada para o seu ambiente de hospedagem.
    # Exemplo simples para rodar localmente, mas a hospedagem usará o WSGI.
    print("Bot em execução no modo Webhook. Não use long polling.")
    # No ambiente de produção (Vercel, Fly.io), o WSGI fará o run, 
    # mas esta linha é mantida para rodar localmente ou indicar o ponto de entrada.
    # app.run(host="0.0.0.0", port=80) 
    # Em ambientes de produção/servless, você só precisa garantir que o 'app' Flask
    # esteja acessível para o servidor WSGI (como Gunicorn ou o runtime da plataforma).
    pass