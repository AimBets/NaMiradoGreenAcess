# Imagem oficial Python
FROM python:3.11-slim

# Evita problemas de locale
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8

# Diretório de trabalho
WORKDIR /app

# Copia requirements.txt
COPY requirements.txt .

# Atualiza pip e instala dependências
RUN python -m pip install --upgrade pip
RUN python -m pip install --no-cache-dir -r requirements.txt

# Copia o código do bot
COPY . .

# Expõe a porta que o Flask vai usar
EXPOSE 8080

# Comando para rodar o Flask em produção (bind em 0.0.0.0 e porta 8080)
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8080", "bot:app"]
