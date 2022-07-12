
import logging
import os
import time

import requests
import telegram

from dotenv import load_dotenv
from telegram import Bot, TelegramError
from http import HTTPStatus
from json.decoder import JSONDecodeError

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    filename='main.log',
    format='%(asctime)s, %(levelname)s, %(message)s, %(name)s',
    filemode='w'
)
logger = logging.getLogger(__name__)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}
LIST_OF_ERRORS = []

HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_and_logging_error(message) -> None:
    """Отправляет сообщение c содержимым ошибки в Telegram чат.
    если до этого сообщение не было отправлено.
    """
    logger.error(message)

    if message in LIST_OF_ERRORS:
        return

    bot = Bot(token=TELEGRAM_TOKEN)
    telegram_message = send_message(bot, message)
    if isinstance(telegram_message, telegram.message.Message):
        LIST_OF_ERRORS.append(message)


def send_message(bot, message) -> telegram.message.Message:
    """отправляет сообщение в Telegram чат."""
    telegram_message = bot.send_message(TELEGRAM_CHAT_ID, message)

    try:
        telegram_message = bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.info(f'Отправлено сообщение: {message}')
        return telegram_message
    except TelegramError:
        send_and_logging_error(f'НЕ Отправлено сообщение: {message}')


def get_api_answer(current_timestamp) -> dict:
    """делает запрос к API-сервису.
    В качестве параметра функция получает временную метку.
    В случае успешного запроса должна вернуть ответ API,
    преобразовав его из формата JSON к типам данных Python
    """
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    # params = {'from_date': 1656333949}  # 27/06
    try:
        answer = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except requests.exceptions.HTTPError as error:
        send_and_logging_error(f'Http Error: {error}')
        return None
    except requests.exceptions.ConnectionError as error:
        send_and_logging_error(f'Error Connecting: {error}')
        return None
    except requests.exceptions.Timeout as error:
        send_and_logging_error(f'Timeout Error: {error}')
        return None
    except requests.exceptions.RequestException as error:
        send_and_logging_error(f'Error: {error}')
        return None

    if answer.status_code != HTTPStatus.OK:
        send_and_logging_error(f'В ответ от API статус {answer.status_code}')
        return None

    try:
        return answer.json()
    except JSONDecodeError:
        send_and_logging_error('Ошибка преобразования в джейсон')


def check_response(response) -> list:
    """Gроверяет ответ API на корректность.
    Если ответ API соответствует ожиданиям,
    то функция должна вернуть список домашних работ
    """
    if not isinstance(response, dict):
        # send_and_logging_error('В ответ от API вернулся не словарь')
        # это чтобы пройти pytest
        raise TypeError('В ответ от API вернулся не словарь')

    # проверяем что homeworks существуют
    homeworks_list = response.get('homeworks')
    if homeworks_list is None:
        send_and_logging_error('В ответе от API нет ключа homeworks')
        return None

    current_date = response.get('current_date')
    if current_date is None:
        send_and_logging_error('В ответе от API нет ключа current_date')
        return None

    # проверяем что homeworks это список
    if not isinstance(homeworks_list, list):
        send_and_logging_error('homeworks_list не список')
        return None

    return homeworks_list


def parse_status(homework) -> str:
    """извлекает из информации о конкретной домашней работе статус этой работы.
    В качестве параметра функция получает только один элемент
    из списка домашних работ.
    В случае успеха, функция возвращает подготовленную для отправки
    в Telegram строку, содержащую один из вердиктов словаря
    """
    homework_name = homework.get('homework_name')
    if homework_name is None:
        # send_and_logging_error('В словаре homework нет поля homework_name')
        # это чтобы пройти pytest
        raise KeyError('В словаре homework нет поля homework_name')

    homework_status = homework.get('status')
    verdict = HOMEWORK_STATUSES.get(homework_status)

    if verdict is None:
        send_and_logging_error(f'В ответе от API статус {homework_status}')

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens() -> bool:
    """проверяет доступность переменных окружения.
    которые необходимы для работы программы.
    """
    if PRACTICUM_TOKEN is None:
        return False
    if TELEGRAM_TOKEN is None:
        return False
    if TELEGRAM_CHAT_ID is None:
        return False
    return True


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical('Не доступны переменные окружения!')
        return

    bot = Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks_list = check_response(response)
            # если вернулось ничего, то надо заершать, что-то пошло не так
            if homeworks_list is None:
                return
            if len(homeworks_list) > 0:
                homework = homeworks_list[0]
                current_timestamp = homework.get('current_date')
                message = parse_status(homework)
                send_message(bot, message)

            time.sleep(RETRY_TIME)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_and_logging_error(message)
            time.sleep(RETRY_TIME)
        else:
            send_and_logging_error('неопознанный косяк')


if __name__ == '__main__':
    main()
