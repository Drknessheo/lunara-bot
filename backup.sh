#!/data/data/com.termux/files/usr/bin/bash

# Load environment variables
source "$(dirname "$0")/.env"

# --- Configuration ---
BOT_DIR="/data/data/com.termux/files/home/lunara-bot"
GDRIVE_REMOTE="$GDRIVE_REMOTE_NAME" # Fetched from .env
GDRIVE_BACKUP_PATH="LunaraBotBackups"

if [ -z "$GDRIVE_REMOTE" ]; then
    echo "Error: GDRIVE_REMOTE_NAME is not set in .env file. Exiting."
    exit 1
fi

echo "--- Starting Lunessa Shi'ra Gork Backup ---"

# 1. Sync current files to a dedicated folder on Google Drive
echo "Syncing current files to Google Drive..."
rclone sync "$BOT_DIR" "$GDRIVE_REMOTE:$GDRIVE_BACKUP_PATH/current_files/" --exclude ".git/**" --exclude "venv314/**" --exclude "*.pyc" --exclude "__pycache__/**" --exclude ".*" -v

# 2. Create a timestamped zip archive of the entire folder
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
ZIP_FILE="$GDRIVE_BACKUP_PATH/archives/lunara-bot-backup-$TIMESTAMP.zip"
echo "Creating zip archive and uploading to $GDRIVE_REMOTE:$ZIP_FILE..."
zip -r - "$BOT_DIR" -x ".git/*" "venv314/*" "*.pyc" "__pycache__/*" ".*" | rclone rcat "$GDRIVE_REMOTE:$ZIP_FILE"

# 3. Keep only the latest 7 zipped versions on Google Drive
echo "Cleaning up old archives (keeping latest 7)..."
rclone delete --min-age 7d "$GDRIVE_REMOTE:$GDRIVE_BACKUP_PATH/archives/" -v

echo "--- Backup Complete ---"