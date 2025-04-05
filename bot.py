import os
import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler
)
from pymongo import MongoClient
import random

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- MongoDB Setup ---
MONGO_URI = os.getenv("MONGO_URI", "your-mongodb-uri")
client = MongoClient(MONGO_URI)
db = client["tictactoe_db"]
stats_col = db["user_stats"]
history_col = db["game_history"]

# --- In-Memory Game Storage ---
games = {}
single_games = {}
invites = {}

# --- Constants ---
DEFAULT_EMOJIS = ['❌', '⭕']
WELCOME_IMG_PATH = 'welcome.jpg'
TIMEOUT = 60

# --- Utility Functions ---

def get_board_markup(board, chat_id, is_single=False):
    prefix = "single" if is_single else "move"
    keyboard = []
    for i in range(3):
        row = []
        for j in range(3):
            idx = i * 3 + j
            row.append(InlineKeyboardButton(
                board[idx], callback_data=f"{prefix}:{chat_id}:{idx}"
            ))
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

def format_board(board):
    return f"{board[0]} | {board[1]} | {board[2]}\n{board[3]} | {board[4]} | {board[5]}\n{board[6]} | {board[7]} | {board[8]}"

def check_winner(board):
    win_pos = [
        [0, 1, 2], [3, 4, 5], [6, 7, 8],
        [0, 3, 6], [1, 4, 7], [2, 5, 8],
        [0, 4, 8], [2, 4, 6]
    ]
    for a, b, c in win_pos:
        if board[a] == board[b] == board[c] and board[a] != '⬜':
            return True
    return False

def is_draw(board):
    return '⬜' not in board

def update_stats(user_id, result):
    stats_col.update_one({'user_id': user_id}, {'$inc': {result: 1}}, upsert=True)

def save_history(chat_id, record):
    history_col.update_one({'chat_id': chat_id}, {'$push': {'history': record}}, upsert=True)

# --- Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Add to Group", url="https://t.me/your_bot_username?startgroup=true")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    with open(WELCOME_IMG_PATH, 'rb') as img:
        await update.message.reply_photo(photo=img, caption="Welcome to Tic Tac Toe Bot!", reply_markup=reply_markup)

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'group':
        return await update.message.reply_text("Game can only be played in groups.")
    
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = games.setdefault(chat_id, {
        'players': [],
        'board': ['⬜'] * 9,
        'turn': 0,
        'active': False,
        'last_move_time': datetime.now()
    })
    if user in game['players']:
        return await update.message.reply_text("You already joined.")
    if len(game['players']) < 2:
        game['players'].append(user)
        await update.message.reply_text(f"{user.first_name} joined.")
        if len(game['players']) == 2:
            await update.message.reply_text("Use /new to start game.")
    else:
        await update.message.reply_text("2 players already joined.")

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'group':
        return await update.message.reply_text("Game can only be played in groups.")
    
    chat_id = update.effective_chat.id
    game = games.get(chat_id)
    if not game or len(game['players']) != 2:
        return await update.message.reply_text("Need 2 players to start.")

    game['board'] = ['⬜'] * 9
    game['turn'] = 0
    game['active'] = True
    game['last_move_time'] = datetime.now()
    await update.message.reply_text(
        f"Game Started!\n{game['players'][0].mention_html()} vs {game['players'][1].mention_html()}\n{game['players'][0].mention_html()}'s turn.",
        parse_mode="HTML",
        reply_markup=get_board_markup(game['board'], chat_id)
    )

async def move_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(":")
    if len(data) != 3:
        return

    _, chat_id, pos = data
    chat_id = int(chat_id)
    pos = int(pos)
    game = games.get(chat_id)
    if not game or not game['active']:
        return

    user = query.from_user
    if user != game['players'][game['turn']]:
        return
    if game['board'][pos] != '⬜':
        return

    game['board'][pos] = DEFAULT_EMOJIS[game['turn']]
    game['last_move_time'] = datetime.now()

    if check_winner(game['board']):
        winner = user
        loser = game['players'][1 - game['turn']]
        await query.message.edit_text(
            f"{format_board(game['board'])}\n\nCongrats {winner.mention_html()}! You win! 🏆",
            parse_mode="HTML"
        )
        update_stats(winner.id, 'win')
        update_stats(loser.id, 'loss')
        save_history(chat_id, f"{winner.first_name} defeated {loser.first_name}")
        games.pop(chat_id, None)
        return

    if is_draw(game['board']):
        await query.message.edit_text(f"{format_board(game['board'])}\n\nIt's a draw!")
        for player in game['players']:
            update_stats(player.id, 'draw')
        save_history(chat_id, "Draw game")
        games.pop(chat_id, None)
        return

    game['turn'] = 1 - game['turn']
    await query.message.edit_text(
        f"{format_board(game['board'])}\n\n{game['players'][game['turn']].mention_html()}'s turn.",
        parse_mode="HTML",
        reply_markup=get_board_markup(game['board'], chat_id)
    )

# --- Player vs Computer ---

async def single(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    single_games[user_id] = {
        'board': ['⬜'] * 9,
        'turn': 0,  # 0 = player, 1 = bot
        'active': True
    }
    await update.message.reply_text(
        "Game started vs Computer!\nYour turn.",
        reply_markup=get_board_markup(single_games[user_id]['board'], user_id, is_single=True)
    )

async def single_move(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(":")
    if len(data) != 3:
        return

    _, user_id, pos = data
    user_id = int(user_id)
    pos = int(pos)

    game = single_games.get(user_id)
    if not game or not game['active']:
        return
    if game['turn'] != 0:
        return
    if game['board'][pos] != '⬜':
        return

    game['board'][pos] = DEFAULT_EMOJIS[0]
    if check_winner(game['board']):
        await query.message.edit_text(f"{format_board(game['board'])}\n\nYou win! 🏆")
        update_stats(user_id, 'win')
        game['active'] = False
        return

    if is_draw(game['board']):
        await query.message.edit_text(f"{format_board(game['board'])}\n\nIt's a draw!")
        update_stats(user_id, 'draw')
        game['active'] = False
        return

    # Bot move
    game['turn'] = 1
    empty = [i for i, cell in enumerate(game['board']) if cell == '⬜']
    bot_move = random.choice(empty)
    game['board'][bot_move] = DEFAULT_EMOJIS[1]

    if check_winner(game['board']):
        await query.message.edit_text(f"{format_board(game['board'])}\n\nComputer wins!")
        update_stats(user_id, 'loss')
        game['active'] = False
        return

    if is_draw(game['board']):
        await query.message.edit_text(f"{format_board(game['board'])}\n\nIt's a draw!")
        update_stats(user_id, 'draw')
        game['active'] = False
        return

    game['turn'] = 0
    await query.message.edit_text(
        f"{format_board(game['board'])}\n\nYour turn.",
        reply_markup=get_board_markup(game['board'], user_id, is_single=True)
    )

# --- Main ---

def main():
    token = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("new", new_game))
    app.add_handler(CommandHandler("single", single))

    app.add_handler(CallbackQueryHandler(move_callback, pattern=r"^move:"))
    app.add_handler(CallbackQueryHandler(single_move, pattern=r"^single:"))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()