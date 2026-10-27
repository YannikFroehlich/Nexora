import uuid

from django.db import migrations, models

CONTROLLABLE_MODELS = ("scoreoverlay", "timeroverlay", "winchallenge")


def assign_control_tokens(apps, schema_editor):
    for model_name in CONTROLLABLE_MODELS:
        model = apps.get_model("app", model_name)
        for pk in model.objects.values_list("pk", flat=True):
            model.objects.filter(pk=pk).update(control_token=uuid.uuid4())


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0018_winchallenge_design_options"),
    ]

    operations = [
        *(
            migrations.AddField(
                model_name=model_name,
                name="control_token",
                field=models.UUIDField(editable=False, null=True),
            )
            for model_name in CONTROLLABLE_MODELS
        ),
        migrations.RunPython(assign_control_tokens, migrations.RunPython.noop),
        *(
            migrations.AlterField(
                model_name=model_name,
                name="control_token",
                field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
            )
            for model_name in CONTROLLABLE_MODELS
        ),
    ]
