import os
from urllib.request import getproxies

import requests
import telebot

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
bot = telebot.TeleBot(os.environ["TELEGRAM_BOT_TOKEN"])

# The local Windows proxy accepts HTTP CONNECT for HTTPS destinations.
proxies = getproxies()
proxy = proxies.get("https", "")
if proxy.startswith(("https://127.0.0.1:", "https://localhost:")):
    proxies["https"] = "http://" + proxy[len("https://"):]
telebot.apihelper.proxy = proxies

def generate_response(prompt):
    # HTTP API works with the installed libraries, without upgrading the old SDK.
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": "Bearer " + OPENAI_API_KEY},
            json={
                "model": "gpt-4.1-mini",
                "input": prompt,
                "temperature": 0.5,
                "max_output_tokens": 4000,
                "store": False,
            },
            proxies=proxies,
            timeout=(10, 90),
        )
    except requests.RequestException:
        raise RuntimeError("Не удалось подключиться к OpenAI. Проверьте интернет и прокси.") from None
    if response.status_code != 200:
        errors = {
            401: "OpenAI: ключ API недействителен. Проверьте OPENAI_API_KEY в настройках запуска.",
            403: "OpenAI: доступ запрещён. Проверьте доступ аккаунта и сети к API.",
            429: "OpenAI: превышен лимит запросов или закончилась квота API. Проверьте баланс и лимиты.",
        }
        raise RuntimeError(errors.get(response.status_code, "Ошибка OpenAI: HTTP " + str(response.status_code)))
    try:
        data = response.json()
        parts = [
            part.get("text", "") if part.get("type") == "output_text" else part.get("refusal", "")
            for item in data.get("output", [])
            if item.get("type") == "message"
            for part in item.get("content", [])
        ]
        text = "\n".join(part for part in parts if part).strip()
    except (ValueError, TypeError, AttributeError):
        raise RuntimeError("OpenAI вернул неожиданный формат ответа.") from None
    if not text:
        raise RuntimeError("OpenAI не вернул текст ответа. Попробуйте ещё раз.")
    return text


ALLOWED_USER_ID = int(os.environ["TELEGRAM_ALLOWED_USER_ID"])
@bot.message_handler(content_types=['text'])
def handle_message(message):
    if (message.from_user is None
            or message.from_user.id != ALLOWED_USER_ID
            or message.chat.type != "private"):
        return
    try:
        text = generate_response(message.text)
    except RuntimeError as error:
        text = str(error)
    # Small chunks also fit Telegram's limit when the answer contains emoji.
    for start in range(0, len(text), 2000):
        bot.send_message(chat_id=message.from_user.id, text=text[start:start + 2000])


if __name__ == '__main__':
    bot.polling()
