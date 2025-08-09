# app/tests.py
import pytest
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

from .models import (
    Student, Activity, EventSlot, register_user_for_event, cancel_registration,
    Submission, approve_submission, PointLedger, Reward, redeem_reward, total_points
)

pytestmark = pytest.mark.django_db

def make_user(email="u@example.com", name="User", staff=False, role="student"):
    u = User.objects.create_user(username=email, email=email, password="pass123", first_name=name, is_staff=staff)
    Student.objects.create(user=u, phone="1", pnr=email, department="CSE", semester="1", role=role)
    return u

def test_event_capacity_register_and_waitlist():
    u1 = make_user("a@a.com")
    u2 = make_user("b@b.com")
    act = Activity.objects.create(title="Clean Up", tier=2, requires_proof=False)
    ev = EventSlot.objects.create(activity=act, start_at=timezone.now(), end_at=timezone.now()+timezone.timedelta(hours=1),
                                  max_participants=1, registered_count=0, location="Lawn")
    r1 = register_user_for_event(u1, ev)
    assert r1.status == "registered"
    r2 = register_user_for_event(u2, ev)
    assert r2.status == "waitlisted"

    cancel_registration(r1)
    r2.refresh_from_db()
    ev.refresh_from_db()
    assert r2.status == "registered"
    assert ev.registered_count == 1

def test_submission_approval_awards_points_once():
    student_user = make_user("s@s.com")
    verifier = make_user("v@v.com", staff=False, role="volunteer")
    act = Activity.objects.create(title="Talk", tier=8, requires_proof=True)
    sub = Submission.objects.create(
        student=student_user.student, activity=act,
        evidence_url="https://example.com/proof"
    )
    approve_submission(sub, verifier)
    assert sub.status == "approved"
    assert PointLedger.objects.count() == 1
    # Approving again doesn't duplicate points
    approve_submission(sub, verifier)
    assert PointLedger.objects.count() == 1

def test_reward_redemption_points_guard():
    u = make_user("p@p.com")
    act = Activity.objects.create(title="Poster", tier=5, requires_proof=False)
    # grant some points via manual ledger
    PointLedger.objects.create(user=u, activity=act, points=10, source="manual", reference_id="seed:1")
    reward = Reward.objects.create(title="Mug", points_cost=8, stock=1, active=True)
    red = redeem_reward(u, reward)
    assert red.status == "pending"
    # stock decremented
    reward.refresh_from_db()
    assert reward.stock == 0
    # second redemption should fail
    with pytest.raises(ValueError):
        redeem_reward(u, reward)

def test_total_points_sum():
    u = make_user("t@t.com")
    a2 = Activity.objects.create(title="T2", tier=2, requires_proof=False)
    a5 = Activity.objects.create(title="T5", tier=5, requires_proof=False)
    PointLedger.objects.create(user=u, activity=a2, points=2, source="manual", reference_id="m1")
    PointLedger.objects.create(user=u, activity=a5, points=5, source="manual", reference_id="m2")
    assert total_points(u) == 7
