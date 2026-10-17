from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

class Teacher(models.Model):
    class Role(models.TextChoices):
        TEACHER = "teacher", "Ustoz"
        ADMIN = "admin", "Administrator"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile', verbose_name="Foydalanuvchi")
    first_name = models.CharField(max_length=50, verbose_name="Ismi")
    last_name = models.CharField(max_length=50, verbose_name="Familiyasi")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.TEACHER, verbose_name="Roli")

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @classmethod
    def ensure_first_user_is_admin(cls, user):
        has_admin = (
            cls.objects.filter(role=cls.Role.ADMIN).exists()
            or User.objects.filter(is_superuser=True).exists()
        )
        if has_admin:
            return cls.objects.get_or_create(
                user=user,
                defaults={
                    "first_name": user.first_name or user.username,
                    "last_name": user.last_name or "",
                    "role": cls.Role.TEACHER,
                },
            )[0]

        teacher, _ = cls.objects.get_or_create(
            user=user,
            defaults={
                "first_name": user.first_name or user.username,
                "last_name": user.last_name or "",
                "role": cls.Role.ADMIN,
            },
        )
        teacher.role = cls.Role.ADMIN
        teacher.save(update_fields=["role"])
        user.is_active = True
        user.is_staff = True
        user.save(update_fields=["is_active", "is_staff"])
        return teacher


class Group(models.Model):
    name = models.CharField(max_length=100, verbose_name="Guruh nomi")
    teachers = models.ManyToManyField(Teacher, related_name='groups', blank=True, verbose_name="Ustozlar")

    def __str__(self):
        return self.name


class Student(models.Model):
    first_name = models.CharField(max_length=50, verbose_name="Ismi")
    last_name = models.CharField(max_length=50, verbose_name="Familiyasi")
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, related_name='students', verbose_name="Guruh")

    def __str__(self):
        if self.group:
            return f"{self.first_name} {self.last_name} ({self.group.name})"
        return f"{self.first_name} {self.last_name}"


class Attendance(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendances')
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True, related_name='attendances', verbose_name="Ustoz")
    date = models.DateField(default=timezone.now, verbose_name="Sana")
    is_present = models.BooleanField(default=False, verbose_name="Keldi/Kelmadi")

    class Meta:
        unique_together = ('student', 'date')

    def __str__(self):
        teacher_str = f" (Ustoz: {self.teacher})" if self.teacher else ""
        return f"{self.student} - {self.date} - {'Keldi' if self.is_present else 'Kelmadi'}{teacher_str}"


class Fund(models.Model):
    MONTH_CHOICES = [
        (1, 'Yanvar'), (2, 'Fevral'), (3, 'Mart'), (4, 'Aprel'),
        (5, 'May'), (6, 'Iyun'), (7, 'Iyul'), (8, 'Avgust'),
        (9, 'Sentabr'), (10, 'Oktabr'), (11, 'Noyabr'), (12, 'Dekabr'),
    ]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='funds', verbose_name="O'quvchi")
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Berilgan summa")
    month = models.IntegerField(choices=MONTH_CHOICES, verbose_name="Oy")
    date_given = models.DateTimeField(default=timezone.now, verbose_name="Topshirilgan vaqt")
    description = models.CharField(max_length=200, blank=True, null=True, verbose_name="Izoh")

    def __str__(self):
        return f"{self.student} - {self.get_month_display()} - {self.amount} so'm"


class Complaint(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='complaints', verbose_name='Foydalanuvchi')
    name = models.CharField(max_length=100, verbose_name='Ism')
    phone = models.CharField(max_length=30, verbose_name='Telefon raqami')
    message = models.TextField(verbose_name='Murojaat matni')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Yuborilgan vaqt')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.phone})"
