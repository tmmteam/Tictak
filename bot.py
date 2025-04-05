import os
import asyncio
import logging
from datetime import datetime, timedelta
from telegram import (
    Update, InputFile, InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
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
user_emojis = {}

# --- Constants ---
DEFAULT_EMOJIS = ['❌', '⭕']
WELCOME_IMG_PATH = 'https://envs.sh/rKZ.jpg'
TIMEOUT = 60

# --- Utility Functions ---
def format_board(board):
    return "\n".join([
        f"{board[0]} | {board[1]} | {board[2]}",
        f"{board[3]} | {board[4]} | {board[5]}",
        f"{board[6]} | {board[7]} | {board[8]}"
    ])

def render_board(chat_id, key):
    game = games[key]
    board = game['board']
    keyboard = []
    for i in range(0, 9, 3):
        row = [
            InlineKeyboardButton(
                text=board[j] if board[j] != ' ' else '⬜',
                callback_data=f"{key}:{j}"
            ) for j in range(i, i + 3)
        ]
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

async def timeout_check(key, app):
    await asyncio.sleep(TIMEOUT)
    game = games.get(key)
    if game and game['active']:
        if datetime.now() - game['last_move_time'] > timedelta(seconds=TIMEOUT):
            user = game['players'][game['turn']]
            await app.bot.send_message(
                game['chat_id'],
                f"{user.mention_html()} took too long! Game ended.",
                parse_mode="HTML"
            )
            games.pop(key, None)

def update_stats(user_id, username, result):
    stats_col.update_one(
        {'user_id': user_id},
        {
            '$inc': {result: 1},
            '$set': {'username': username, 'updated': datetime.utcnow()}
        },
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
    await update.message.reply_photo(
        photo=WELCOME_IMG_PATH,
        caption="Welcome to Tic Tac Toe Bot! Use /join to participate."
    )

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    key = f"{chat_id}_{user.id}"

    game = games.setdefault(key, {
        'chat_id': chat_id,
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
    for key, game in games.items():
        if game['chat_id'] == chat_id and len(game['players']) == 2:
            game['board'] = [' '] * 9
            game['turn'] = 0
            game['active'] = True
            game['last_move_time'] = datetime.now()
            await update.message.reply_text(
                f"Game started!\n{game['players'][0].mention_html()} vs {game['players'][1].mention_html()}\n\n{game['players'][0].mention_html()}'s turn.",
                reply_markup=render_board(chat_id, key),
                parse_mode="HTML"
            )
            asyncio.create_task(timeout_check(key, context.application))
            return
    await update.message.reply_text("No pair ready. Use /join.")

async def end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    to_remove = [key for key, g in games.items() if g['chat_id'] == chat_id]
    for key in to_remove:
        games.pop(key)
    await update.message.reply_text("Game(s) ended and data cleared.")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    for key, game in games.items():
        if game['chat_id'] == chat_id:
            game['board'] = [' '] * 9
            game['turn'] = 0
            await update.message.reply_text("Board reset.", reply_markup=render_board(chat_id, key))

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    for game in games.values():
        if game['chat_id'] == chat_id and game['active']:
            await update.message.reply_text(f"Current board:\n{format_board(game['board'])}")
            return
    await update.message.reply_text("No active game.")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Overall", callback_data="lb:overall"),
         InlineKeyboardButton("Today", callback_data="lb:today")]
    ])
    await update.message.reply_text("Select leaderboard type:", reply_markup=keyboard)

async def leaderboard_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(":")[1]

    if data == "overall":
        top = stats_col.find().sort([("win", -1)]).limit(10)
    else:
        since = datetime.utcnow() - timedelta(days=1)
        top = stats_col.find({"updated": {"$gte": since}}).sort([("win", -1)]).limit(10)

    text = "\n".join([
        f"{doc.get('username', doc['user_id'])}: {doc.get('win', 0)}W-{doc.get('loss', 0)}L-{doc.get('draw', 0)}D"
        for doc in top
    ]) or "No data found."
    await query.edit_message_text("Leaderboard:\n" + text)

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

async def set_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    if len(args) != 1:
        return await update.message.reply_text("Usage: /emoji [emoji]")
    user_emojis[user.id] = args[0]
    await update.message.reply_text(f"Your emoji is now: {args[0]}")

# --- Button Handler for Moves ---
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    payload = query.data.split(":")
    key, pos = payload[0], int(payload[1])
    game = games.get(key)

    if not game or not game['active']:
        return

    user = update.effective_user
    if user != game['players'][game['turn']]:
        return

    if game['board'][pos] != ' ':
        return

    emoji = user_emojis.get(user.id, DEFAULT_EMOJIS[game['turn']])
    game['board'][pos] = emoji
    game['last_move_time'] = datetime.now()

    if check_winner(game['board']):
        winner = user
        loser = game['players'][1 - game['turn']]
        await query.edit_message_text(
            text=f"{format_board(game['board'])}\n\nCongrats {winner.mention_html()}! You win!",
            parse_mode="HTML"
        )
        update_stats(winner.id, winner.username or winner.first_name, 'win')
        update_stats(loser.id, loser.username or loser.first_name, 'loss')
        save_history(game['chat_id'], f"{winner.first_name} defeated {loser.first_name}")
        games.pop(key, None)
        return

    if is_draw(game['board']):
        await query.edit_message_text(
            text=f"{format_board(game['board'])}\n\nIt's a draw!"
        )
        for player in game['players']:
            update_stats(player.id, player.username or player.first_name, 'draw')
        save_history(game['chat_id'], "Game ended in draw")
        games.pop(key, None)
        return

    game['turn'] = 1 - game['turn']
    await query.edit_message_reply_markup(
        reply_markup=render_board(game['chat_id'], key)
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
    app.add_handler(CommandHandler("emoji", set_emoji))
    app.add_handler(CallbackQueryHandler(button_click, pattern=r"^[\w\d_]+:\d$"))
    app.add_handler(CallbackQueryHandler(leaderboard_button, pattern=r"^lb:"))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()