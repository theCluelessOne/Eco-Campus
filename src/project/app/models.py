# app/models.py
from django.db import models, transaction
from django.db.models import F, Q, UniqueConstraint, CheckConstraint
from django.contrib.auth.models import User
from django.utils import timezone

# ====== Existing ======
class Student(models.Model):  # (unchanged)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=15)
    pnr = models.CharField(max_length=50, unique=True)
    department = models.CharField(max_length=50)
    semester = models.CharField(max_length=5)
    # Optional role helper (default student). Admins use is_staff.
    role = models.CharField(
        max_length=20,
        choices=[("student","Student"),("volunteer","Volunteer")],
        default="student",
    )
    def __str__(self): return self.user.username

# ====== Activities ======
class Activity(models.Model):
    TIER_CHOICES = [(2,"Tier 2"), (5,"Tier 5"), (8,"Tier 8")]
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    tier = models.IntegerField(choices=TIER_CHOICES)
    requires_proof = models.BooleanField(default=False)
    monthly_cap_per_student = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def points(self) -> int:
        # Points derived directly from tier (2/5/8)
        return self.tier

    def __str__(self): return f"{self.title} (T{self.tier})"

# ====== Events & Registration ======
class EventSlot(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.PROTECT, related_name="slots")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    max_participants = models.PositiveIntegerField()
    registered_count = models.PositiveIntegerField(default=0)  # denormalized
    location = models.CharField(max_length=200)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            CheckConstraint(check=Q(end_at__gt=F('start_at')), name="event_time_valid"),
            CheckConstraint(check=Q(registered_count__gte=0), name="event_regcnt_nonneg"),
        ]

    def __str__(self): return f"{self.activity.title} @ {self.start_at:%Y-%m-%d %H:%M}"

    @property
    def is_full(self):
        return self.registered_count >= self.max_participants

    @property
    def is_over(self):
        return timezone.now() > self.end_at

class Registration(models.Model):
    STATUS_CHOICES = [
        ("registered","Registered"),
        ("waitlisted","Waitlisted"),
        ("canceled","Canceled"),
    ]
    event = models.ForeignKey(EventSlot, on_delete=models.CASCADE, related_name="registrations")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="registrations")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="registered")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["event","user"], name="uniq_event_user"),
        ]

# ====== Verification Workflow & Points ======
class Submission(models.Model):
    STATUS_CHOICES = [("pending","Pending"), ("approved","Approved"), ("rejected","Rejected")]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="submissions")
    activity = models.ForeignKey(Activity, on_delete=models.PROTECT, related_name="submissions")
    event_slot = models.ForeignKey(EventSlot, on_delete=models.SET_NULL, null=True, blank=True)
    evidence_url = models.URLField(blank=True)
    evidence_file = models.FileField(upload_to="evidence/", blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="verifications")
    verified_at = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def can_verify(self, by_user: User) -> bool:
    # admins always allowed (but block self-approval below)
        if by_user.is_staff:
            pass
        else:
            # volunteers allowed; guard missing Student profile
            try:
                if getattr(by_user.student, "role", "student") != "volunteer":
                    return False
            except Student.DoesNotExist:
                return False

        # Block self-approval
        return self.student.user_id != by_user.id

class PointLedger(models.Model):
    SOURCE_CHOICES = [("submission","submission"), ("manual","manual")]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="point_ledger")
    activity = models.ForeignKey(Activity, on_delete=models.PROTECT)
    points = models.IntegerField()
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES)
    reference_id = models.CharField(max_length=64)  # submission_id or note
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user","created_at"]) ]
        constraints = [
            # Idempotency: only one ledger row per submission
            UniqueConstraint(
                fields=["source","reference_id"], name="uniq_source_reference"
            ),
        ]

# ====== Badges ======
class BadgeThreshold(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    percent_of_potential = models.PositiveIntegerField(default=60)  # 60% default
    active = models.BooleanField(default=True)

# ====== Rewards & Redemptions ======
class Reward(models.Model):
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    points_cost = models.PositiveIntegerField()
    stock = models.PositiveIntegerField(null=True, blank=True)  # None => unlimited
    active = models.BooleanField(default=True)

    def __str__(self): return f"{self.title} ({self.points_cost} pts)"

class Redemption(models.Model):
    STATUS_CHOICES = [("pending","Pending"), ("fulfilled","Fulfilled"), ("canceled","Canceled")]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="redemptions")
    reward = models.ForeignKey(Reward, on_delete=models.PROTECT, related_name="redemptions")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    fulfilled_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="fulfillments")
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

