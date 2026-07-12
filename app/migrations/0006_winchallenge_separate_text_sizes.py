import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0005_winchallenge_overlay_dimensions"),
    ]

    operations = [
        migrations.AddField(
            model_name="winchallenge",
            name="label_text_size",
            field=models.PositiveSmallIntegerField(
                default=10,
                validators=[
                    django.core.validators.MinValueValidator(6),
                    django.core.validators.MaxValueValidator(32),
                ],
            ),
        ),
        migrations.AddField(
            model_name="winchallenge",
            name="title_text_size",
            field=models.PositiveSmallIntegerField(
                default=20,
                validators=[
                    django.core.validators.MinValueValidator(10),
                    django.core.validators.MaxValueValidator(64),
                ],
            ),
        ),
        migrations.AddField(
            model_name="winchallenge",
            name="total_text_size",
            field=models.PositiveSmallIntegerField(
                default=14,
                validators=[
                    django.core.validators.MinValueValidator(8),
                    django.core.validators.MaxValueValidator(40),
                ],
            ),
        ),
        migrations.AddField(
            model_name="winchallenge",
            name="game_text_size",
            field=models.PositiveSmallIntegerField(
                default=15,
                validators=[
                    django.core.validators.MinValueValidator(8),
                    django.core.validators.MaxValueValidator(48),
                ],
            ),
        ),
        migrations.AddField(
            model_name="winchallenge",
            name="game_score_text_size",
            field=models.PositiveSmallIntegerField(
                default=12,
                validators=[
                    django.core.validators.MinValueValidator(8),
                    django.core.validators.MaxValueValidator(36),
                ],
            ),
        ),
        migrations.AddField(
            model_name="winchallenge",
            name="pager_text_size",
            field=models.PositiveSmallIntegerField(
                default=12,
                validators=[
                    django.core.validators.MinValueValidator(8),
                    django.core.validators.MaxValueValidator(32),
                ],
            ),
        ),
    ]
