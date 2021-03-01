import hashlib
from os import urandom
from random import choice
from re import findall
from time import sleep

import qrcode
from loguru import logger

# Telegram stuff
from telegram import (
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    KeyboardButton, 
    ReplyKeyboardMarkup, 
    Update
)

from telegram.ext import (
    CallbackContext, 
    CallbackQueryHandler,
    ConversationHandler
)

from lib.dbhelper import DBHelper, RemoteServer
from lib.settings import *


# State definitions for top level conversation
REGISTRATION, LOCATION, CHECK = map(chr, range(3))
# State definitions for registration conversation
SELECTING_FEATURE, TYPING = map(chr, range(6, 8))
# State definition for otp verification
CHECK_OTP = chr(20)

# Meta state
STOPPING = map(chr, range(4, 5))
# Shortcut for ConversationHandler.END
END = ConversationHandler.END

# Differents states
(
    MAIN_REG,
    REGISTRATION_USER,
    CHECK_USER,
    START_OVER,
    CURRENT_FEATURE,
) = map(chr, range(10, 15))

# Global variable for checking otp_code and verification
otp_code = hashlib.md5(urandom(32)).hexdigest()

# Init class DBhelper for work with db
db = DBHelper()
r_server = RemoteServer()

# Some basic function
def mumble(update: Update, cx: CallbackContext):
    """If user not choice available options send 'i don't know' message"""

    stickers = [
        'CAACAgIAAxkBAAINAl-9nTmXosBfTTsgxqkLPzuoxWWMAAIoAQACzk6PArBGaMYEVWBEHgQ',
        'CAACAgIAAxkBAAINFF-9nlokjHN1b9ugRAGt6XkcO5t7AAIUAQACzk6PArThej9_OS8VHgQ'
    ]

    sticker = choice(stickers)
    update.message.reply_sticker(sticker)


def send_dev(update: Update, cx: CallbackContext):
    """If user choose /dev than send message about developer"""

    text = 'Если вы заметили какие-то сбои в моей программе, \
    то сообщите моему создателю: @delvinru -- Алексей'
    update.message.reply_text(text=text)


def send_help(update: Update, cx: CallbackContext):
    text =  "Используй /start, чтобы начать взаимодействовать с ботом\n"
    text += "Если у вас возникли проблемы, пропишите команду /stop.\n"
    text += "Если и это не помогло, обратитесь к преподавателю."
    update.message.reply_text(text)


def stop(update: Update, cx: CallbackContext) -> int:
    update.message.reply_text(text='Хорошо, может по новой?')
    return END


def start(update: Update, cx: CallbackContext):
    """Initialize main window"""

    # Check user was init or not
    if cx.user_data.get(START_OVER):
        text = f'Привет, {cx.user_data["name"]}!\n'

        # Sometimes this code got exception because message don't callback query
        try:
            update.callback_query.answer()
            update.callback_query.edit_message_text(text=text)
        except:
            update.message.reply_text(text)

        try:
            data = update.message.text
        except:
            # if OTP-code not provided in /start than just end conversation or other shit
            return END

        code = data.removeprefix('/start ')
        if code != '/start':
            check_otp_code(update, cx, code)

        return END
    else:
        user_id = update.message.from_user.id
        user = db.search_user(user_id)

        # If new user was detected
        if user is None:
            keyboard = [
                [InlineKeyboardButton(
                    'Зарегистрироваться', callback_data=str(REGISTRATION_USER))],
            ]
            text =  "Привет, это бот для учёта посещаемости студентов на парах.\n"
            text += "Вводите полное ФИО. Если вы опечатались, то данные можно поправить до нажатия кнопки 'Завершить регистрацию'\n"
            text += "❗️❗️❗\n️Будьте внимательны, после её нажатия изменить свои данные нельзя.\nОбращайтесь к преподавателю.\n❗️❗️❗️"
            text += "\n\n"
            text += "Для того, чтобы отметиться на паре тебе достаточно отсканировать QR-код, который покажет преподаватель на доске."
            text += "Чтобы начать регистрацию нажмите на кнопку ниже👇\n"


            reply_markup = InlineKeyboardMarkup(keyboard)
            update.message.reply_text(
                text,
                reply_markup=reply_markup
            )

            cx.user_data["uid"] = user_id

            logger.info(f'New user {user_id} came to registration menu.')

            return REGISTRATION
        else:
            # user = (id, name)
            text = f'Привет, {user[1]}!\n'

            update.message.reply_text(text=text)

            # Put info in context menu
            cx.user_data['uid'] = user[0]
            cx.user_data['name'] = user[1]

            try:
                data = update.message.text
            except:
                # if code not provided in /start than just end conversation or other shit
                return END

            code = data.removeprefix('/start ')
            if code != '/start':
                check_otp_code(update, cx, code)

            return END

