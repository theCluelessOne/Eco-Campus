# app/views_extra.py
from datetime import timedelta
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum,F
from django.views.decorators.http import require_POST

from .models import (
    Activity, EventSlot, Registration, Submission,
    approve_submission, reject_submission,
    total_points, Reward, Redemption, redeem_reward, Student, PointLedger,
    register_user_for_event,       # ← add this
    cancel_registration,
)
from .forms import EventRegistrationForm, EventCancelForm, SubmissionForm, RedemptionForm
from .permissions import admin_required, staff_or_volunteer_required
from .throttling import simple_rate_limit

# ----- Activities -----
@admin_required
def activities_admin(request):
    # simple list page (no template changes required)
    items = Activity.objects.order_by("-created_at")
    return render(request, "admin.html", {"activities": items})  # uses your admin.html

# ----- Events -----
@login_required
def active_events(request):
    include_full = request.GET.get("include_full") == "true"
    now = timezone.now()
    qs = EventSlot.objects.filter(end_at__gte=now).select_related("activity")
    if not include_full:
        qs = qs.filter(registered_count__lt=F("max_participants"))
    # Hand to existing events.html
    return render(request, "events.html", {"events": qs})

@login_required
@require_POST
@simple_rate_limit("event_reg", limit=20, window_sec=60)
def register_event(request):
    form = EventRegistrationForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid request.")
        return redirect("event")
    ev = get_object_or_404(EventSlot, pk=form.cleaned_data["event_id"])
    try:
        reg = register_user_for_event(request.user, ev)
        if reg.status == "registered":
            messages.success(request, "Registered for event!")
        else:
            messages.info(request, "Event is full. You have been waitlisted.")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("event")

@login_required
@require_POST
def cancel_event_registration(request):
    form = EventCancelForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid request.")
        return redirect("event")
    reg = get_object_or_404(Registration, pk=form.cleaned_data["registration_id"], user=request.user)
    cancel_registration(reg)
    messages.success(request, "Registration canceled.")
    return redirect("event")

# ----- Submissions -----
@login_required
def create_submission(request):
    if request.method == "POST":
        form = SubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            sub = form.save(commit=False)
            sub.student = get_object_or_404(Student, user=request.user)
            # Optional cap check: monthly cap per student
            cap = sub.activity.monthly_cap_per_student
            if cap:
                start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                used = PointLedger.objects.filter(
                    user=request.user,
                    activity=sub.activity,
                    created_at__gte=start
                ).count()
                if used >= cap:
                    messages.error(request, "Monthly cap reached for this activity.")
                    return redirect("profile")
            sub.save()
            messages.success(request, "Submission created. Awaiting verification.")
            return redirect("profile")
    else:
        form = SubmissionForm()
    return render(request, "profile.html", {"submission_form": form})

@staff_or_volunteer_required
def verify_queue(request):
    # Volunteers/Admins: see pending (excluding own submissions)
    qs = Submission.objects.select_related("student__user","activity").filter(status="pending")
    qs = qs.exclude(student__user=request.user)
    return render(request, "admin.html", {"pending_submissions": qs})

@staff_or_volunteer_required
@require_POST
@simple_rate_limit("verify", limit=30, window_sec=60)
def approve_submission_view(request, pk):
    sub = get_object_or_404(Submission, pk=pk)
    try:
        approve_submission(sub, request.user, comment=request.POST.get("comment",""))
        messages.success(request, "Submission approved and points awarded.")
    except PermissionError as e:
        messages.error(request, str(e))
    return redirect("verify_queue")

@staff_or_volunteer_required
@require_POST
def reject_submission_view(request, pk):
    sub = get_object_or_404(Submission, pk=pk)
    try:
        reject_submission(sub, request.user, comment=request.POST.get("comment",""))
        messages.info(request, "Submission rejected.")
    except PermissionError as e:
        messages.error(request, str(e))
    return redirect("verify_queue")

