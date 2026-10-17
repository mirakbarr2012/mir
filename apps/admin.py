from django.contrib import admin
from django.contrib.auth import get_user_model
from .models import Teacher, Group, Student, Attendance, Fund


User = get_user_model()


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'user', 'role', 'get_is_active')
    list_editable = ('role',)
    list_filter = ('role', 'user__is_active')
    search_fields = ('first_name', 'last_name', 'user__username')
    actions = ('activate_accounts', 'deactivate_accounts')

    def get_is_active(self, obj):
        return obj.user.is_active
    get_is_active.boolean = True
    get_is_active.short_description = "Faol (Active)"

    @admin.action(description="Tanlangan akkauntlarni faollashtirish")
    def activate_accounts(self, request, queryset):
        User.objects.filter(pk__in=queryset.values('user_id')).update(is_active=True)

    @admin.action(description="Tanlangan akkauntlarni vaqtincha bloklash")
    def deactivate_accounts(self, request, queryset):
        User.objects.filter(pk__in=queryset.values('user_id')).update(is_active=False)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name',)
    filter_horizontal = ('teachers',)
    search_fields = ('name',)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'group')
    list_filter = ('group',)
    search_fields = ('first_name', 'last_name')


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('student', 'teacher', 'date', 'is_present')
    list_filter = ('date', 'is_present', 'teacher')
    search_fields = ('student__first_name', 'student__last_name', 'teacher__first_name', 'teacher__last_name')


@admin.register(Fund)
class FundAdmin(admin.ModelAdmin):
    list_display = ('student', 'amount', 'month', 'date_given')
    list_filter = ('month', 'date_given')
    search_fields = ('student__first_name', 'student__last_name')