# ====== Domain services (transactional helpers) ======

def total_points(user: User, start=None, end=None) -> int:
    qs = PointLedger.objects.filter(user=user)
    if start: qs = qs.filter(created_at__gte=start)
    if end:   qs = qs.filter(created_at__lt=end)
    return qs.aggregate(s=models.Sum("points"))["s"] or 0

@transaction.atomic
def register_user_for_event(user: User, event: EventSlot) -> Registration:
    """Atomic capacity enforcement + waitlist."""
    if timezone.now() > event.end_at:
        raise ValueError("Event already ended.")
    # Lock row
    ev = EventSlot.objects.select_for_update().get(pk=event.pk)
    status = "registered"
    if ev.registered_count >= ev.max_participants:
        status = "waitlisted"
    reg, created = Registration.objects.get_or_create(event=ev, user=user, defaults={"status": status})
    if not created:
        raise ValueError("Already registered for this event.")
    if status == "registered":
        ev.registered_count = F("registered_count") + 1
        ev.save(update_fields=["registered_count"])
    return reg

@transaction.atomic
def cancel_registration(reg: Registration):
    ev = EventSlot.objects.select_for_update().get(pk=reg.event_id)
    was_registered = (reg.status == "registered")
    reg.status = "canceled"
    reg.save(update_fields=["status"])
    if was_registered:
        ev.registered_count = F("registered_count") - 1
        ev.save(update_fields=["registered_count"])
        # promote first waitlisted
        wl = (Registration.objects
              .select_for_update()
              .filter(event=ev, status="waitlisted")
              .order_by("created_at")
              .first())
        if wl:
            wl.status = "registered"
            wl.save(update_fields=["status"])
            ev.registered_count = F("registered_count") + 1
            ev.save(update_fields=["registered_count"])

@transaction.atomic
def approve_submission(sub: Submission, by_user: User, comment: str = ""):
    if not sub.can_verify(by_user):
        raise PermissionError("Not allowed to approve this submission.")
    if sub.status == "approved":
        return  # idempotent, ledger enforced below
    sub.status = "approved"
    sub.verified_by = by_user
    sub.verified_at = timezone.now()
    sub.comment = (comment or sub.comment)
    sub.save()

    # create ledger exactly once per submission
    PointLedger.objects.create(
        user=sub.student.user,
        activity=sub.activity,
        points=sub.activity.points,
        source="submission",
        reference_id=f"submission:{sub.id}",
    )

@transaction.atomic
def reject_submission(sub: Submission, by_user: User, comment: str = ""):
    if not sub.can_verify(by_user):
        raise PermissionError("Not allowed to reject this submission.")
    sub.status = "rejected"
    sub.verified_by = by_user
    sub.verified_at = timezone.now()
    sub.comment = (comment or sub.comment)
    sub.save()

@transaction.atomic
def redeem_reward(user: User, reward: Reward) -> Redemption:
    # stock check
    if not reward.active:
        raise ValueError("Reward not active.")
    if reward.stock is not None and reward.stock <= 0:
        raise ValueError("Reward out of stock.")

    # sufficient points?
    pts = total_points(user)
    spent = (Redemption.objects.filter(user=user)
             .exclude(status="canceled")
             .aggregate(x=models.Sum("reward__points_cost"))["x"] or 0)
    available = pts - spent
    if available < reward.points_cost:
        raise ValueError("Insufficient points.")

    # create redemption
    red = Redemption.objects.create(user=user, reward=reward, status="pending")
    # decrement stock
    if reward.stock is not None:
        Reward.objects.filter(pk=reward.pk, stock__gt=0).update(stock=F("stock") - 1)
        reward.refresh_from_db()
        if reward.stock < 0:
            raise ValueError("Race: stock went negative")
    return red
