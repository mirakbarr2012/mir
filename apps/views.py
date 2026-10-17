from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Sum
from django.contrib.auth import login, logout, authenticate, get_user_model
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.conf import settings
from functools import wraps
from .models import Student, Attendance, Fund, Teacher, Group, Complaint
from .forms import RegistrationForm
from datetime import datetime, date
from httpx import get, post
User = get_user_model()

# O'zbek oylar va hafta kunlari
OY_NOMLARI = {
    1: 'Yanvar', 2: 'Fevral', 3: 'Mart', 4: 'Aprel',
    5: 'May', 6: 'Iyun', 7: 'Iyul', 8: 'Avgust',
    9: 'Sentabr', 10: 'Oktabr', 11: 'Noyabr', 12: 'Dekabr'
}
KUN_NOMLARI = {
    0: 'Dushanba', 1: 'Seshanba', 2: 'Chorshanba',
    3: 'Payshanba', 4: 'Juma', 5: 'Shanba', 6: 'Yakshanba'
}

def format_date_uz(d):
    kun = KUN_NOMLARI[d.weekday()]
    oy = OY_NOMLARI[d.month]
    return f"{kun}, {d.day}-{oy}, {d.year} yil"


def get_teacher_profile(user):
    try:
        return user.teacher_profile
    except Teacher.DoesNotExist:
        return None


def is_admin_user(user):
    teacher = get_teacher_profile(user)
    return user.is_superuser or (
        teacher is not None and teacher.role == Teacher.Role.ADMIN
    )


def get_accessible_groups(user, teacher=None):
    if is_admin_user(user):
        return Group.objects.all()
    teacher = teacher or get_teacher_profile(user)
    if teacher is None:
        return Group.objects.none()
    return teacher.groups.all()


def social_provider_is_configured(provider):
    app = settings.SOCIALACCOUNT_PROVIDERS.get(provider, {}).get('APP', {})
    client_id = app.get('client_id', '')
    client_secret = app.get('secret', '')
    return bool(
        isinstance(client_id, str)
        and client_id.strip()
        and isinstance(client_secret, str)
        and client_secret.strip()
        and client_id.strip() != f'{provider.upper()}_CLIENT_ID'
        and client_secret.strip() != f'{provider.upper()}_CLIENT_SECRET'
    )


