# Imagem oficial Python
FROM python:3.11-slim

# Diretório de trabalho
WORKDIR /app

# Copia o requirements.txt
COPY requirements.txt .

# Atualiza pip e instala dependências
RUN python -m pip install --upgrade pip
RUN python -m pip install --no-cache-dir -r requirements.txt

# Copia todo o código do bot
COPY . .

# Define variável de ambiente padrão para Fly
ENV PORT 8080

# Comando para iniciar o bot
CMD ["python", "bot.py"]