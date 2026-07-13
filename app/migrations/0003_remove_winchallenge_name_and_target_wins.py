from django.db import migrations


def copy_name_to_empty_title(apps, schema_editor):
    win_challenge = apps.get_model("app", "WinChallenge")

    for challenge in win_challenge.objects.filter(title=""):
        challenge.title = challenge.name
        challenge.save(update_fields=["title"])


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0002_winchallengegame_target_wins"),
    ]

    operations = [
        migrations.RunPython(copy_name_to_empty_title, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="winchallenge",
            name="name",
        ),
        migrations.RemoveField(
            model_name="winchallenge",
            name="target_wins",
        ),
        migrations.RemoveField(
            model_name="winchallenge",
            name="show_progress_bar",
        ),
    ]
