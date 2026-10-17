import os
import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

def _read_env_value(env_key):
    value = os.getenv(env_key, '').strip()
    try:
        env_file = settings.BASE_DIR / '.env'
        if os.path.exists(env_file):
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith(f'{env_key}='):
                        val = line.split('=', 1)[1].strip()
                        if val:
                            value = val
                            break
    except Exception:
        pass
    return value


def get_bot_token():
    return _read_env_value('TELEGRAM_BOT_TOKEN')


def get_chat_id():
    return _read_env_value('TELEGRAM_CHAT_ID')


def get_attendance_bot_token():
    value = _read_env_value('ATTENDANCE_BOT_TOKEN')
    return value or get_bot_token()


def get_attendance_chat_id():
    value = _read_env_value('ATTENDANCE_CHAT_ID')
    return value or get_chat_id()


def get_complaint_bot_token():
    value = _read_env_value('COMPLAINT_BOT_TOKEN')
    return value or get_bot_token()


def get_complaint_chat_id():
    value = _read_env_value('COMPLAINT_CHAT_ID')
    return value or get_chat_id()


def send_telegram_notification(text, token=None, chat_id=None):
    """
    Telegram guruh/kanal/admin ga bildirishnoma yuborish
    """
    token = (token or '').strip() or get_bot_token()
    chat_id = (chat_id or '').strip() or get_chat_id()

    if not token or not chat_id or token == 'YOUR_TELEGRAM_BOT_TOKEN_HERE':
        logger.info("Telegram Bot Token yoki Chat ID sozlanmagan.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }

    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code != 200:
            logger.error(f"Telegram API xatoligi ({response.status_code}): {response.text}")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Telegram bildirishnoma yuborishda xatolik: {e}")
        return False


def send_complaint_notification(name, phone, message):
    text = (
        "📩 <b>YANGI MUROJAAT</b>\n\n"
        f"👤 <b>Ism:</b> {name}\n"
        f"📞 <b>Telefon:</b> {phone}\n\n"
        f"💬 <b>Murojaat:</b>\n{message}"
    )
    return send_telegram_notification(
        text,
        token=get_complaint_bot_token(),
        chat_id=get_complaint_chat_id(),
    )


def send_attendance_notification(selected_date, formatted_date, student_list, teacher_name=None, group_name=None):
    """
    Davomat saqlanganda Telegram ga avtomatik kattaroq va ko'rkam hisobot yuborish.
    Guruh bo'yicha davomat ma'lumotlari bilan.
    """
    present_students = [s for s in student_list if s['is_present']]
    absent_students = [s for s in student_list if not s['is_present']]

    message = "═══════════════════\n"
    message += "📋 <b>SINF DAVOMATI SAQLANDI</b>\n"
    message += "═══════════════════\n\n"
    message += f"📅 <b>Sana:</b> <b>{formatted_date}</b>\n"
    if group_name:
        message += f"👥 <b>Guruh:</b> <b>{group_name}</b>\n"
    if teacher_name:
        message += f"👨‍🏫 <b>Ustoz:</b> <b>{teacher_name}</b>\n"
    message += f"📊 <b>Jami o'quvchilar:</b> <b>{len(student_list)} nafar</b>\n\n"

    message += f"🟢 <b><u>KELGANLAR ({len(present_students)} nafar):</u></b>\n"
    if present_students:
        for idx, s in enumerate(present_students, 1):
            name_upper = s['full_name'].upper()
            group_tag = f" [{s.get('group_name', '')}]" if s.get('group_name') else ""
            message += f"<b>{idx}. 🔹 {name_upper}{group_tag}</b>\n"
    else:
        message += "  <i>Hech kim kelmadi</i>\n"

    message += f"\n🔴 <b><u>KELMAGANLAR ({len(absent_students)} nafar):</u></b>\n"
    if absent_students:
        for idx, s in enumerate(absent_students, 1):
            name_upper = s['full_name'].upper()
            group_tag = f" [{s.get('group_name', '')}]" if s.get('group_name') else ""
            message += f"<b>{idx}. 🔸 {name_upper}{group_tag}</b>\n"
    else:
        message += "  <b>🎉 Hamma kelgan!</b>\n"

    message += "\n═══════════════════"

    return send_telegram_notification(
        message,
        token=get_attendance_bot_token(),
        chat_id=get_attendance_chat_id(),
    )

