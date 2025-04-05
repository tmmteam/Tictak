from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, ChatMemberHandler
import logging

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Game state
games = {}

# Replace this with your own hosted image
WELCOME_IMAGE_URL = 'https://your-welcome-image-url.com/welcome.jpg'

# Emojis
EMPTY = "⬜"
X = "❌"
O = "⭕"

# /start command
def start(update: Update, context: CallbackContext):
    chat = update.effective_chat
    if chat.type == "private":
        # Private message (DM)
        context.bot.send_photo(
            chat_id=chat.id,
            photo=WELCOME_IMAGE_URL,
            caption="Hi there! I'm your Tic Tac Toe bot.\nAdd me to a group and type /new to start a game!"
        )
    else:
        # Group message
        context.bot.send_photo(
            chat_id=chat.id,
            photo=WELCOME_IMAGE_URL,
            caption="Welcome to Tic Tac Bot! Use /new to start a new game in the group."
        )

# Welcome message when bot added to a group
def bot_added(update: Update, context: CallbackContext):
    member = update.my_chat_member
    if member.new_chat_member.status == "member":
        context.bot.send_photo(
            chat_id=member.chat.id,
            photo=WELCOME_IMAGE_URL,
            caption="Hello Group! I'm Tic Tac Bot.\nUse /new to begin a game!"
        )

# Start a new game
def new_game(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    games[chat_id] = {
        "players": [],
        "board": [EMPTY] * 9,
        "turn": None,
        "active": False
    }
    update.message.reply_text("Game created! Two players use /join to participate.")

# Join command
def join_game(update: Update, context: CallbackContext):
    user = update.effective_user
    chat_id = update.effective_chat.id
    game = games.get(chat_id)

    if not game:
        update.message.reply_text("No game found. Start a game with /new.")
        return

    if len(game["players"]) < 2 and user.id not in game["players"]:
        game["players"].append(user.id)
        update.message.reply_text(f"{user.first_name} joined the game!")

    if len(game["players"]) == 2:
        game["active"] = True
        game["turn"] = game["players"][0]
        update.message.reply_text("Both players joined! Let’s play!")
        send_board(update, context)

# Show board with buttons
def send_board(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    game = games[chat_id]
    board = game["board"]
    keyboard = []

    for i in range(0, 9, 3):
        row = [InlineKeyboardButton(board[i + j], callback_data=str(i + j)) for j in range(3)]
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.send_message(
        chat_id=chat_id,
        text=f"Turn: {'❌' if game['turn'] == game['players'][0] else '⭕'}",
        reply_markup=reply_markup
    )

# Handle button click
def button(update: Update, context: CallbackContext):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat.id
    game = games.get(chat_id)

    if not game or not game["active"]:
        query.answer()
        return

    if user.id != game["turn"]:
        query.answer("Not your turn!")
        return

    index = int(query.data)
    if game["board"][index] != EMPTY:
        query.answer("Already taken!")
        return

    symbol = X if user.id == game["players"][0] else O
    game["board"][index] = symbol

    winner = check_winner(game["board"])
    if winner:
        context.bot.send_message(
            chat_id=chat_id,
            text=f"Congrats {user.mention_html()}! You won!",
            parse_mode='HTML'
        )
        game["active"] = False
        return

    if EMPTY not in game["board"]:
        context.bot.send_message(chat_id=chat_id, text="It's a draw!")
        game["active"] = False
        return

    game["turn"] = game["players"][1] if user.id == game["players"][0] else game["players"][0]
    query.answer()
    send_board(update, context)

# Check for winner
def check_winner(board):
    win_combos = [(0,1,2), (3,4,5), (6,7,8),
                  (0,3,6), (1,4,7), (2,5,8),
                  (0,4,8), (2,4,6)]
    for a, b, c in win_combos:
        if board[a] == board[b] == board[c] != EMPTY:
            return board[a]
    return None

# End game
def end_game(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    if chat_id in games:
        del games[chat_id]
        update.message.reply_text("Game ended.")
    else:
        update.message.reply_text("No active game.")

# Main function
def main():
    TOKEN = 'YOUR_BOT_TOKEN_HERE'  # Replace with your bot token
    updater = Updater(TOKEN)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("new", new_game))
    dp.add_handler(CommandHandler("join", join_game))
    dp.add_handler(CommandHandler("end", end_game))
    dp.add_handler(CallbackQueryHandler(button))
    dp.add_handler(ChatMemberHandler(bot_added, chat_member_types=["my_chat_member"]))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()