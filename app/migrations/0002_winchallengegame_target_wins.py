import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0001_winchallenge"),
    ]

    operations = [
        migrations.AddField(
            model_name="winchallengegame",
            name="target_wins",
            field=models.PositiveIntegerField(
                default=10,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(99999),
                ],
            ),
        ),
    ]
