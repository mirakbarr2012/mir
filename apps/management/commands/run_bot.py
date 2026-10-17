import os
import django
from django.core.management.base import BaseCommand
from django.db.models import Sum
from datetime import date
from django.conf import settings
from asgiref.sync import sync_to_async

def save_chat_id_to_env(chat_id):
    chat_id_str = str(chat_id)
    os.environ['TELEGRAM_CHAT_ID'] = chat_id_str

    env_path = settings.BASE_DIR / '.env'
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        found = False
        new_lines = []
        for line in lines:
            if line.startswith('TELEGRAM_CHAT_ID='):
                new_lines.append(f"TELEGRAM_CHAT_ID={chat_id_str}\n")
                found = True
            else:
                new_lines.append(line)
        
        if not found:
            new_lines.append(f"TELEGRAM_CHAT_ID={chat_id_str}\n")
        
        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)


class Command(BaseCommand):
    help = 'Telegram Botni ishga tushirish (Davomat va Fond hisobotlari bot)'

    def handle(self, *args, **options):
        token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()

        if not token or token == 'YOUR_TELEGRAM_BOT_TOKEN_HERE':
            self.stderr.write(
                self.style.ERROR(
                    "Xatolik: .env faylida TELEGRAM_BOT_TOKEN kiritilmagan!\n"
                    "Botni ishga tushirish uchun .env fayliga bot tokenini qo'shing."
                )
            )
            return

        self.stdout.write(self.style.SUCCESS("Telegram Bot ishga tushmoqda..."))

        from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
        from apps.models import Student, Attendance, Fund
        from apps.views import format_date_uz

        @sync_to_async
        def get_davomat_text():
            today = date.today()
            formatted_date = format_date_uz(today)
            students = list(Student.objects.all())
            if not students:
                return "<i>Sinfda hali o'quvchilar yo'q.</i>"

            attendances = list(Attendance.objects.filter(date=today).select_related('teacher'))
            attendance_dict = {a.student_id: a.is_present for a in attendances}
            teacher_name = None
            for a in attendances:
                if a.teacher:
                    teacher_name = a.teacher.full_name
                    break

            present = []
            absent = []

            for student in students:
                full_name = f"{student.first_name} {student.last_name}".upper()
                if attendance_dict.get(student.id, False):
                    present.append(full_name)
                else:
                    absent.append(full_name)

            text = "═══════════════════\n"
            text += "📋 <b>BUGUNGI SINF DAVOMATI</b>\n"
            text += "═══════════════════\n\n"
            text += f"📅 <b>Sana:</b> <b>{formatted_date}</b>\n"
            if teacher_name:
                text += f"👨‍🏫 <b>Ustoz:</b> <b>{teacher_name}</b>\n"
            text += f"📊 <b>Jami o'quvchilar:</b> <b>{len(students)} nafar</b>\n\n"

            text += f"🟢 <b><u>KELGANLAR ({len(present)} nafar):</u></b>\n"
            if present:
                for idx, name in enumerate(present, 1):
                    text += f"<b>{idx}. 🔹 {name}</b>\n"
            else:
                text += "  <i>Hech kim belgilanmagan / kelmagan</i>\n"

            text += f"\n🔴 <b><u>KELMAGANLAR ({len(absent)} nafar):</u></b>\n"
            if absent:
                for idx, name in enumerate(absent, 1):
                    text += f"<b>{idx}. 🔸 {name}</b>\n"
            else:
                text += "  <b>🎉 Hamma kelgan!</b>\n"

            text += "\n═══════════════════"
            return text

        @sync_to_async
        def get_fond_text():
            total = Fund.objects.aggregate(total=Sum('amount'))['total'] or 0
            funds = list(Fund.objects.select_related('student').order_by('-date_given')[:10])

            text = "═══════════════════\n"
            text += "💰 <b>SINF FONDI HISOBOTI</b>\n"
            text += "═══════════════════\n\n"
            text += f"💵 <b>Umumiy yig'ilgan mablag':</b> <b>{total:,.2f} so'm</b>\n\n"
            text += f"📜 <b><u>OXIRGI TOPSHIRILGAN TO'LOVLAR:</u></b>\n"

            if funds:
                for f in funds:
                    student_name = f"{f.student.first_name} {f.student.last_name}".upper()
                    text += f"• <b>{student_name}</b> ➔ <b>{f.amount:,.0f} so'm</b> (<i>{f.get_month_display()}</i>)\n"
            else:
                text += "<i>Hali fond to'lovlari kiritilmagan.</i>\n"

            text += "\n═══════════════════"
            return text

        @sync_to_async
        def get_oquvchilar_text():
            students = list(Student.objects.all().order_by('last_name', 'first_name'))
            text = "═══════════════════\n"
            text += "👨‍🎓 <b>SINF O'QUVCHILARI RO'YXATI</b>\n"
            text += "═══════════════════\n\n"
            text += f"📊 <b>Jami:</b> <b>{len(students)} nafar</b>\n\n"

            if students:
                for idx, s in enumerate(students, 1):
                    name_upper = f"{s.first_name} {s.last_name}".upper()
                    text += f"<b>{idx}. 👤 {name_upper}</b>\n"
            else:
                text += "<i>Ro'yxatda o'quvchilar yo'q.</i>"

            text += "\n═══════════════════"
            return text

        @sync_to_async
        def auto_save_chat_id(chat_id):
            save_chat_id_to_env(chat_id)

        async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            chat_id = update.effective_chat.id
            await auto_save_chat_id(chat_id)

            keyboard = [
                [
                    InlineKeyboardButton("📋 Bugungi davomat", callback_data="davomat"),
                    InlineKeyboardButton("💰 Sinf fondi", callback_data="fond")
                ],
                [
                    InlineKeyboardButton("👨‍🎓 O'quvchilar ro'yxati", callback_data="oquvchilar")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            welcome_text = (
                "<b>🏫 Maktab Boshqaruvi Telegram Boti</b>\n\n"
                "Xush kelibsiz! Shaxsiy chatingiz muvaffaqiyatli ulandi. "
                "<b>Saytda davomat saqlanganda hisobot to'g'ridan-to'g'ri shu chatingizga keladi! 📥</b>\n\n"
                "Buyruqlar:\n"
                "📌 /davomat - Bugungi sinf davomati\n"
                "📌 /fond - Sinf fondi hisoboti\n"
                "📌 /oquvchilar - Sinf o'quvchilari ro'yxati"
            )
            await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='HTML')

        async def davomat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            chat_id = update.effective_chat.id
            await auto_save_chat_id(chat_id)
            text = await get_davomat_text()
            await update.message.reply_text(text, parse_mode='HTML')

        async def fond_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            chat_id = update.effective_chat.id
            await auto_save_chat_id(chat_id)
            text = await get_fond_text()
            await update.message.reply_text(text, parse_mode='HTML')

        async def oquvchilar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            chat_id = update.effective_chat.id
            await auto_save_chat_id(chat_id)
            text = await get_oquvchilar_text()
            await update.message.reply_text(text, parse_mode='HTML')

        async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            query = update.callback_query
            await query.answer()

            chat_id = update.effective_chat.id
            await auto_save_chat_id(chat_id)

            if query.data == "davomat":
                text = await get_davomat_text()
            elif query.data == "fond":
                text = await get_fond_text()
            elif query.data == "oquvchilar":
                text = await get_oquvchilar_text()
            else:
                text = "Noma'lum buyruq"

            keyboard = [
                [
                    InlineKeyboardButton("📋 Davomat", callback_data="davomat"),
                    InlineKeyboardButton("💰 Fond", callback_data="fond")
                ],
                [
                    InlineKeyboardButton("👨‍🎓 O'quvchilar", callback_data="oquvchilar")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            try:
                await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
            except Exception:
                pass

        app = ApplicationBuilder().token(token).build()

        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", start_command))
        app.add_handler(CommandHandler("davomat", davomat_command))
        app.add_handler(CommandHandler("fond", fond_command))
        app.add_handler(CommandHandler("oquvchilar", oquvchilar_command))
        app.add_handler(CallbackQueryHandler(button_handler))

        self.stdout.write(self.style.SUCCESS("Telegram Bot ishga tushdi va buyruqlarni kutmoqda..."))
        import time
        while True:
            try:
                app.run_polling(drop_pending_updates=True)
            except Exception as e:
                self.stderr.write(self.style.WARNING(f"Tarmoq xatosi yuz berdi: {e}. 3 soniyadan so'ng qayta ulanadi..."))
                time.sleep(3)
