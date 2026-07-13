import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0006_winchallenge_separate_text_sizes"),
    ]

    operations = [
        migrations.AddField(
            model_name="winchallenge",
            name="page_interval_seconds",
            field=models.PositiveSmallIntegerField(
                default=4,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(60),
                ],
            ),
        ),
    ]
