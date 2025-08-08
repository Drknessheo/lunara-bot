from functools import wraps
import db

# Decorator to restrict command to users with a required tier (e.g., 'PREMIUM')
def require_tier(required_tier):
    def decorator(func):
        @wraps(func)
        async def wrapper(update, context, *args, **kwargs):
            user_id = update.effective_user.id
            user_tier = db.get_user_tier(user_id)
            if user_tier != required_tier:
                await update.message.reply_text(
                    f"This command is only available to {required_tier} users. Please upgrade your subscription."
                )
                return
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator
