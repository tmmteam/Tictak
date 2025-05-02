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

def render_board(chat_id):
    game = games[chat_id]
    board = game['board']
    keyboard = []
    for i in range(0, 9, 3):
        row = [
            InlineKeyboardButton(
                text=board[j] if board[j] != ' ' else '⬜',
                callback_data=str(j)
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

def update_stats(user_id, result, username=None):
    update_data = {'$inc': {result: 1}}
    if username:
        update_data['$set'] = {'username': username}
    stats_col.update_one({'user_id': user_id}, update_data, upsert=True)

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
        caption="Ready to put your skills to the test? Challenge your friends and climb the leaderboard! 🚀"
    )

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
    await update.message.reply_text(
        f"Game started!\n{game['players'][0].mention_html()} vs {game['players'][1].mention_html()}\n\n{game['players'][0].mention_html()}'s turn.",
        reply_markup=render_board(chat_id),
        parse_mode="HTML"
    )
    asyncio.create_task(timeout_check(chat_id, context.application))

async def end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    games.pop(chat_id, None)
    await update.message.reply_text("Game ended and data cleared.")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in games:
        games[chat_id]['board'] = [' '] * 9
        games[chat_id]['turn'] = 0
        await update.message.reply_text("Board reset.", reply_markup=render_board(chat_id))

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = games.get(chat_id)
    if game and game['active']:
        await update.message.reply_text(f"Current board:\n{format_board(game['board'])}")
    else:
        await update.message.reply_text("No active game.")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("Today🗓", callback_data="leaderboard_today")],
        [InlineKeyboardButton("Global🌎", callback_data="leaderboard_global")],
        [InlineKeyboardButton("Overall📈", callback_data="leaderboard_overall")]
    ]
    await update.message.reply_text(
        "Choose a leaderboard:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_leaderboard_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    button = query.data

    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)

    if button == "leaderboard_today":
        stats = stats_col.find({"last_win": {"$gte": today_start}}).sort("win", -1).limit(10)
        title = "Today's Top Players"
    elif button == "leaderboard_global":
        stats = stats_col.find({"last_win": {"$gte": today_start}}).sort("win", -1)
        title = "Global Leaderboard (Today)"
    else:
        stats = stats_col.find().sort("win", -1).limit(10)
        title = "Overall Leaderboard"

    lines = []
    for doc in stats:
        username = doc.get("username", str(doc["user_id"]))
        wins = doc.get("win", 0)
        losses = doc.get("loss", 0)
        draws = doc.get("draw", 0)
        lines.append(f"{username}: {wins}Win💫 - {losses}Loss💔 - {draws}Draw🤝")

    text = f"{title}:\n\n" + "\n".join(lines) if lines else "No data yet."
    await query.edit_message_text(text=text)

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

# --- Move Handler ---
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    game = games.get(chat_id)
    if not game or not game['active']:
        return

    user = update.effective_user
    if user != game['players'][game['turn']]:
        return

    pos = int(query.data)
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
        asyncio.create_task(update_stats(winner.id, 'win', winner.username))
        asyncio.create_task(update_stats(loser.id, 'loss', loser.username))
        asyncio.create_task(stats_col.update_one(
            {'user_id': winner.id},
            {'$set': {'last_win': datetime.utcnow()}}
        ))
        asyncio.create_task(save_history(chat_id, f"{winner.first_name} defeated {loser.first_name}"))
        games.pop(chat_id, None)
        return

    if is_draw(game['board']):
        await query.edit_message_text(
            text=f"{format_board(game['board'])}\n\nIt's a draw!"
        )
        for player in game['players']:
            asyncio.create_task(update_stats(player.id, 'draw', player.username))
        asyncio.create_task(save_history(chat_id, "Game ended in draw"))
        games.pop(chat_id, None)
        return

    game['turn'] = 1 - game['turn']
    await query.edit_message_reply_markup(reply_markup=render_board(chat_id))

# --- Main Function ---
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
    app.add_handler(CallbackQueryHandler(button_click, pattern="^[0-8]$"))
    app.add_handler(CallbackQueryHandler(handle_leaderboard_button, pattern="^leaderboard_"))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()