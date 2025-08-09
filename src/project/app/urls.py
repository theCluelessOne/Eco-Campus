from django.contrib import admin
from django.urls import path
from . import views 

urlpatterns = [

    
    path('', views.home, name='home'),
    path('signup/', views.sign, name='signin'),
    path('login/', views.log, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile,name="profile"),
    path('leader/', views.leader,name="leader"),
    
]

from django.urls import path
from . import views  # your existing
from . import views_extra as vx  # the server handlers we already added

urlpatterns += [
    # Admin Activities (HTML form posts)
    path('admins/activities/', vx.activities_admin, name='activities_admin'),
    path('admins/activities/delete/', vx.delete_activity, name='activities_delete'),

    # Events HTML flows
    path('events/active/', vx.active_events, name='events_active'),
    path('events/register/', vx.register_event, name='register_event'),
    path('events/cancel/', vx.cancel_event_registration, name='cancel_event'),

    # Submissions & Rewards via HTML forms
    path('submissions/new/', vx.create_submission, name='create_submission'),
    path('verify/queue/', vx.verify_queue, name='verify_queue'),
    path('verify/<int:pk>/approve/', vx.approve_submission_view, name='approve_submission'),
    path('verify/<int:pk>/reject/', vx.reject_submission_view, name='reject_submission'),
    path('rewards/', vx.rewards_list, name='rewards_list'),
    path('rewards/redeem/', vx.redeem, name='redeem'),

    # Leaderboard
    path('leaderboard/data/', vx.leaderboard, name='leaderboard_data'),

     path('events/', vx.active_events, name='event'),
     path('admins/', vx.activities_admin, name='admin')
]
