from django.apps import AppConfig


class PortalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'portal'

    def ready(self):
        from . import signals  # noqa: F401
        from django.conf import settings
        # One-time startup check: confirms whether VAPID env vars are actually
        # loaded on this environment (a common cause of silent push failures).
        print(
            f"VAPID check on startup -> public_key set: {bool(settings.VAPID_PUBLIC_KEY)}, "
            f"private_key set: {bool(settings.VAPID_PRIVATE_KEY)}",
            flush=True,
        )
