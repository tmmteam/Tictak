import json import os import asyncio import logging from telegram import Update, InputFile, User from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes) from datetime import datetime, timedelta

Enable logging

logging.basicConfig(level=logging.INFO) logger = logging.getLogger(name)

Game storage (multi-group support)

games = {} user_stats = {}

Emoji defaults

DEFAULT_EMOJIS = ['❌', '⭕'] user_emojis = {}

File paths

WELCOME_IMG_PATH = 'welcome.jpg' STATS_FILE = 'stats.json'

Timeout duration (seconds)

TIMEOUT = 60

--- Utility Functions ---

def format_board(board): return "\n".join([ f"{board[0]} | {board[1]} | {board[2]}", f"{board[3]} | {board[4]} | {board[5]}", f"{board[6]} | {board[7]} | {board[8]}" ])

def check_winner(board): win_pos = [[0,1,2],[3,4,5],[6,7,8], [0,3,6],[1,4,7],[2,5,8], [0,4,8],[2,4,6]] for a,b,c in win_pos: if board[a] == board[b] == board[c] and board[a] != ' ': return True return False

def is_draw(board): return ' ' not in board

async def timeout_check(group_id, app): await asyncio.sleep(TIMEOUT) game = games.get(group_id) if game and game['active']: if datetime.now() - game['last_move_time'] > timedelta(seconds=TIMEOUT): user = game['players'][game['turn']] await app.bot.send_message(group_id, f"{user.mention_html()} took too long! Game ended.", parse_mode="HTML") games.pop(group_id, None)

--- Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE): chat = update.effective_chat if chat.type == 'private' or chat.type == 'group': with open(WELCOME_IMG_PATH, 'rb') as img: await update.message.reply_photo(photo=InputFile(img), caption="Welcome to Tic Tac Toe Bot! Use /join to participate.")

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE): chat_id = update.effective_chat.id user = update.effective_user game = games.setdefault(chat_id, {'players': [], 'board': [' '] * 9, 'turn': 0, 'active': False, 'history': [], 'last_move_time': datetime.now()}) if user in game['players']: await update.message.reply_text("You already joined.") elif len(game['players']) < 2: game['players'].append(user) await update.message.reply_text(f"{user.first_name} joined the game.") if len(game['players']) == 2: await update.message.reply_text("2 players joined! Use /new to start the game.") else: await update.message.reply_text("Game already has 2 players.")

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE): chat_id = update.effective_chat.id game = games.get(chat_id) if not game or len(game['players']) != 2: await update.message.reply_text("Need 2 players to start. Use /join.") return game['board'] = [' '] * 9 game['turn'] = 0 game['active'] = True game['last_move_time'] = datetime.now() await update.message.reply_text(f"Game started!\n{game['players'][0].mention_html()} vs {game['players'][1].mention_html()}\n\n{format_board(game['board'])}\n\n{game['players'][0].mention_html()}'s turn.", parse_mode="HTML") asyncio.create_task(timeout_check(chat_id, context.application))

async def end(update: Update, context: ContextTypes.DEFAULT_TYPE): chat_id = update.effective_chat.id games.pop(chat_id, None) await update.message.reply_text("Game ended and data cleared.")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE): chat_id = update.effective_chat.id if chat_id in games: games[chat_id]['board'] = [' '] * 9 games[chat_id]['turn'] = 0 await update.message.reply_text("Board reset.")

async def move(update: Update, context: ContextTypes.DEFAULT_TYPE): chat_id = update.effective_chat.id game = games.get(chat_id) if not game or not game['active']: return user = update.effective_user if user != game['players'][game['turn']]: return try: pos = int(update.message.text.strip()) - 1 if not 0 <= pos <= 8 or game['board'][pos] != ' ': return await update.message.reply_text("Invalid move.") emoji = user_emojis.get(user.id, DEFAULT_EMOJIS[game['turn']]) game['board'][pos] = emoji game['last_move_time'] = datetime.now()

if check_winner(game['board']):
        winner = user
        loser = game['players'][1 - game['turn']]
        await update.message.reply_text(f"{format_board(game['board'])}\n\nCongrats {winner.mention_html()}! You win!", parse_mode="HTML")
        user_stats.setdefault(winner.id, {'win': 0, 'loss': 0, 'draw': 0})['win'] += 1
        user_stats.setdefault(loser.id, {'win': 0, 'loss': 0, 'draw': 0})['loss'] += 1
        game['history'].append(f"{winner.first_name} defeated {loser.first_name}")
        games.pop(chat_id, None)
        return

    if is_draw(game['board']):
        await update.message.reply_text(f"{format_board(game['board'])}\n\nIt's a draw!")
        for player in game['players']:
            user_stats.setdefault(player.id, {'win': 0, 'loss': 0, 'draw': 0})['draw'] += 1
        game['history'].append("Game ended in draw")
        games.pop(chat_id, None)
        return

    game['turn'] = 1 - game['turn']
    await update.message.reply_text(f"{format_board(game['board'])}\n\n{game['players'][game['turn']].mention_html()}'s turn.", parse_mode="HTML")
except:
    return

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE): chat_id = update.effective_chat.id game = games.get(chat_id) if game and game['active']: await update.message.reply_text(f"Current board:\n{format_board(game['board'])}") else: await update.message.reply_text("No active game.")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE): text = "\n".join([f"{uid}: {data['win']}W-{data['loss']}L-{data['draw']}D" for uid, data in user_stats.items()]) await update.message.reply_text("Leaderboard:\n" + text)

async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE): user = update.effective_user stats = user_stats.get(user.id, {'win': 0, 'loss': 0, 'draw': 0}) await update.message.reply_text(f"Your stats:\nWins: {stats['win']}\nLosses: {stats['loss']}\nDraws: {stats['draw']}")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE): chat_id = update.effective_chat.id game = games.get(chat_id) if game and game['history']: await update.message.reply_text("Game History:\n" + "\n".join(game['history'])) else: await update.message.reply_text("No history yet.")

async def set_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE): user = update.effective_user args = context.args if len(args) != 1: return await update.message.reply_text("Usage: /emoji [emoji]") user_emojis[user.id] = args[0] await update.message.reply_text(f"Your emoji is now: {args[0]}")

--- Main ---

def main(): token = "YOUR_BOT_TOKEN_HERE" app = ApplicationBuilder().token(token).build()

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
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, move))

print("Bot is running...")
app.run_polling()

if name == "main": main()

