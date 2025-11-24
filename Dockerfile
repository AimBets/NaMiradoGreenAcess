# Imagem oficial Python
FROM python:3.11-slim

# Diretório de trabalho
WORKDIR /app

# Instala dependências do sistema necessárias
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia o requirements.txt
COPY requirements.txt .

# Atualiza pip e instala dependências do Python
RUN python -m pip install --upgrade pip
RUN python -m pip install --no-cache-dir -r requirements.txt

# Copia todo o código do bot
COPY . .

# Comando padrão para rodar o bot
CMD ["python", "bot.py"]
