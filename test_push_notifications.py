#!/usr/bin/env python
"""
Test Web Push Notification System

This script helps you test the Web Push notification system by:
1. Verifying VAPID configuration
2. Checking database subscriptions
3. Sending test notifications to users

USAGE:
    python test_push_notifications.py              # Interactive mode
    python test_push_notifications.py --verify    # Just verify config
    python test_push_notifications.py --send      # Send test to all users
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'future_leaders_academy.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.conf import settings
from portal.models import PushSubscription, Notification
from portal.utils import send_push_notification_to_user
import argparse

User = get_user_model()

class PushNotificationTester:
    def __init__(self):
        self.vapid_public = settings.VAPID_PUBLIC_KEY
        self.vapid_private = settings.VAPID_PRIVATE_KEY
        self.vapid_email = settings.VAPID_ADMIN_EMAIL

    def verify_configuration(self):
        """Verify VAPID configuration is set"""
        print("\n" + "="*70)
        print("VAPID CONFIGURATION CHECK")
        print("="*70)
        
        print(f"✓ VAPID_PUBLIC_KEY: {'SET' if self.vapid_public else '❌ NOT SET'}")
        print(f"✓ VAPID_PRIVATE_KEY: {'SET' if self.vapid_private else '❌ NOT SET'}")
        print(f"✓ VAPID_ADMIN_EMAIL: {self.vapid_email}")
        
        if not self.vapid_public or not self.vapid_private:
            print("\n⚠️  Missing VAPID keys!")
            print("Run: python generate_vapid_keys.py")
            return False
        
        print("\n✓ Configuration is valid!")
        return True

    def check_subscriptions(self):
        """Check for active push subscriptions"""
        print("\n" + "="*70)
        print("ACTIVE PUSH SUBSCRIPTIONS")
        print("="*70)
        
        total = PushSubscription.objects.count()
        active = PushSubscription.objects.filter(is_active=True).count()
        inactive = PushSubscription.objects.filter(is_active=False).count()
        
        print(f"Total subscriptions: {total}")
        print(f"  ✓ Active: {active}")
        print(f"  ✗ Inactive: {inactive}")
        
        if active == 0:
            print("\n⚠️  No active subscriptions found!")
            print("Have users click 'Enable Notifications' in the app first.")
            return False
        
        print(f"\n✓ Found {active} active subscriptions")
        
        # Show sample subscriptions
        subscriptions = PushSubscription.objects.filter(is_active=True)[:3]
        if subscriptions:
            print("\nSample subscriptions:")
            for sub in subscriptions:
                endpoint = sub.endpoint[:50] + "..." if len(sub.endpoint) > 50 else sub.endpoint
                print(f"  - {sub.user.username}: {endpoint}")
        
        return True

    def list_users(self):
        """List all users with subscriptions"""
        print("\n" + "="*70)
        print("USERS WITH ACTIVE SUBSCRIPTIONS")
        print("="*70)
        
        users_with_subs = User.objects.filter(push_subscriptions__is_active=True).distinct()
        
        if not users_with_subs.exists():
            print("No users with active subscriptions")
            return
        
        for user in users_with_subs:
            sub_count = user.push_subscriptions.filter(is_active=True).count()
            print(f"  ✓ {user.username} ({user.get_full_name() or 'No name'}) - {sub_count} subscription(s)")

    def send_test_notification(self, username=None):
        """Send a test notification to a specific user or first available"""
        print("\n" + "="*70)
        print("SEND TEST NOTIFICATION")
        print("="*70)
        
        if username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                print(f"❌ User '{username}' not found")
                return False
        else:
            # Find first user with active subscription
            user = User.objects.filter(push_subscriptions__is_active=True).first()
            if not user:
                print("❌ No users with active subscriptions found")
                return False
        
        print(f"Sending test notification to: {user.username}")
        
        try:
            successful, failed = send_push_notification_to_user(
                user=user,
                title="🎓 Test Notification",
                body="This is a test Web Push notification from Future Leaders Academy!",
                link="/inbox/",
                tag="test-notification",
            )
            
            print(f"✓ Sent successfully to {successful} device(s)")
            if failed > 0:
                print(f"⚠️  Failed to send to {failed} device(s)")
            
            return True
        except Exception as e:
            print(f"❌ Error sending notification: {e}")
            import traceback
            traceback.print_exc()
            return False

    def create_test_notification(self, username=None):
        """Create a database Notification object (triggers automatic push)"""
        print("\n" + "="*70)
        print("CREATE TEST DATABASE NOTIFICATION")
        print("="*70)
        
        if username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                print(f"❌ User '{username}' not found")
                return False
        else:
            user = User.objects.filter(push_subscriptions__is_active=True).first()
            if not user:
                print("❌ No users with active subscriptions found")
                return False
        
        print(f"Creating notification for: {user.username}")
        
        try:
            notification = Notification.objects.create(
                recipient=user,
                title="📢 Test System Notification",
                message="This notification was created in the database and triggered an automatic push!",
                link="/inbox/",
            )
            print(f"✓ Notification created (ID: {notification.id})")
            print("  Push should be sent automatically by signal handler")
            return True
        except Exception as e:
            print(f"❌ Error creating notification: {e}")
            import traceback
            traceback.print_exc()
            return False

    def interactive_menu(self):
        """Interactive menu for testing"""
        while True:
            print("\n" + "="*70)
            print("WEB PUSH NOTIFICATION TESTER - INTERACTIVE MENU")
            print("="*70)
            print("1. Verify VAPID Configuration")
            print("2. Check Active Subscriptions")
            print("3. List Users with Subscriptions")
            print("4. Send Test Push Notification")
            print("5. Create Test Database Notification")
            print("6. Run All Checks")
            print("0. Exit")
            print("="*70)
            
            choice = input("Select option (0-6): ").strip()
            
            if choice == '1':
                self.verify_configuration()
            elif choice == '2':
                self.check_subscriptions()
            elif choice == '3':
                self.list_users()
            elif choice == '4':
                username = input("Enter username (or press Enter for first available): ").strip()
                self.send_test_notification(username or None)
            elif choice == '5':
                username = input("Enter username (or press Enter for first available): ").strip()
                self.create_test_notification(username or None)
            elif choice == '6':
                self.verify_configuration()
                self.check_subscriptions()
                self.list_users()
                print("\n✓ All checks completed!")
            elif choice == '0':
                print("Exiting...")
                break
            else:
                print("❌ Invalid option")

def main():
    parser = argparse.ArgumentParser(description='Test Web Push Notification System')
    parser.add_argument('--verify', action='store_true', help='Verify VAPID configuration only')
    parser.add_argument('--send', action='store_true', help='Send test notification to all users')
    parser.add_argument('--user', type=str, help='Target username for notification')
    parser.add_argument('--create', action='store_true', help='Create database notification (triggers push)')
    
    args = parser.parse_args()
    
    tester = PushNotificationTester()
    
    if args.verify:
        tester.verify_configuration()
    elif args.send:
        tester.send_test_notification(args.user)
    elif args.create:
        tester.create_test_notification(args.user)
    else:
        # Interactive mode by default
        tester.interactive_menu()

if __name__ == '__main__':
    main()
