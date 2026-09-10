# Generate VAPID Keys for Web Push Notifications
#
# This script generates the required VAPID keys for your Web Push system.
# Run this script once and save the output securely.
#
# USAGE:
#   python generate_vapid_keys.py

import json
import base64
from py_vapid import Vapid01
from cryptography.hazmat.primitives import serialization

def generate_keys():
    """Generate VAPID key pair"""
    # Create a new Vapid01 instance and generate keys
    vapid = Vapid01()
    vapid.generate_keys()
    
    # Extract public key: X962 uncompressed point format (0x04 + X + Y)
    public_raw = vapid.public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    
    # Extract private key scalar value (32 bytes for P256 / NIST P-256)
    # Get the private numbers and convert to bytes
    private_numbers = vapid.private_key.private_numbers()
    private_scalar = private_numbers.private_value
    private_raw = private_scalar.to_bytes(32, byteorder='big')
    
    # Encode as base64url (standard VAPID format - without padding)
    public_key = base64.urlsafe_b64encode(public_raw).decode('utf-8').rstrip('=')
    private_key = base64.urlsafe_b64encode(private_raw).decode('utf-8').rstrip('=')
    
    return {
        'public_key': public_key,
        'private_key': private_key,
    }

def print_keys(keys):
    """Print keys in a user-friendly format"""
    print("\n" + "="*80)
    print("VAPID KEYS GENERATED SUCCESSFULLY")
    print("="*80)
    print("\n📋 Add these to your environment variables (.env or hosting provider):\n")
    
    print("VAPID_PUBLIC_KEY={}".format(keys['public_key']))
    print("VAPID_PRIVATE_KEY={}".format(keys['private_key']))
    print("VAPID_ADMIN_EMAIL=admin@futureleadersacademy.local\n")
    
    print("="*80)
    print("\n⚠️  SECURITY REMINDERS:\n")
    print("1. NEVER commit VAPID_PRIVATE_KEY to version control")
    print("2. Store PRIVATE_KEY in .env or secure environment variable system")
    print("3. Share only PUBLIC_KEY with clients")
    print("4. The admin email is used for push service communication\n")
    
    print("="*80)
    print("\n💾 JSON Format (for .env file or easy copying):\n")
    print(json.dumps(keys, indent=2))
    print("\n" + "="*80 + "\n")

if __name__ == '__main__':
    keys = generate_keys()
    print_keys(keys)
