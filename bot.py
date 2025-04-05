from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, ChatMemberHandler
from threading import Timer
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Game state per group
games = {}
leaderboard = {}

WELCOME_IMAGE_URL = "https://your-image-url.com/welcome.jpg"  # Replace with your image

# Default emojis
DEFAULT_EMOJIS = {0: "❌", 1: "⭕"}
EMPTY = "⬜"

# Timeout duration in seconds
TIMEOUT = 120


def start(update: Update, context: CallbackContext):
    chat = update.effective_chat
    if chat.type == "private":
        context.bot.send_photo(
            chat_id=chat.id,
            photo=WELCOME_IMAGE_URL,
            caption="Hi there! I'm your Tic Tac Toe bot. Add me to a group and type /new to start a game!"
        )
    else:
        context.bot.send_photo(
            chat_id=chat.id,
            photo=WELCOME_IMAGE_URL,
            caption="Welcome! Use /new to start a game."
        )


def bot_added(update: Update, context: CallbackContext):
    member = update.my_chat_member
    if member.new_chat_member.status == "member":
        context.bot.send_photo(
            chat_id=member.chat.id,
            photo=WELCOME_IMAGE_URL,
            caption="Hello Group! I'm Tic Tac Bot.\nUse /new to begin a game!"
        )


def new_game(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    games[chat_id] = {
        "players": [],
        "board": [EMPTY] * 9,
        "turn": None,
        "active": False,
        "emojis": DEFAULT_EMOJIS.copy(),
        "timeout": None,
        "last_move_time": time.time()
    }
    update.message.reply_text("Game created! Two players use /join to play.")


def join_game(update: Update, context: CallbackContext):
    user = update.effective_user
    chat_id = update.effective_chat.id
    game = games.get(chat_id)

    if not game:
        update.message.reply_text("Start a game first using /new.")
        return

    if user.id in game["players"]:
        update.message.reply_text("You're already in the game.")
        return

    if len(game["players"]) >= 2:
        update.message.reply_text("Two players already joined.")
        return

    game["players"].append(user.id)
    update.message.reply_text(f"{user.first_name} joined!")

    if len(game["players"]) == 2:
        game["turn"] = game["players"][0]
        game["active"] = True
        game["last_move_time"] = time.time()
        update.message.reply_text("Game started!")
        send_board(update, context)
        schedule_timeout(chat_id, context)


def send_board(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    game = games[chat_id]
    board = game["board"]
    keyboard = []

    for i in range(0, 9, 3):
        row = [InlineKeyboardButton(board[i + j], callback_data=str(i + j)) for j in range(3)]
        keyboard.append(row)

    symbol = game["emojis"][0] if game["turn"] == game["players"][0] else game["emojis"][1]
    reply_markup = InlineKeyboardMarkup(keyboard)

    context.bot.send_message(
        chat_id=chat_id,
        text=f"Turn: {symbol}",
        reply_markup=reply_markup
    )


def button(update: Update, context: CallbackContext):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat.id
    game = games.get(chat_id)

    if not game or not game["active"]:
        query.answer("Game not active.")
        return

    if user.id != game["turn"]:
        query.answer("Not your turn.")
        return

    index = int(query.data)
    if game["board"][index] != EMPTY:
        query.answer("Already taken.")
        return

    symbol = game["emojis"][0] if user.id == game["players"][0] else game["emojis"][1]
    game["board"][index] = symbol
    game["last_move_time"] = time.time()

    winner = check_winner(game["board"])
    if winner:
        context.bot.send_message(
            chat_id=chat_id,
            text=f"Congrats {user.mention_html()}! You won!",
            parse_mode='HTML'
        )
        leaderboard[user.id] = leaderboard.get(user.id, 0) + 1
        game["active"] = False
        return

    if EMPTY not in game["board"]:
        context.bot.send_message(
            chat_id=chat_id,
            text=f"It's a draw between {context.bot.get_chat_member(chat_id, game['players'][0]).user.first_name} and {context.bot.get_chat_member(chat_id, game['players'][1]).user.first_name}!"
        )
        game["active"] = False
        return

    game["turn"] = game["players"][1] if user.id == game["players"][0] else game["players"][0]
    query.answer()
    send_board(update, context)
    schedule_timeout(chat_id, context)


def check_winner(b):
    combos = [(0,1,2), (3,4,5), (6,7,8),
              (0,3,6), (1,4,7), (2,5,8),
              (0,4,8), (2,4,6)]
    for a,b,c in combos:
        if games and games[next(iter(games))]["board"][a] == games[next(iter(games))]["board"][b] == games[next(iter(games))]["board"][c] != EMPTY:
            return True
    return False


def end_game(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    if chat_id in games:
        games.pop(chat_id)
        update.message.reply_text("Game ended.")
    else:
        update.message.reply_text("No game running.")


def reset_board(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    game = games.get(chat_id)
    if not game:
        update.message.reply_text("No game found.")
        return

    game["board"] = [EMPTY] * 9
    game["last_move_time"] = time.time()
    update.message.reply_text("Board reset!")
    send_board(update, context)


def game_status(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    game = games.get(chat_id)
    if not game or not game["active"]:
        update.message.reply_text("No active game.")
        return

    p1 = context.bot.get_chat_member(chat_id, game["players"][0]).user.first_name
    p2 = context.bot.get_chat_member(chat_id, game["players"][1]).user.first_name
    turn = p1 if game["turn"] == game["players"][0] else p2
    update.message.reply_text(f"{p1} vs {p2}\nCurrent turn: {turn}")


def emoji_command(update: Update, context: CallbackContext):
    user = update.effective_user
    chat_id = update.effective_chat.id
    game = games.get(chat_id)
    if not game or user.id not in game["players"]:
        update.message.reply_text("You must join a game first.")
        return

    if len(context.args) != 1:
        update.message.reply_text("Usage: /emoji <emoji>")
        return

    emoji = context.args[0]
    index = game["players"].index(user.id)
    game["emojis"][index] = emoji
    update.message.reply_text(f"Your emoji has been set to {emoji}!")


def show_leaderboard(update: Update, context: CallbackContext):
    if not leaderboard:
        update.message.reply_text("Leaderboard is empty.")
        return

    lines = ["🏆 Leaderboard:"]
    for user_id, score in sorted(leaderboard.items(), key=lambda x: x[1], reverse=True):
        try:
            user = context.bot.get_chat_member(update.effective_chat.id, user_id).user
            lines.append(f"{user.first_name}: {score}")
        except:
            lines.append(f"User {user_id}: {score}")
    update.message.reply_text("\n".join(lines))


def schedule_timeout(chat_id, context: CallbackContext):
    def timeout_check():
        game = games.get(chat_id)
        if game and game["active"] and (time.time() - game["last_move_time"] > TIMEOUT):
            context.bot.send_message(chat_id=chat_id, text="Game ended due to inactivity.")
            games.pop(chat_id, None)

    timer = Timer(TIMEOUT + 1, timeout_check)
    games[chat_id]["timeout"] = timer
    timer.start()


def main():
    TOKEN = 'YOUR_BOT_TOKEN_HERE'
    updater = Updater(TOKEN)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(ChatMemberHandler(bot_added, chat_member_types=["my_chat_member"]))
    dp.add_handler(CommandHandler("new", new_game))
    dp.add_handler(CommandHandler("join", join_game))
    dp.add_handler(CommandHandler("end", end_game))
    dp.add_handler(CommandHandler("reset", reset_board))
    dp.add_handler(CommandHandler("status", game_status))
    dp.add_handler(CommandHandler("emoji", emoji_command))
    dp.add_handler(CommandHandler("leaderboard", show_leaderboard))
    dp.add_handler(CallbackQueryHandler(button))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()