import os
import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes
)
from pymongo import MongoClient

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- MongoDB Setup ---
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://Ishuxd:ishusomuxd@ishuxd.78ljc.mongodb.net/?retryWrites=true&w=majority&appName=Ishuxd")
client = MongoClient(MONGO_URI)
db = client["tictactoe_db"]
stats_col = db["user_stats"]
history_col = db["game_history"]

# --- In-Memory Game Storage ---
games = {}

# --- Constants ---
DEFAULT_EMOJIS = ['❌', '⭕']
TIMEOUT = 60

# --- Utility Functions ---
def build_keyboard(board):
    keyboard = []
    for i in range(0, 9, 3):
        row = []
        for j in range(3):
            idx = i + j
            text = board[idx]
            if text == ' ':
                text = '⬜'
            row.append(InlineKeyboardButton(text, callback_data=str(idx)))
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

def check_winner(board):
    win_pos = [
        [0, 1, 2], [3, 4, 5], [6, 7, 8],
        [0, 3, 6], [1, 4, 7], [2, 5, 8],
        [0, 4, 8], [2, 4, 6]
    ]
    for a, b, c in win_pos:
        if board[a] == board[b] == board[c] and board[a] != ' ':
            return True
    return False

def is_draw(board):
    return ' ' not in board

async def timeout_check(group_id, app):
    await asyncio.sleep(TIMEOUT)
    game = games.get(group_id)
    if game and game['active']:
        if datetime.now() - game['last_move_time'] > timedelta(seconds=TIMEOUT):
            user = game['players'][game['turn']]
            await app.bot.send_message(
                group_id,
                f"{user.mention_html()} took too long! Game ended.",
                parse_mode="HTML"
            )
            games.pop(group_id, None)

def update_stats(user_id, result):
    stats_col.update_one(
        {'user_id': user_id},
        {'$inc': {result: 1}},
        upsert=True
    )

def get_stats(user_id):
    stats = stats_col.find_one({'user_id': user_id})
    return stats or {'win': 0, 'loss': 0, 'draw': 0}

def save_history(chat_id, record):
    history_col.update_one(
        {'chat_id': chat_id},
        {'$push': {'history': record}},
        upsert=True
    )

def get_history(chat_id):
    doc = history_col.find_one({'chat_id': chat_id})
    return doc['history'] if doc and 'history' in doc else []

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to Tic Tac Toe Bot! Use /join to participate.")

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = games.setdefault(chat_id, {
        'players': [],
        'board': [' '] * 9,
        'turn': 0,
        'active': False,
        'last_move_time': datetime.now()
    })

    if user in game['players']:
        await update.message.reply_text("You already joined.")
    elif len(game['players']) < 2:
        game['players'].append(user)
        await update.message.reply_text(f"{user.first_name} joined the game.")
        if len(game['players']) == 2:
            await update.message.reply_text("2 players joined! Use /new to start the game.")
    else:
        await update.message.reply_text("Game already has 2 players.")

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = games.get(chat_id)
    if not game or len(game['players']) != 2:
        await update.message.reply_text("Need 2 players to start. Use /join.")
        return
    game['board'] = [' '] * 9
    game['turn'] = 0
    game['active'] = True
    game['last_move_time'] = datetime.now()

    player1 = game['players'][0]
    player2 = game['players'][1]
    await update.message.reply_text(
        f"Game started!\n{player1.mention_html()} vs {player2.mention_html()}\n{player1.mention_html()}'s turn.",
        parse_mode="HTML",
        reply_markup=build_keyboard(game['board'])
    )
    asyncio.create_task(timeout_check(chat_id, context.application))

async def end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    games