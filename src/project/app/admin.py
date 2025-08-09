from django.contrib import admin
from .models import Student

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'pnr', 'department', 'semester')
    search_fields = ('user__username', 'user__email', 'pnr', 'department')
    list_filter = ('department', 'semester')


# app/admin.py (append)
from django.contrib import admin
from .models import Activity, EventSlot, Registration, Submission, PointLedger, Reward, Redemption, BadgeThreshold

@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("title","tier","requires_proof","monthly_cap_per_student","created_at")
    search_fields = ("title",)
    list_filter = ("tier","requires_proof")

@admin.register(EventSlot)
class EventSlotAdmin(admin.ModelAdmin):
    list_display = ("activity","start_at","end_at","max_participants","registered_count","location")
    list_filter = ("activity","start_at")
    search_fields = ("activity__title","location")

@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("event","user","status","created_at")
    list_filter = ("status","event__activity")

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("student","activity","status","verified_by","verified_at","created_at")
    list_filter = ("status","activity")
    search_fields = ("student__user__email","activity__title")
    actions = ["approve_selected","reject_selected"]
    def approve_selected(self, request, queryset):
        for s in queryset:
            try: 
                from .models import approve_submission
                approve_submission(s, request.user)
            except Exception:
                pass
    def reject_selected(self, request, queryset):
        for s in queryset:
            try:
                from .models import reject_submission
                reject_submission(s, request.user)
            except Exception:
                pass

@admin.register(PointLedger)
class PointLedgerAdmin(admin.ModelAdmin):
    list_display = ("user","activity","points","source","reference_id","created_at")
    list_filter = ("source","activity")
    search_fields = ("user__email","reference_id")

@admin.register(Reward)
class RewardAdmin(admin.ModelAdmin):
    list_display = ("title","points_cost","stock","active")
    list_filter = ("active",)
    search_fields = ("title",)

@admin.register(Redemption)
class RedemptionAdmin(admin.ModelAdmin):
    list_display = ("user","reward","status","fulfilled_by","fulfilled_at","created_at")
    list_filter = ("status",)
    search_fields = ("user__email","reward__title")

@admin.register(BadgeThreshold)
class BadgeThresholdAdmin(admin.ModelAdmin):
    list_display = ("code","name","percent_of_potential","active")
    list_filter = ("active",)
