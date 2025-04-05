import os
import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)
from pymongo import MongoClient
import random

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- MongoDB Setup ---
MONGO_URI = os.getenv("MONGO_URI", "your_mongo_uri")
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

def get_keyboard(board):
    buttons = []
    for i in range(0, 9, 3):
        row = []
        for j in range(3):
            idx = i + j
            text = board[idx] if board[idx] != ' ' else str(idx + 1)
            row.append(InlineKeyboardButton(text=text, callback_data=str(idx)))
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

async def timeout_check(chat_id, app):
    await asyncio.sleep(TIMEOUT)
    game = games.get(chat_id)
    if game and game['active']:
        if datetime.now() - game['last_move_time'] > timedelta(seconds=TIMEOUT):
            current = game['players'][game['turn']]
            await app.bot.send_message(
                chat_id,
                f"{current.mention_html()} took too long! Game ended.",
                parse_mode="HTML"
            )
            games.pop(chat_id)

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to Tic Tac Toe! Use /join or /single to start.")

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = games.setdefault(chat_id, {
        'players': [],
        'board': [' '] * 9,
        'turn': 0,
        'active': False,
        'last_move_time': datetime.now(),
        'vs_bot': False
    })

    if user in game['players']:
        await update.message.reply_text("You already joined.")
    elif len(game['players']) < 2:
        game['players'].append(user)
        await update.message.reply_text(f"{user.first_name} joined the game.")
        if len(game['players']) == 2:
            await update.message.reply_text("Two players joined. Use /new to start.")
    else:
        await update.message.reply_text("Already have two players.")

async def single(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    games[chat_id] = {
        'players': [user, 'BOT'],
        'board': [' '] * 9,
        'turn': 0,
        'active': True,
        'last_move_time': datetime.now(),
        'vs_bot': True
    }
    await update.message.reply_text(
        f"{user.mention_html()} vs Computer!\nYour turn.",
        reply_markup=get_keyboard([' '] * 9),
        parse_mode="HTML"
    )

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = games.get(chat_id)
    if not game or len(game['players']) != 2:
        return await update.message.reply_text("Need 2 players to start.")
    game['board'] = [' '] * 9
    game['turn'] = 0
    game['active'] = True
    game['last_move_time'] = datetime.now()
    await update.message.reply_text(
        f"Game Started!\n{game['players'][0].mention_html()} vs {game['players'][1].mention_html()}",
        reply_markup=get_keyboard(game['board']),
        parse_mode="HTML"
    )
    asyncio.create_task(timeout_check(chat_id, context.application))

async def end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    games.pop(chat_id, None)
    await update.message.reply_text("Game ended.")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in games:
        games[chat_id]['board'] = [' '] * 9
        games[chat_id]['turn'] = 0
        await update.message.reply_text("Board reset.", reply_markup=get_keyboard([' '] * 9))

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = games.get(chat_id)
    if game and game['active']:
        await update.message.reply_text("Current Game:", reply_markup=get_keyboard(game['board']))
    else:
        await update.message.reply_text("No active game.")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top = stats_col.find().sort([("win", -1)]).limit(10)
    text = "\n".join([f"{doc['user_id']}: {doc.get('win',0)}W-{doc.get('loss',0)}L-{doc.get('draw',0)}D" for doc in top])
    await update.message.reply_text("Leaderboard:\n" + text)

async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    stats = get_stats(user.id)
    await update.message.reply_text(
        f"Your stats:\nWins: {stats.get('win', 0)}\nLosses: {stats.get('loss', 0)}\nDraws: {stats.get('draw', 0)}"
    )

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    hist = get_history(chat_id)
    if hist:
        await update.message.reply_text("Game History:\n" + "\n".join(hist))
    else:
        await update.message.reply_text("No history yet.")

# --- Callback Handler for Taps ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    user = query.from_user
    pos = int(query.data)

    game = games.get(chat_id)
    if not game or not game['active']:
        return

    if game['players'][game['turn']] != user:
        return

    if game['board'][pos] != ' ':
        return

    emoji = DEFAULT_EMOJIS[game['turn']]
    game['board'][pos] = emoji
    game['last_move_time'] = datetime.now()

    if check_winner(game['board']):
        winner = user
        loser = game['players'][1 - game['turn']]
        update_stats(winner.id, 'win')
        if loser != 'BOT':
            update_stats(loser.id, 'loss')
        save_history(chat_id, f"{winner.first_name} defeated {loser if loser=='BOT' else loser.first_name}")
        games.pop(chat_id, None)
        return await query.edit_message_text(
            f"{get_keyboard(game['board']).to_dict()['inline_keyboard'][0][0]['text']}...\n\n🏆 {winner.mention_html()} wins!",
            parse_mode="HTML"
        )

    if is_draw(game['board']):
        for player in game['players']:
            if player != 'BOT':
                update_stats(player.id, 'draw')
        save_history(chat_id, "Draw")
        games.pop(chat_id, None)
        return await query.edit_message_text("Draw!", parse_mode="HTML")

    game['turn'] = 1 - game['turn']
    await query.edit_message_reply_markup(reply_markup=get_keyboard(game['board']))

    # Bot move
    if game['vs_bot'] and game['players'][game['turn']] == 'BOT':
        await asyncio.sleep(1)
        available = [i for i, cell in enumerate(game['board']) if cell == ' ']
        bot_pos = random.choice(available)
        game['board'][bot_pos] = DEFAULT_EMOJIS[1]
        game['last_move_time'] = datetime.now()

        if check_winner(game['board']):
            update_stats(user.id, 'loss')
            save_history(chat_id, f"Computer defeated {user.first_name}")
            games.pop(chat_id, None)
            return await context.bot.edit_message_text(
                f"{get_keyboard(game['board']).to_dict()['inline_keyboard'][0][0]['text']}...\n\n🏆 Computer wins!",
                chat_id=chat_id,
                message_id=query.message.message_id,
                parse_mode="HTML"
            )

        if is_draw(game['board']):
            update_stats(user.id, 'draw')
            save_history(chat_id, "Draw with Computer")
            games.pop(chat_id, None)
            return await context.bot.edit_message_text(
                "Draw!", chat_id=chat_id, message_id=query.message.message_id
            )

        game['turn'] = 0
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=query.message.message_id,
            reply_markup=get_keyboard(game['board'])
        )

# --- Main ---
def main():
    token = os.getenv("BOT_TOKEN", "7801621884:AAHmK4MjTuEanUftEhQJezANh0fiF1cLGTY")
    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("new", new_game))
    app.add_handler(CommandHandler("end", end))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("mystats", mystats))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("single", single))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()