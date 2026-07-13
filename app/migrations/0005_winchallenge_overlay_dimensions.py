import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0004_winchallenge_text_size_item_spacing"),
    ]

    operations = [
        migrations.AddField(
            model_name="winchallenge",
            name="overlay_width",
            field=models.PositiveSmallIntegerField(
                default=460,
                validators=[
                    django.core.validators.MinValueValidator(260),
                    django.core.validators.MaxValueValidator(1200),
                ],
            ),
        ),
        migrations.AddField(
            model_name="winchallenge",
            name="overlay_height",
            field=models.PositiveSmallIntegerField(
                default=0,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(1000),
                ],
            ),
        ),
    ]
