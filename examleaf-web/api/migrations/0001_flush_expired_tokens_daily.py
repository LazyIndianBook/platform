"""Schedules api.tasks.flush_expired_tokens at 04:30 (IST) in celery beat's tables; editable in the admin."""

from django.db import migrations

NAME = "flush-expired-jwt"


def schedule(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    crontab, _ = CrontabSchedule.objects.get_or_create(
        minute="30", hour="4", day_of_week="*", day_of_month="*", month_of_year="*", timezone="Asia/Kolkata"
    )
    PeriodicTask.objects.get_or_create(name=NAME, defaults={"task": "api.tasks.flush_expired_tokens", "crontab": crontab})


def unschedule(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=NAME).delete()


class Migration(migrations.Migration):
    dependencies = [("django_celery_beat", "0020_periodictask_beat_periodic_enabled_idx")]
    operations = [migrations.RunPython(schedule, unschedule)]
