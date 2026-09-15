"""
Telegram 2-Channel Required-Join Verification Module
-----------------------------------------------------
This module is standalone and does NOT inspect or modify your existing bot code.

Usage (python-telegram-bot v20+):
    from channel_verify import required_join_menu, verify_callback

Add required_join_menu(update, context) wherever you want the gate to appear,
and add CallbackQueryHandler(verify_callback, pattern=r"^verify_join$") to
your application.

IMPORTANT:
1. Replace CHANNEL_1 with your channel usernames/IDs.
2. The bot must be an administrator in both channels so get_chat_member()
   can verify membership.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

# ====== CHANGE ONLY THESE ======
CHANNEL_1 = "-1003718902158"


CHANNEL_1_URL = "https://t.me/+jme9t2CoEcM3MzQ1"

# ===============================


async def is_member(context: ContextTypes.DEFAULT_TYPE, chat_id, user_id: int) -> bool:
    """Return True if the user is a member of the channel."""
    try:
        member = await context.bot.get_chat_member(
            chat_id=chat_id,
            user_id=user_id
        )
        print("✅ getChatMember:", member.status)
        return member.status in ("member", "administrator", "creator")

    except Exception as e:
        print("❌ getChatMember error:", repr(e))
        return False


def join_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel 1", url="https://t.me/+jme9t2CoEcM3MzQ1")],
        
        [InlineKeyboardButton("🔄 Re-Verify / Start", callback_data="verify_join")],
    ])


async def required_join_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the required-channel gate."""
    text = (
        "⚠️ *Join Required Channels*\n\n"
        "Bot use karne ke liye pehle channel join karein.\n"
        "Join karne ke baad *Re-Verify / Start* dabayein."
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            reply_markup=join_keyboard(),
            parse_mode="Markdown",
        )
    else:
        await update.effective_message.reply_text(
            text=text,
            reply_markup=join_keyboard(),
            parse_mode="Markdown",
        )


async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verify both required channels and continue to your bot."""
    query = update.callback_query
   # await query.answer()

    user_id = query.from_user.id
    first = await is_member(context, CHANNEL_1, user_id)
 

    if first:
        context.user_data["channel_verified"] = True
        # Replace this text with your existing bot's main-menu function.
        await query.edit_message_text(
            "✅ *Verification Successful!*\n\n"
            "Channel verify ho gaya.\n"
            "Ab aap bot use kar sakte hain.",
            parse_mode="Markdown",
        )
    else:
        missing = []
        if not first:
            missing.append("Channel 1")
     

    await query.answer(
        "❌ Pehle Channel 1 join karein.",
        show_alert=True,
    )

    await query.edit_message_text(
        "⚠️ *Join Required Channel*\n\n"
        f"Abhi verify nahi hua.\n"
        f"Missing: {', '.join(missing)}\n\n"
        "Channel join karke *Re-Verify / Start* dabayein.",
        reply_markup=join_keyboard(),
        parse_mode="Markdown",
    )