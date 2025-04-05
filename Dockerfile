# Python base image
FROM python:3.10-slim

# Working directory inside container
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy rest of the bot files
COPY . .

# Set environment variable (optional)
# ENV BOT_TOKEN=your_token_here

# Run the bot
CMD ["python", "tictactoe_bot.py"]