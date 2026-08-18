from django.core.management.base import BaseCommand

from app import twitch_api
from app.models import TwitchConnection


class Command(BaseCommand):
    help = "Validate every stored Twitch OAuth token (schedule hourly in production)."

    def handle(self, *args, **options):
        checked = 0
        invalid = 0
        for connection in TwitchConnection.objects.exclude(access_token="").iterator():
            checked += 1
            try:
                twitch_api.validate_connection(connection, force=True)
            except twitch_api.TwitchAPIError as error:
                invalid += 1
                self.stderr.write(f"{connection.pk}: {error}")
        self.stdout.write(
            self.style.SUCCESS(f"Validated {checked} Twitch token(s); {invalid} invalid.")
        )