###
# Functions that are required for user registration
###
def reg_select_feature(update: Update, cx: CallbackContext) -> str:
    """Main menu of registration field"""
    buttons = [
        [
            InlineKeyboardButton('ФИО', callback_data='name'),
            InlineKeyboardButton('Группа', callback_data='group')
        ],
        [
            InlineKeyboardButton('Студенческий билет', callback_data='id_card')
        ],
        [
            InlineKeyboardButton(
                'Введённые данные',
                callback_data='show_data'
            ),
            InlineKeyboardButton('Завершить регистрацию', callback_data='done')
        ]
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    text = 'Нажми на кнопку, чтобы указать свои данные.'
    if not cx.user_data.get(START_OVER):
        # First run of this function
        update.callback_query.answer()
        update.callback_query.edit_message_text(text=text, reply_markup=keyboard)
    else:
        update.message.reply_text(text=text, reply_markup=keyboard)

    return SELECTING_FEATURE


def show_data(update: Update, cx: CallbackContext):
    """Show info about user in registration field"""

    cx.user_data[CURRENT_FEATURE] = update.callback_query.data

    text = "*Твой профиль*\n"
    if cx.user_data.get('name'):
        text += f'*ФИО:* {cx.user_data["name"]}\n'
    else:
        text += f'*ФИО:* пока не указано\n'

    if cx.user_data.get('group'):
        text += f'*Группа:* {cx.user_data["group"]}\n'
    else:
        text += f'*Группа:* пока не указана\n'
    
    if cx.user_data.get('id_card'):
        text += f'*Студак:* {cx.user_data["id_card"]}\n'
    else:
        text += f'*Студак:* пока не указан\n'

    buttons = [[InlineKeyboardButton(text='Назад', callback_data='back')]]
    keyboard = InlineKeyboardMarkup(buttons)

    cx.user_data[START_OVER] = False
    update.callback_query.answer()
    update.callback_query.edit_message_text(
        text=text, 
        reply_markup=keyboard, 
        parse_mode='Markdown'
    )

    return MAIN_REG


def ask_for_input(update: Update, cx: CallbackContext):
    """Prompt for user input"""

    cx.user_data[CURRENT_FEATURE] = update.callback_query.data
    text = 'Хорошо, жду информацию🙄'
    update.callback_query.answer()
    update.callback_query.edit_message_text(text=text)
    return TYPING


def save_input(update: Update, cx: CallbackContext):
    """Save user state in context"""

    cx.user_data['uid'] = update.message.from_user.id
    cx.user_data['username'] = update.message.from_user.username
    current_option = cx.user_data[CURRENT_FEATURE]
    user_text = update.message.text

    # This line have special format for group. Ex.: KKSO-11-11
    regex_group = r'^\S{4}-\d{2}-\d{2}$'
    regex_name = r'\S{3,}'

    bad_input = False
    if current_option == 'name':
        if len(findall(regex_name, user_text)) > 0:
            cx.user_data['name'] = user_text
        else:
            bad_input = True
    elif current_option == 'group':
        if len(findall(regex_group, user_text)) > 0:
            cx.user_data['group'] = user_text.upper()
        else:
            bad_input = True
    elif current_option == 'id_card':
        if len(user_text) == 0:
            bad_input = True
        else:
            cx.user_data['id_card'] = user_text.upper()

    if bad_input:
        cx.bot.send_message(
            chat_id=update.message.chat.id,
            text='Вы ввели какие-то некорректные данные.🤔\nПопробуйте снова'
        )

    cx.user_data[START_OVER] = True
    return reg_select_feature(update, cx)


@logger.catch
def register_user(update: Update, cx: CallbackContext):
    """Add user to database"""

    # If tried register without name or group show data and start again
    if not cx.user_data.get('name') or not cx.user_data.get('group'):
        logger.error(
            f'User {cx.user_data["uid"]} try register without required field')
        cx.user_data[START_OVER] = True
        return show_data(update, cx)

    if not cx.user_data.get('username'):
        logger.warning(f'User {cx.user_data["name"]} with empty username')
        cx.user_data['username'] = 'None'

    # Create user in database
    db.init_user(
        cx.user_data['uid'],
        cx.user_data['username'],
        cx.user_data['name'],
        cx.user_data['group']
    )

    r_server.init_user(
        cx.user_data['uid'],
        cx.user_data['id_card']
    )

    logger.info(
        f'User {cx.user_data["uid"]} {cx.user_data["username"]} was registered'
    )

    cx.user_data[START_OVER] = True
    start(update, cx)
    return END


def stop_reg(update: Update, cx: CallbackContext):
    """End registration"""
    update.message.reply_text('Хорошо, пока!')
    return END

###
# Functions that are needed to mark the user
###
def stop_check(update: Update, cx: CallbackContext):
    """End of check"""
    update.message.reply_text('Хорошо, пока!')
    return END


def check_otp_code(update: Update, cx: CallbackContext, code: str):
    """Functions check OTP code input by user and if correct mark him in DB"""

    # Count failed tries
    if not cx.user_data.get('otp_try'):
        cx.user_data['otp_try'] = 0

    global otp_code
    if code == otp_code:
        # mark user in database
        db.mark_user(cx.user_data['uid'])
        r_server.mark_user(cx.user_data['uid'])
        logger.info(
            f'{cx.user_data["uid"]} {cx.user_data["name"]} was marked in DB'
        )
        # send successfull message
        cx.bot.send_message(
            chat_id=update.message.chat.id,
            text='Поздравляю, ты отмечен на паре!☺️'
        )

        return END
    else:
        cx.user_data['otp_try'] += 1

        logger.warning(
            f'{cx.user_data["uid"]} {cx.user_data["name"]} try incorrect password'
        )

        if cx.user_data['otp_try'] >= 3:
            logger.error(
                f'{cx.user_data["uid"]} {cx.user_data["name"]} entered the password incorrectly more than 3 times.'
            )

        cx.bot.send_message(
            chat_id=update.message.chat.id,
            text='Друг, а ты точно на паре?👿'
        )

        return END