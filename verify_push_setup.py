#!/usr/bin/env python
"""
Pre-Flight Checklist: Verify Web Push Setup

This script checks that all necessary files, configurations, and dependencies
are in place before you start using the Web Push notification system.

Usage:
    python verify_push_setup.py
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'future_leaders_academy.settings')
django.setup()

from django.conf import settings
import importlib

class PreFlightCheck:
    def __init__(self):
        self.checks_passed = 0
        self.checks_failed = 0
        self.checks_warning = 0

    def check(self, name, condition, error_msg=""):
        """Check a condition and track result"""
        status = "✓" if condition else "✗"
        symbol = "✓" if condition else "✗"
        print(f"  {symbol} {name}")
        
        if condition:
            self.checks_passed += 1
        else:
            self.checks_failed += 1
            if error_msg:
                print(f"      └─ {error_msg}")
        
        return condition

    def warning(self, name, msg):
        """Log a warning"""
        print(f"  ⚠ {name}")
        print(f"      └─ {msg}")
        self.checks_warning += 1

    def section(self, title):
        """Print a section header"""
        print(f"\n{'='*70}")
        print(f" {title}")
        print('='*70)

    def run_all_checks(self):
        """Run all verification checks"""
        
        self.section("1. PYTHON DEPENDENCIES")
        self.check_dependencies()
        
        self.section("2. FILE STRUCTURE")
        self.check_files()
        
        self.section("3. DJANGO CONFIGURATION")
        self.check_django_config()
        
        self.section("4. DATABASE")
        self.check_database()
        
        self.section("5. VAPID CONFIGURATION")
        self.check_vapid_config()
        
        self.section("6. STATIC FILES")
        self.check_static_files()
        
        self.print_summary()

    def check_dependencies(self):
        """Check required Python packages"""
        packages = {
            'django': 'Django',
            'pywebpush': 'pywebpush',
            'cryptography': 'cryptography (required by pywebpush)',
        }
        
        for module, display_name in packages.items():
            try:
                importlib.import_module(module)
                self.check(f"{display_name} installed", True)
            except ImportError:
                self.check(f"{display_name} installed", False, 
                          f"Run: pip install {module}")

    def check_files(self):
        """Check required files exist"""
        base_path = os.path.dirname(os.path.abspath(__file__))
        
        files_to_check = {
            'portal/models.py': 'Models file',
            'portal/views.py': 'Views file',
            'portal/utils.py': 'Utils file',
            'portal/signals.py': 'Signals file',
            'portal/urls.py': 'URLs file',
            'portal/static/portal/sw.js': 'Service Worker',
            'portal/static/portal/push-notifications.js': 'Push Notification Manager',
            'portal/migrations/0070_add_push_subscription_model.py': 'Migration file',
            'generate_vapid_keys.py': 'VAPID key generator',
            'test_push_notifications.py': 'Test script',
            'WEB_PUSH_SETUP_GUIDE.md': 'Setup guide',
        }
        
        for file_path, description in files_to_check.items():
            full_path = os.path.join(base_path, file_path)
            exists = os.path.exists(full_path)
            self.check(f"{description} exists", exists, f"Missing: {file_path}")

    def check_django_config(self):
        """Check Django settings"""
        # Check VAPID settings are defined
        has_public = hasattr(settings, 'VAPID_PUBLIC_KEY')
        has_private = hasattr(settings, 'VAPID_PRIVATE_KEY')
        has_email = hasattr(settings, 'VAPID_ADMIN_EMAIL')
        
        self.check("VAPID_PUBLIC_KEY setting defined", has_public,
                  "Add to settings.py: VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')")
        self.check("VAPID_PRIVATE_KEY setting defined", has_private,
                  "Add to settings.py: VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')")
        self.check("VAPID_ADMIN_EMAIL setting defined", has_email,
                  "Add to settings.py: VAPID_ADMIN_EMAIL = os.environ.get('VAPID_ADMIN_EMAIL', '')")
        
        # Check portal app is installed
        installed = 'portal' in settings.INSTALLED_APPS
        self.check("'portal' app installed", installed)

    def check_database(self):
        """Check database tables"""
        from django.db import connection
        
        with connection.cursor() as cursor:
            # Check if PushSubscription table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='portal_pushsubscription'
            """)
            table_exists = cursor.fetchone() is not None
        
        self.check("PushSubscription table exists", table_exists,
                  "Run: python manage.py migrate")
        
        if table_exists:
            # Check if auth_user table exists
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM auth_user
                """)
                user_count = cursor.fetchone()[0]
            
            self.check(f"Database has users ({user_count} found)", user_count > 0,
                      "Create a user account first")

    def check_vapid_config(self):
        """Check VAPID keys are configured"""
        public_key = getattr(settings, 'VAPID_PUBLIC_KEY', '')
        private_key = getattr(settings, 'VAPID_PRIVATE_KEY', '')
        admin_email = getattr(settings, 'VAPID_ADMIN_EMAIL', '')
        
        if public_key and private_key:
            self.check("VAPID keys configured", True)
            self.check("VAPID public key looks valid", public_key.startswith('BA'),
                      f"Public key should start with 'BA', got: {public_key[:10]}...")
            self.check("VAPID private key configured", len(private_key) > 20,
                      f"Private key seems too short: {len(private_key)} chars")
        else:
            self.check("VAPID keys configured", False,
                      "Run: python generate_vapid_keys.py")
        
        if admin_email:
            self.check("Admin email configured", True)
        else:
            self.warning("Admin email", 
                        "Not configured. Push service may send warnings.")

    def check_static_files(self):
        """Check static files are in place"""
        base_path = os.path.dirname(os.path.abspath(__file__))
        
        static_files = {
            'portal/static/portal/sw.js': 'Service Worker',
            'portal/static/portal/push-notifications.js': 'Push Notifications JS',
        }
        
        for file_path, description in static_files.items():
            full_path = os.path.join(base_path, file_path)
            exists = os.path.exists(full_path)
            self.check(f"{description} exists", exists, f"Missing: {file_path}")
            
            if exists:
                # Check file has content
                with open(full_path, 'r') as f:
                    content = f.read()
                has_content = len(content) > 100
                self.check(f"{description} has content", has_content)

    def print_summary(self):
        """Print summary and recommendations"""
        self.section("SUMMARY")
        
        print(f"\n✓ Passed:   {self.checks_passed}")
        print(f"✗ Failed:   {self.checks_failed}")
        print(f"⚠ Warnings: {self.checks_warning}")
        
        total = self.checks_passed + self.checks_failed + self.checks_warning
        print(f"\nTotal:     {total} checks\n")
        
        if self.checks_failed == 0:
            print("✅ All checks passed! You're ready to use Web Push notifications.\n")
            print("Next steps:")
            print("1. Run: python generate_vapid_keys.py")
            print("2. Set environment variables (copy from step 1)")
            print("3. Run: python manage.py migrate")
            print("4. Run: python manage.py runserver")
            print("5. Test: python test_push_notifications.py")
        else:
            print("❌ Some checks failed. Please fix the issues above.\n")
            print("Common fixes:")
            print("- Install missing packages: pip install -r requirements.txt")
            print("- Run migrations: python manage.py migrate")
            print("- Generate VAPID keys: python generate_vapid_keys.py")
            print("- Set environment variables from VAPID key output")
        
        if self.checks_warning > 0:
            print("\n⚠️  Address the warnings above for optimal setup.")
        
        return self.checks_failed == 0

def main():
    print("\n" + "="*70)
    print(" WEB PUSH NOTIFICATION SYSTEM - PRE-FLIGHT CHECK")
    print("="*70)
    
    checker = PreFlightCheck()
    success = checker.run_all_checks()
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
