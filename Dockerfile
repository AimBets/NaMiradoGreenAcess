# Usando imagem oficial Python
FROM python:3.12-slim

# Diretório de trabalho
WORKDIR /app

# Copiando arquivos
COPY bot.py ./
COPY requirements.txt ./

# Instalando dependências
RUN pip install --no-cache-dir -r requirements.txt

# Variáveis de ambiente (podem ser sobrescritas no Fly.io)
ENV BOT_TOKEN="SEU_TOKEN_AQUI"
ENV MP_ACCESS_TOKEN="SEU_TOKEN_MP"
ENV VALOR_GRUPO="397.0"
ENV SEGREDO_WEBHOOK="SEU_SEGREDO"
ENV ID_GRUPO_VIP="-1002915685276"
ENV FIREBASE_CONFIG=""

# Expõe porta para o Fly.io
EXPOSE 8080

# Comando padrão para iniciar o bot com Gunicorn (recomendado no Fly.io)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "bot:app"]
