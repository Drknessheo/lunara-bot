#!/usr/bin/env python
"""
CLI tool for managing encryption key rotation
Usage:
    python manage_keys.py --status
    python manage_keys.py --rotate-now
    python manage_keys.py --verify-backup
    python manage_keys.py --restore-backup [backup_path]
"""

import os
import sys
import argparse
from datetime import datetime
import json
from flask import Flask
from app.services.key_rotation_service import KeyRotationService
from app.services.key_backup_service import KeyBackupService
from app.config_files.encryption_config import ENCRYPTION_KEY_ENV

def create_app():
    """Create minimal Flask app for context"""
    app = Flask(__name__)
    app.config['INSTANCE_PATH'] = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'instance'
    )
    return app

def get_key_services(app):
    """Initialize key rotation and backup services"""
    key_file_path = os.path.join(app.config['INSTANCE_PATH'], 'encryption_keys.json')
    backup_dir = os.path.join(app.config['INSTANCE_PATH'], 'key_backups')
    
    rotation_service = KeyRotationService(key_file_path)
    backup_service = KeyBackupService(backup_dir)
    
    return rotation_service, backup_service

def check_status(rotation_service):
    """Check current key rotation status"""
    try:
        data = rotation_service._read_key_file()
        last_rotation = datetime.fromisoformat(data['last_rotation'])
        next_rotation = datetime.fromisoformat(data['next_rotation'])
        
        print("\nKey Rotation Status:")
        print("-" * 50)
        print(f"Last rotation: {last_rotation.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Next scheduled rotation: {next_rotation.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Days until next rotation: {(next_rotation - datetime.now()).days}")
        print(f"Previous key available: {'Yes' if data.get('previous_key') else 'No'}")
        print("-" * 50)
        
    except Exception as e:
        print(f"Error checking status: {str(e)}")
        sys.exit(1)

def rotate_keys_now(rotation_service):
    """Perform immediate key rotation"""
    try:
        print("\nInitiating manual key rotation...")
        rotation_service.rotate_keys()
        print("Key rotation completed successfully!")
        
    except Exception as e:
        print(f"Error during key rotation: {str(e)}")
        sys.exit(1)

def verify_backups(backup_service):
    """Verify all key backups"""
    try:
        print("\nVerifying key backups...")
        backup_files = [f for f in os.listdir(backup_service.backup_dir) 
                       if f.endswith('.bak')]
        
        for backup_file in backup_files:
            backup_path = os.path.join(backup_service.backup_dir, backup_file)
            is_valid = backup_service.verify_backup(backup_path)
            
            print(f"\nBackup: {backup_file}")
            print(f"Status: {'Valid' if is_valid else 'INVALID'}")
            
            if not is_valid:
                print("WARNING: Backup verification failed!")
        
    except Exception as e:
        print(f"Error verifying backups: {str(e)}")
        sys.exit(1)

def restore_backup(backup_service, backup_path, rotation_service):
    """Restore from a specific backup"""
    try:
        print(f"\nAttempting to restore from backup: {backup_path}")
        
        if not os.path.exists(backup_path):
            print("Error: Backup file not found!")
            sys.exit(1)
        
        if backup_service.restore_backup(backup_path, rotation_service.key_file_path):
            print("Backup restored successfully!")
        else:
            print("Error: Backup restoration failed!")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error restoring backup: {str(e)}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Encryption Key Management CLI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--status', action='store_true', help='Check key rotation status')
    group.add_argument('--rotate-now', action='store_true', help='Perform immediate key rotation')
    group.add_argument('--verify-backup', action='store_true', help='Verify all key backups')
    group.add_argument('--restore-backup', type=str, help='Restore from specific backup file')
    
    args = parser.parse_args()
    
    # Create minimal Flask app and get services
    app = create_app()
    with app.app_context():
        rotation_service, backup_service = get_key_services(app)
        
        if args.status:
            check_status(rotation_service)
        elif args.rotate_now:
            rotate_keys_now(rotation_service)
        elif args.verify_backup:
            verify_backups(backup_service)
        elif args.restore_backup:
            restore_backup(backup_service, args.restore_backup, rotation_service)

if __name__ == '__main__':
    main()
