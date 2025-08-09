# app/permissions.py
from django.contrib.auth.decorators import user_passes_test

def is_admin(u): return u.is_staff
def is_volunteer(u):
    try:
        return (not u.is_anonymous) and getattr(u.student, "role", "student") == "volunteer"
    except Exception:
        return False

def staff_or_volunteer_required(view):
    return user_passes_test(lambda u: u.is_staff or is_volunteer(u))(view)

def admin_required(view):
    return user_passes_test(is_admin)(view)
