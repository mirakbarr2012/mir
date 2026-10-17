from django.urls import path, include
from django.conf.urls.static import static

from . import views
from root import settings

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('social-login/<str:provider>/', views.social_login_view, name='social_login'),
    path('logout/', views.logout_view, name='logout'),
    path('complaint/', views.complaint_view, name='complaint'),
    path('', views.attendance_view, name='attendance_view'),
    path('attendance/', views.attendance_view, name='attendance_view_alt'),
    path('attendance/history/', views.attendance_history_view, name='attendance_history'),
    path('attendance/delete/<int:pk>/', views.attendance_delete, name='attendance_delete'),
    path('fund/', views.fund_view, name='fund_view'),
    path('fund/delete/<int:pk>/', views.fund_delete, name='fund_delete'),
    path('groups/', views.group_list_view, name='group_list'),
    path('groups/<int:pk>/', views.group_detail_view, name='group_detail'),
    path('accounts/', include('allauth.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

