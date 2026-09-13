from django.apps import AppConfig


class PortalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'portal'

    def ready(self):
        from . import signals  # noqa: F401
        from django.conf import settings
        from django.db.models.signals import post_migrate

        # One-time startup check: confirms whether VAPID env vars are actually
        # loaded on this environment (a common cause of silent push failures).
        print(
            f"VAPID check on startup -> public_key set: {bool(settings.VAPID_PUBLIC_KEY)}, "
            f"private_key set: {bool(settings.VAPID_PRIVATE_KEY)}",
            flush=True,
        )

        def auto_seed_books_after_migration(sender, **kwargs):
            try:
                from .models import BookItem
                if BookItem.objects.count() == 0:
                    from .management.commands.seed_book_list import Command as SeedBookListCommand
                    SeedBookListCommand().handle()
                    print("Auto-seeded BookItem records after migration.", flush=True)
            except Exception:
                pass

        post_migrate.connect(auto_seed_books_after_migration, sender=self)
