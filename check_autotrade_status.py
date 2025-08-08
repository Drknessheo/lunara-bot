import config
import db

admin_user_id = config.ADMIN_USER_ID
autotrade_enabled = db.get_autotrade_status(admin_user_id)

print(f"Autotrade status for ADMIN_USER_ID ({admin_user_id}): {autotrade_enabled}")
