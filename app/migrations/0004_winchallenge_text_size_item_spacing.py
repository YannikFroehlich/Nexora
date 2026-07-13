import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0003_remove_winchallenge_name_and_target_wins"),
    ]

    operations = [
        migrations.AddField(
            model_name="winchallenge",
            name="text_size",
            field=models.PositiveSmallIntegerField(
                default=16,
                validators=[
                    django.core.validators.MinValueValidator(10),
                    django.core.validators.MaxValueValidator(36),
                ],
            ),
        ),
        migrations.AddField(
            model_name="winchallenge",
            name="item_spacing",
            field=models.PositiveSmallIntegerField(
                default=9,
                validators=[
                    django.core.validators.MinValueValidator(4),
                    django.core.validators.MaxValueValidator(28),
                ],
            ),
        ),
    ]
