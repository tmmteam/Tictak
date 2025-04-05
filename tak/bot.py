from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from pymongo import MongoClient

# Telegram Bot Token
TOKEN = '7313059877:AAEuRl43jQbDd9yIRcW-AnwKH8BWWHn9gXE'

# MongoDB Atlas Connection
mongo_uri = 'mongodb+srv://manoranjanhor43:somuxd@manoranjan.wsglmdq.mongodb.net/?retryWrites=true&w=majority&appName=Manoranjan'
client = MongoClient(mongo_uri)
db = client['tictactoe_bot']
games_col = db['games']
scores_col = db['scores']

# Telegram User IDs for the two players (replace these)
PLAYER1_ID = 123456789
PLAYER2_ID = 987654321

# Emoji for X and O
EMOJIS = {'X': '❌', 'O': '⭕'}

def get_board_markup(board):
    keyboard = []
    for i in range(3):
        row = []
        for j in range(3):
            cell = board[i][j]
            text = EMOJIS[cell] if cell in EMOJIS else ' '
            row.append(InlineKeyboardButton(text, callback_data=f"{i},{j}"))
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

def check_winner(board):
    for i in range(3):
        if board[i][0] == board[i][1] == board[i][2] != '':
            return board[i][0]
        if board[0][i] == board[1][i] == board[2][i] != '':
            return board[0][i]
    if board[0][0] == board[1][1] == board[2][2] != '':
        return board[0][0]
    if board[0][2] == board[1][1] == board[2][0] != '':
        return board[0][2]
    return None

def is_draw(board):
    return all(cell != '' for row in board for cell in row)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to Tic Tac Toe Bot!\n\n"
        "/new - Start a new game\n"
        "/end - End the current game\n"
        "/score - Show the score"
    )

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'group':
        await update.message.reply_text("This bot only works in group chats.")
        return

    user_id = update.effective_user.id
    if user_id not in (PLAYER1_ID, PLAYER2_ID):
        await update.message.reply_text("Only two assigned players can start a game.")
        return

    chat_id = update.effective_chat.id

    # Save new game state in MongoDB
    board = [['' for _ in range(3)] for _ in range(3)]
    games_col.update_one(
        {"chat_id": chat_id},
        {"$set": {
            "board": board,
            "turn": 'X',
            "players": {'X': PLAYER1_ID, 'O': PLAYER2_ID}
        }},
        upsert=True
    )

    await update.message.reply_text(
        f"New game started! {EMOJIS['X']} goes first.",
        reply_markup=get_board_markup(board)
    )

async def end_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'group':
        await update.message.reply_text("This bot only works in group chats.")
        return

    chat_id = update.effective_chat.id
    games_col.delete_one({'chat_id': chat_id})
    await update.message.reply_text("Game has been ended.")

async def show_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'group':
        await update.message.reply_text("This bot only works in group chats.")
        return

    chat_id = update.effective_chat.id
    score = scores_col.find_one({'chat_id': chat_id}) or {'X': 0, 'O': 0, 'Draw': 0}

    await update.message.reply_text(
        f"Scoreboard:\n"
        f"{EMOJIS['X']}: {score.get('X', 0)}\n"
        f"{EMOJIS['O']}: {score.get('O', 0)}\n"
        f"Draws: {score.get('Draw', 0)}"
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    user_id = query.from_user.id

    game = games_col.find_one({'chat_id': chat_id})
    if not game:
        return

    board = game['board']
    turn = game['turn']
    current_player_id = game['players'][turn]

    if user_id != current_player_id:
        await query.answer("It's not your turn!", show_alert=True)
        return

    i, j = map(int, query.data.split(','))
    if board[i][j] != '':
        return

    board[i][j] = turn
    winner = check_winner(board)

    if winner:
        scores_col.update_one(
            {'chat_id': chat_id},
            {'$inc': {winner: 1}},
            upsert=True
        )
        games_col.delete_one({'chat_id': chat_id})
        await query.edit_message_text(f"{EMOJIS[winner]} wins the game!")
        return

    if is_draw(board):
        scores_col.update_one(
            {'chat_id': chat_id},
            {'$inc': {'Draw': 1}},
            upsert=True
        )
        games_col.delete_one({'chat_id': chat_id})
        await query.edit_message_text("The game is a draw!")
        return

    # Switch turns and update game
    turn = 'O' if turn == 'X' else 'X'
    games_col.update_one(
        {'chat_id': chat_id},
        {'$set': {'board': board, 'turn': turn}}
    )

    await query.edit_message_text(
        f"{EMOJIS[turn]} turn",
        reply_markup=get_board_markup(board)
    )

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("new", new_game))
    app.add_handler(CommandHandler("end", end_game))
    app.add_handler(CommandHandler("score", show_score))
    app.add_handler(CallbackQueryHandler(button))
    print("Bot is running with MongoDB Atlas...")
    app.run_polling()