# ----- Leaderboard -----
@login_required
def leaderboard(request):
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    overall = (PointLedger.objects
               .values("user__id","user__first_name")
               .annotate(total=Sum("points"))
               .order_by("-total","user__first_name"))
    monthly = (PointLedger.objects
               .filter(created_at__gte=month_start)
               .values("user__id","user__first_name")
               .annotate(total=Sum("points"))
               .order_by("-total","user__first_name"))
    return render(request, "leader.html", {"overall": overall, "monthly": monthly})

# ----- Rewards & Redemptions -----
@login_required
def rewards_list(request):
    items = Reward.objects.filter(active=True).order_by("points_cost")
    return render(request, "profile.html", {"rewards": items})

@login_required
@require_POST
@simple_rate_limit("redeem", limit=10, window_sec=60)
def redeem(request):
    form = RedemptionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid request.")
        return redirect("profile")
    reward = get_object_or_404(Reward, pk=form.cleaned_data["reward_id"])
    try:
        redeem_reward(request.user, reward)
        messages.success(request, "Redemption requested. Await fulfillment.")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("profile")

@admin_required
@require_POST
def fulfill_redemption(request, rid):
    red = get_object_or_404(Redemption, pk=rid, status="pending")
    red.status = "fulfilled"
    red.fulfilled_by = request.user
    red.fulfilled_at = timezone.now()
    red.save(update_fields=["status","fulfilled_by","fulfilled_at"])
    messages.success(request, "Redemption fulfilled.")
    return redirect("profile")

# --- Admin Activities via HTML forms ---
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import user_passes_test
from django.utils import timezone
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from .models import Activity, EventSlot

def _is_admin(u): return u.is_staff or u.is_superuser
admin_required = user_passes_test(_is_admin)

@admin_required
def activities_admin(request):
    """
    GET: render admin.html with activities list
    POST: create activity + one EventSlot from the HTML form fields
    """
    if request.method == "POST":
        title = request.POST.get("title","").strip()
        description = request.POST.get("description","").strip()
        location = request.POST.get("location","").strip()
        slots = int(request.POST.get("slots") or 0)
        # tier/points: HTML adds a hidden input we'll wire in admin.html below
        try:
            tier = int(request.POST.get("tier") or request.POST.get("points") or 2)
        except ValueError:
            tier = 2

        date = (request.POST.get("date") or "").strip()
        time_s = (request.POST.get("time") or "").strip()

        if not title or not slots:
            messages.error(request, "Title and number of slots are required.")
            return redirect("activities_admin")

        # Build datetime if provided, else default to now → now + 1h
        from datetime import datetime, timedelta
        from django.utils import timezone as tz

        if date and time_s:
            start_at = tz.make_aware(datetime.fromisoformat(f"{date}T{time_s}"))
        elif date:
            start_at = tz.make_aware(datetime.fromisoformat(f"{date}T09:00"))
        else:
            start_at = tz.now() + timedelta(minutes=10)
        end_at = start_at + timedelta(hours=1)

        with transaction.atomic():
            act = Activity.objects.create(
                title=title,
                description=description,
                tier=tier,
                requires_proof=False,
                monthly_cap_per_student=None,
            )
            EventSlot.objects.create(
                activity=act,
                start_at=start_at,
                end_at=end_at,
                max_participants=max(1, slots),
                location=location or "TBD",
                notes="",
            )
        messages.success(request, "Activity created.")
        return redirect("activities_admin")

    # GET list
    acts = (Activity.objects
            .all()
            .order_by("-created_at")
            .prefetch_related("slots"))
    # Flatten for simple template loop
    rows = []
    for a in acts:
        for s in a.slots.all():
            rows.append({
                "id": a.id, "title": a.title, "description": a.description,
                "points": a.tier, "slots": s.max_participants,
                "date": s.start_at.date().isoformat(),
                "time": s.start_at.time().strftime("%H:%M"),
                "location": s.location,
                "slot_id": s.id
            })
    return render(request, "admin.html", {"activities": rows})

@admin_required
@require_POST
def delete_activity(request):
    aid = request.POST.get("activity_id")
    if not aid:
        messages.error(request, "Missing activity id.")
        return redirect("activities_admin")
    act = get_object_or_404(Activity, pk=aid)
    act.delete()
    messages.success(request, "Activity deleted.")
    return redirect("activities_admin")