def auth_and_pin_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_active:
            raise PermissionDenied
        if not request.user.is_superuser and get_teacher_profile(request.user) is None:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def admin_required(view_func):
    @auth_and_pin_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not is_admin_user(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def register_view(request):
    if request.user.is_authenticated:
        return redirect('attendance_view')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            first_account = not Teacher.objects.exists() and not User.objects.filter(is_superuser=True).exists()
            if first_account:
                user.is_active = True
                user.is_staff = True
                user.save()
                Teacher.ensure_first_user_is_admin(user)
                login(request, user)
                messages.success(request, "Birinchi foydalanuvchi sifatida administrator sifatida ro'yxatdan o'tdingiz.")
                return redirect('attendance_view')

            user.is_active = False
            user.save()
            Teacher.objects.create(
                user=user,
                first_name=user.first_name,
                last_name=user.last_name,
            )
            messages.info(
                request,
                "Ro'yxatdan o'tdingiz. Admin akkauntingizni faollashtirgandan "
                "so'ng tizimga kirishingiz mumkin.",
            )
            return redirect('login')
    else:
        form = RegistrationForm()

    return render(request, 'register.html', {'form': form})


def social_login_view(request, provider):
    if provider not in {'google', 'github'}:
        raise Http404

    if not social_provider_is_configured(provider):
        provider_name = {'google': 'Google', 'github': 'GitHub'}[provider]
        messages.error(
            request,
            f"{provider_name} bilan kirish hozir sozlanmagan. "
            "Client ID va Client Secret qiymatlarini .env fayliga kiriting.",
        )
        return redirect('register')

    return redirect(f'/accounts/{provider}/login/')


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        user = User.objects.filter(username=username).first()
        if user and user.check_password(password):
            if not user.is_active:
                messages.error(request, "Akkauntingiz hali admin tomonidan faollashtirilmagan!")
            elif not user.is_superuser and get_teacher_profile(user) is None:
                messages.error(request, "Akkauntingizga admin tomonidan rol berilishi kerak.")
            else:
                login(request, user)
                messages.success(request, f"Xush kelibsiz, {user.first_name or user.username}!")
                return redirect('attendance_view')
        else:
            messages.error(request, "Foydalanuvchi nomi yoki parol noto'g'ri!")
    return render(request, 'login.html')


def logout_view(request):
    request.session.flush()
    logout(request)
    messages.info(request, "Tizimdan chiqdingiz.")
    return redirect('login')


@auth_and_pin_required
def complaint_view(request):
    if request.method == 'POST':
        name = (request.POST.get('name', '') or '').strip()
        phone = (request.POST.get('phone', '') or '').strip()
        message = (request.POST.get('message', '') or '').strip()

        if not name or not phone or not message:
            messages.error(request, 'Ism, telefon raqami va murojaat matni majburiy.')
            return render(request, 'complaint.html', {
                'name': name,
                'phone': phone,
                'message': message,
            })

        complaint = Complaint.objects.create(
            user=request.user,
            name=name,
            phone=phone,
            message=message,
        )

        try:
            from .telegram import send_complaint_notification
            send_complaint_notification(name, phone, message)
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Telegram murojaat yuborishda xatolik yuz berdi.')

        messages.success(request, 'Murojaatingiz muvaffaqiyatli yuborildi.')
        return redirect('attendance_view')

    return render(request, 'complaint.html')


@auth_and_pin_required
def attendance_view(request):
    date_str = request.GET.get('date') or request.POST.get('date')
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = date.today()
    else:
        selected_date = date.today()

    current_teacher = get_teacher_profile(request.user)
    if current_teacher is None and request.user.is_superuser:
        current_teacher = Teacher.objects.create(
            user=request.user,
            first_name=request.user.first_name or request.user.username,
            last_name=request.user.last_name or "",
            role=Teacher.Role.ADMIN,
        )
    is_admin = is_admin_user(request.user)
    groups = get_accessible_groups(request.user, current_teacher)
    active_teachers = Teacher.objects.filter(user__is_active=True) if is_admin else [current_teacher]

    # O'quvchi qo'shish
    if request.method == 'POST' and 'add_student' in request.POST:
        if not is_admin:
            raise PermissionDenied
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        group_id = request.POST.get('group_id')
        group = Group.objects.filter(id=group_id).first() if group_id else None

        if first_name and last_name:
            Student.objects.create(first_name=first_name, last_name=last_name, group=group)
        # Guruh filterini saqlab qolish
        current_group_filter = request.POST.get('current_group_filter') or ''
        if current_group_filter:
            return redirect(f'/?date={selected_date}&group_id={current_group_filter}')
        return redirect(f'/?date={selected_date}')

    # O'quvchi o'chirish
    if request.method == 'POST' and 'delete_student' in request.POST:
        if not is_admin:
            raise PermissionDenied
        student_id = request.POST.get('delete_student')
        Student.objects.filter(id=student_id).delete()
        # Guruh filterini saqlab qolish
        current_group_filter = request.POST.get('current_group_filter') or ''
        if current_group_filter:
            return redirect(f'/?date={selected_date}&group_id={current_group_filter}')
        return redirect(f'/?date={selected_date}')

    # Davomatni saqlash → shu sahifada qolish
    if request.method == 'POST' and 'save_attendance' in request.POST:
        group_filter_id = request.POST.get('filter_group_id')
        selected_group = (
            get_object_or_404(groups, pk=group_filter_id)
            if group_filter_id
            else None
        )
        selected_teacher_id = request.POST.get('teacher_id')
        saving_teacher = current_teacher
        if is_admin and selected_teacher_id:
            saving_teacher = get_object_or_404(
                Teacher, pk=selected_teacher_id, user__is_active=True
            )

        if group_filter_id:
            students = selected_group.students.all().select_related('group')
        elif is_admin:
            students = Student.objects.all().select_related('group')
        else:
            students = Student.objects.filter(group__in=groups).select_related('group')

        saved_list = []
        for student in students:
            status = request.POST.get(f'status_{student.id}') == 'present'
            Attendance.objects.update_or_create(
                student=student,
                date=selected_date,
                defaults={
                    'is_present': status,
                    'teacher': saving_teacher
                }
            )
            saved_list.append({
                'full_name': f"{student.first_name} {student.last_name}",
                'group_name': student.group.name if student.group else None,
                'is_present': status
            })

        # Telegram guruh/kanalga bildirishnoma yuborish
        try:
            from .telegram import send_attendance_notification
            teacher_name = saving_teacher.full_name if saving_teacher else current_teacher.full_name
            group_name = None
            if group_filter_id:
                group_obj = Group.objects.filter(id=group_filter_id).first()
                if group_obj:
                    group_name = group_obj.name
            send_attendance_notification(selected_date, format_date_uz(selected_date), saved_list, teacher_name=teacher_name, group_name=group_name)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Telegram yuborishda kutilmagan xato: {e}")

        messages.success(request, "Davomat saqlandi!")
        # Guruh filterini saqlab qolish va shu sahifada qolish
        if group_filter_id:
            return redirect(f'/?date={selected_date}&group_id={group_filter_id}')
        return redirect(f'/?date={selected_date}')

    # Sahifa uchun ma'lumotlar
    group_filter_id = request.GET.get('group_id')
    if group_filter_id:
        selected_group = get_object_or_404(groups, pk=group_filter_id)
        students = selected_group.students.all().select_related('group')
    elif is_admin:
        selected_group = None
        students = Student.objects.all().select_related('group')
    else:
        selected_group = None
        students = Student.objects.filter(group__in=groups).select_related('group')

    attendance_records = {
        a.student_id: a
        for a in Attendance.objects.filter(
            date=selected_date, student__in=students
        ).select_related('teacher')
    }

    # Tanlangan kungi ustozni aniqlash
    existing_teacher_on_date = None
    for a in attendance_records.values():
        if a.teacher:
            existing_teacher_on_date = a.teacher
            break

    active_teacher = existing_teacher_on_date or current_teacher

    student_list = []
    for student in students:
        att = attendance_records.get(student.id)
        student_list.append({
            'id': student.id,
            'full_name': f"{student.first_name} {student.last_name}",
            'group_name': student.group.name if student.group else None,
            'is_present': att.is_present if att else False
        })

    context = {
        'student_list': student_list,
        'selected_date': selected_date,
        'formatted_date': format_date_uz(selected_date),
        'active_teachers': active_teachers,
        'current_teacher': active_teacher,
        'logged_in_teacher': current_teacher,
        'groups': groups,
        'selected_group': selected_group,
        'group_filter_id': group_filter_id,
        'is_admin': is_admin,
    }
    return render(request, 'attendance.html', context)


@auth_and_pin_required
def attendance_history_view(request):
    current_teacher = get_teacher_profile(request.user)
    is_admin = is_admin_user(request.user)
    groups = get_accessible_groups(request.user, current_teacher)
    records = Attendance.objects.select_related(
        'student', 'teacher', 'student__group'
    )

    if not is_admin:
        records = records.filter(student__group__in=groups)

    group_filter_id = request.GET.get('group_id')
    if group_filter_id:
        selected_group = get_object_or_404(groups, pk=group_filter_id)
        records = records.filter(student__group=selected_group)
    else:
        selected_group = None
    records = records.order_by('-date', 'student__last_name', 'student__first_name')

    history = []
    current_date = None

    for record in records:
        if record.date != current_date:
            current_date = record.date
            history.append({
                'date': record.date,
                'formatted_date': format_date_uz(record.date),
                'teacher': record.teacher,
                'records': [],
            })
        if not history[-1]['teacher'] and record.teacher:
            history[-1]['teacher'] = record.teacher
        history[-1]['records'].append(record)

    return render(request, 'attendance_history.html', {
        'history': history,
        'groups': groups,
        'selected_group': selected_group,
        'group_filter_id': group_filter_id,
        'is_admin': is_admin,
    })


@admin_required
def fund_view(request):
    # Fond yozuvini o'chirish
    if request.method == 'POST' and 'delete_fund' in request.POST:
        fund_id = request.POST.get('delete_fund')
        Fund.objects.filter(id=fund_id).delete()
        return redirect('fund_view')

    # Fond yozuvini tahrirlash
    if request.method == 'POST' and 'edit_fund' in request.POST:
        fund_id = request.POST.get('fund_id')
        amount = request.POST.get('amount')
        month = request.POST.get('month')
        description = request.POST.get('description', '')
        if fund_id and amount and month:
            try:
                fund = Fund.objects.get(id=fund_id)
                fund.amount = amount
                fund.month = month
                fund.description = description
                fund.save()
            except Fund.DoesNotExist:
                pass
        return redirect('fund_view')

    # O'quvchini o'chirish (fond sahifasidan)
    if request.method == 'POST' and 'delete_student' in request.POST:
        student_id = request.POST.get('delete_student')
        Student.objects.filter(id=student_id).delete()
        return redirect('fund_view')

    # Yangi fond yozuvi qo'shish
    if request.method == 'POST' and 'add_fund' in request.POST:
        student_id = request.POST.get('student_id')
        amount = request.POST.get('amount')
        month = request.POST.get('month')
        description = request.POST.get('description', '')
        if student_id and amount and month:
            try:
                student = Student.objects.get(id=student_id)
                Fund.objects.create(student=student, amount=amount, month=month, description=description)
            except Student.DoesNotExist:
                pass
        return redirect('fund_view')

    students = Student.objects.all()
    fund_history = Fund.objects.all().order_by('-date_given')
    total_fund = Fund.objects.aggregate(total=Sum('amount'))['total'] or 0

    context = {
        'students': students,
        'fund_history': fund_history,
        'total_fund': total_fund,
        'current_time': timezone.now(),
        'month_choices': Fund.MONTH_CHOICES,
    }
    return render(request, 'fund.html', context)


@admin_required
def fund_delete(request, pk):
    if request.method != 'POST':
        raise PermissionDenied
    item = get_object_or_404(Fund, pk=pk)
    item.delete()
    return redirect('fund_view')


@admin_required
def attendance_delete(request, pk):
    if request.method != 'POST':
        raise PermissionDenied
    record = get_object_or_404(Attendance, pk=pk)
    record.delete()
    return redirect('attendance_history')


# ===================== GURUH BOSHQARUVI =====================

@auth_and_pin_required
def group_list_view(request):
    """Guruhlar ro'yxati va yangi guruh qo'shish"""
    current_teacher = get_teacher_profile(request.user)
    is_admin = is_admin_user(request.user)

    if request.method == 'POST' and 'add_group' in request.POST:
        if not is_admin:
            raise PermissionDenied
        name = request.POST.get('name', '').strip()
        if name:
            Group.objects.create(name=name)
            messages.success(request, f"'{name}' guruhi yaratildi!")
        return redirect('group_list')

    if request.method == 'POST' and 'delete_group' in request.POST:
        if not is_admin:
            raise PermissionDenied
        group_id = request.POST.get('delete_group')
        Group.objects.filter(id=group_id).delete()
        messages.info(request, "Guruh o'chirildi.")
        return redirect('group_list')

    groups = get_accessible_groups(
        request.user, current_teacher
    ).prefetch_related('students', 'teachers')
    context = {
        'groups': groups,
        'is_admin': is_admin,
    }
    return render(request, 'group_list.html', context)


@auth_and_pin_required
def group_detail_view(request, pk):
    """Guruh tafsilotlari: o'quvchilar, ustozlar, davomat tarixi"""
    group = get_object_or_404(
        get_accessible_groups(request.user), pk=pk
    )
    students = group.students.all().prefetch_related('attendances')
    teachers = group.teachers.all()

    # Guruhga tegishli o'quvchilarning davomat tarixi
    student_ids = [s.id for s in students]
    attendance_records = Attendance.objects.filter(student_id__in=student_ids).select_related('student', 'teacher').order_by('-date')

    context = {
        'group': group,
        'students': students,
        'teachers': teachers,
        'attendance_records': attendance_records,
    }
    return render(request, 'group_detail.html', context)

import requests
from django.shortcuts import render

TELEGRAM_BOT_TOKEN = "8919353734:AAG22rLkUZWe25E-xLU61LgZDgL2viDykNk"
CHAT_ID = 5700429424


def bot(request):
    print("BOT VIEW ISHLADI!")
    print("METHOD:", request.method)

    if request.method == "POST":
        print("POST ISHLADI!")

        name = request.POST.get("name")
        phone = request.POST.get("phone")
        message = request.POST.get("message")

        print("DATA:", name, phone, message)

        text = f"""🧑 Foydalanuvchi: {name}
📞 Raqami: {phone}
📕 Xabar: {message}"""

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

        try:
            response = requests.post(
                url,
                data={
                    "chat_id": CHAT_ID,
                    "text": text
                },
                timeout=10
            )

            print("TELEGRAM STATUS:", response.status_code)
            print("TELEGRAM JAVOBI:", response.text)

            response.raise_for_status()

        except requests.RequestException as e:
            print("TELEGRAM XATOSI:", e)

    return render(request, "contact.html")