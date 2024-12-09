import logging
import json
import requests
import time
import base64
import asyncio
from typing import Dict, List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from config import TELEGRAM_TOKEN, GEMINI_API_KEY, GEMINI_API_URL, BOT_SIGNATURE, ADMIN_NOTIFICATION_ID
from database import Database
from admin_panel import (
    admin_panel, 
    handle_admin_callback, 
    handle_admin_message, 
    get_admin_keyboard, 
    get_groups_keyboard,
    show_groups,
    show_statistics,
    show_users,
    start_broadcast,
    show_ban_menu,
    start_ban,
    start_unban,
    show_banned_users,
    start_forward_ad,
    handle_forward_ad_message,
    start_groups_broadcast,
    handle_groups_broadcast,
    execute_groups_broadcast,
    is_admin
)
from group_handler import GroupHandler
import re
import html
import datetime

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize database
db = Database()

# Dictionary to store conversation history
conversation_history: Dict[int, List[Dict]] = {}

def get_base_keyboard():
    """Get the base keyboard markup with 'محادثة جديدة' button."""
    keyboard = [[KeyboardButton("🔄 محادثة جديدة")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is subscribed to the channel."""
    try:
        member = await context.bot.get_chat_member(chat_id="@SyberSc71", user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

async def force_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force user to subscribe to channel."""
    user_id = update.effective_user.id
    if not await check_subscription(user_id, context):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("اشترك في القناة 📢", url="https://t.me/SyberSc71")],
            [InlineKeyboardButton("تحقق من الاشتراك ✅", callback_data="check_subscription")]
        ])
        await update.message.reply_text(
            "عذراً! يجب عليك الاشتراك في قناتنا أولاً للاستمرار.\n"
            "اشترك ثم اضغط على زر التحقق 👇 أو اضغط /start",
            reply_markup=keyboard
        )
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    user_id = user.id
    
    # Print user ID for admin
    if is_admin(user.username):
        await update.message.reply_text(f"Your numeric ID is: {user_id}")
    
    # Add user to database
    is_new_user = str(user_id) not in db.data["users"]
    db.add_user(user_id, user.username or "", user.first_name)
    
    # Send notification to admin about new user
    if is_new_user:
        admin_notification = (
            f"🔔 مستخدم جديد انضم للبوت:\n"
            f"الاسم: {user.first_name}\n"
            f"المعرف: @{user.username if user.username else 'لا يوجد'}\n"
            f"الآيدي: {user_id}"
        )
        try:
            await context.bot.send_message(chat_id=ADMIN_NOTIFICATION_ID, text=admin_notification)
        except Exception as e:
            logger.error(f"Failed to send admin notification: {e}")
    
    # Check if user is banned
    if db.is_user_banned(user_id):
        await update.message.reply_text("عذراً، تم حظرك من استخدام البوت.")
        return

    conversation_history[user_id] = []
    welcome_message = (
        f"مرحباً بك {user.first_name} في بوت المساعد الذكي للطلاب! 👋\n\n"
        "يمكنني مساعدتك في:\n"
        "- الإجابة على الأسئلة الأكاديمية\n"
        "- شرح المفاهيم المعقدة\n"
        "- تحليل الصور وشرح محتواها\n"
        "- المساعدة في حل المسائل\n"
        "- تقديم نصائح للدراسة\n\n"
        "يمكنك إرسال سؤال نصي أو صورة وسأقوم بمساعدتك! 📚✨\n\n"
        "━━━━━━━━━━━━━━\n"
        "📢 قناة التلجرام: @SyberSc71\n"
        "👨‍💻 برمجة: @WAT4F"
    )
    await update.message.reply_text(
        welcome_message,
        reply_markup=get_base_keyboard()
    )

def format_text(text: str) -> str:
    """Format mixed text (Arabic/English) for better readability with HTML support."""
    # Split text into paragraphs while preserving code blocks
    parts = []
    current_part = []
    in_code_block = False
    
    # First, split the text while preserving code blocks
    for line in text.split('\n'):
        if line.strip().startswith('```'):
            if in_code_block:
                # End of code block
                current_part.append(line)
                parts.append('\n'.join(current_part))
                current_part = []
                in_code_block = False
            else:
                # Start of code block
                if current_part:
                    parts.append('\n'.join(current_part))
                    current_part = []
                current_part.append(line)
                in_code_block = True
        else:
            current_part.append(line)
    
    # Add any remaining content
    if current_part:
        parts.append('\n'.join(current_part))
    
    formatted_parts = []
    for part in parts:
        if part.strip().startswith('```'):
            # Handle code block
            code_content = part.replace('```python', '').replace('```', '').strip()
            formatted_parts.append(f'<pre><code>{html.escape(code_content)}</code></pre>')
        else:
            # Handle regular text
            lines = part.split('\n')
            formatted_lines = []
            
            for line in lines:
                # Skip empty lines
                if not line.strip():
                    formatted_lines.append(line)
                    continue
                    
                # Handle inline code
                line = re.sub(r'`([^`]+)`', lambda m: f'<code>{html.escape(m.group(1))}</code>', line)
                
                # Handle bold text
                line = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', line)
                line = re.sub(r'__(.+?)__', r'<b>\1</b>', line)
                
                # Handle italic text
                line = re.sub(r'\*(.+?)\*', r'<i>\1</i>', line)
                line = re.sub(r'_(.+?)_', r'<i>\1</i>', line)
                
                # Handle bullet points
                if line.strip().startswith(('•', '-', '*')):
                    line = f'• {line.strip().lstrip("•-* ")}'
                
                formatted_lines.append(line)
            
            formatted_parts.append('\n'.join(formatted_lines))
    
    # Join all parts with appropriate spacing
    final_text = '\n\n'.join(part for part in formatted_parts if part.strip())
    return final_text

def add_signature(text: str):
    """Add a signature to long messages"""
    signature = "\n\n━━━━━━━━━━━━━━\n📢 قناة التلجرام: @SyberSc71\n👨‍💻 برمجة: @WAT4F"
    return text + signature

def escape_markdown_v2(text: str) -> str:
    """Escape special characters for Markdown V2 format"""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages with conversation history."""
    if not await force_subscription(update, context):
        return
    
    try:
        user = update.effective_user
        user_id = user.id
        user_message = update.message.text

        # Check if user is banned
        if db.is_user_banned(user_id):
            await update.message.reply_text("عذراً، تم حظرك من استخدام البوت.")
            return

        # Check if user is admin and in admin mode
        if is_admin(update.message.from_user.username):
            # Handle admin commands
            if user_message == "/admin":
                await admin_panel(update, context)
                return
            # Handle admin states
            if context.user_data.get("admin_state"):
                await handle_admin_message(update, context, db)
                return
        
        # Check if user clicked "محادثة جديدة" button
        if user_message == "🔄 محادثة جديدة":
            conversation_history[user_id] = []
            await update.message.reply_text(
                f"تم بدء محادثة جديدة! كيف يمكنني مساعدتك؟{BOT_SIGNATURE}",
                reply_markup=get_base_keyboard()
            )
            return
        
        # Update user activity in database
        db.update_user_activity(user_id, "text")
        
        # Initialize conversation history if it doesn't exist
        if user_id not in conversation_history:
            conversation_history[user_id] = []
        
        # Add user message to history
        conversation_history[user_id].append({
            "role": "user",
            "parts": [{"text": f"{user_message} ( استخدم ايموجات تفاعلية اذا لزم الامر بس اذا كان كود برمجي مافيش داعي  )"}]
        })
        
        # Prepare conversation context
        # Keep last 10 messages for better context understanding
        messages = conversation_history[user_id][-10:]
        
        # Prepare the request payload with conversation history
        payload = {
            "contents": messages,
            "generationConfig": {
                "temperature": 0.7,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 1024,
            }
        }
        
        # Make request to Gemini API
        headers = {
            "Content-Type": "application/json"
        }
        
        # Send "thinking" message
        thinking_message = await update.message.reply_text("جار التفكير... ⏳")
        
        try:
            response = requests.post(
                f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
                headers=headers,
                json=payload,
                timeout=30  # Add timeout
            )
            
            # Delete thinking message
            await thinking_message.delete()
            
            if response.status_code == 200:
                response_data = response.json()
                ai_response = response_data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', 'عذراً، لم أستطع فهم الرسالة.')
                
                # Format the response text
                parts = ai_response.split("تم تدريبي بواسطة جوجل")
                ai_response = "تم تدريبي بواسطة جوجل وتم ربطي في البوت وبرمجتي لاتعامل مع المستخدمين من قبل وهيب الشرعبي".join(parts)

                ai_response = format_text(ai_response)
                
                # Add AI response to history
                conversation_history[user_id].append({
                    "role": "assistant",
                    "parts": [{"text": ai_response}]
                })
                
                await update.message.reply_text(
                    f"{ai_response}{BOT_SIGNATURE}",
                    reply_markup=get_base_keyboard(),
                    parse_mode='HTML'
                )
            else:
                error_message = f"خطأ في الAPI: {response.status_code}\n{response.text}"
                logger.error(error_message)
                await thinking_message.delete()
                await update.message.reply_text(
                    f"عذراً، حدث خطأ في معالجة طلبك. الرجاء المحاولة مرة أخرى.{BOT_SIGNATURE}",
                    reply_markup=get_base_keyboard(),
                    parse_mode='HTML'
                )
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error in API request: {str(e)}")
            await thinking_message.delete()
            await update.message.reply_text(
                f"عذراً، هناك مشكلة في الاتصال. الرجاء المحاولة مرة أخرى.{BOT_SIGNATURE}",
                reply_markup=get_base_keyboard(),
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            await thinking_message.delete()
            await update.message.reply_text(
                f"عذراً، حدث خطأ ما. الرجاء المحاولة مرة أخرى.{BOT_SIGNATURE}",
                reply_markup=get_base_keyboard(),
                parse_mode='HTML'
            )
            
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        await update.message.reply_text(
            f"عذراً، حدث خطأ ما. الرجاء المحاولة مرة أخرى.{BOT_SIGNATURE}",
            reply_markup=get_base_keyboard(),
            parse_mode='HTML'
        )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photos with optional captions using Gemini Vision API."""
    if not await force_subscription(update, context):
        return
    
    try:
        user = update.effective_user
        user_id = user.id

        # Check if user is banned
        if db.is_user_banned(user_id):
            await update.message.reply_text("عذراً، تم حظرك من استخدام البوت.")
            return

        # Check daily image limit for non-premium users
        if not db.is_user_premium(user_id):
            daily_count = db.get_daily_image_count(user_id)
            if daily_count >= 5:
                keyboard = [
                    [InlineKeyboardButton("⭐️ الترقية للعضوية المميزة", url="https://t.me/WAT4F")],
                    [InlineKeyboardButton("💬 تواصل مع الأدمن", url="https://t.me/WAT4F")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "عذراً، لقد وصلت للحد الأقصى من الصور المسموح بها يومياً (5 صور).\n"
                    "للحصول على استخدام غير محدود، يرجى الترقية إلى العضوية المميزة.",
                    reply_markup=reply_markup
                )
                return

        # Update user activity in database
        db.update_user_activity(user_id, "image")
        
        # Get the photo file
        photo = update.message.photo[-1]  # Get the largest photo size
        photo_file = await context.bot.get_file(photo.file_id)
        
        # Download the photo
        photo_data = await photo_file.download_as_bytearray()
        
        # Convert the photo to base64
        base64_image = base64.b64encode(photo_data).decode('utf-8')
        
        # Get caption if exists
        caption = update.message.caption or "قم بتحليل هذه الصورة وشرح محتواها"
        caption = f"{caption} (ملاحظه لا تكتبها بالرساله (استخدم ايموجات تفاعلية بالنص وحاول التنسيق بين الغات  بحث يسهل القراءه واجعل الشرح مفهوم  .لا تكتب بالرد اني قلت لك كذه ) )"
        
        # Prepare the request payload
        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"text": caption},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": base64_image
                        }
                    }
                ]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "topK": 32,
                "topP": 1,
                "maxOutputTokens": 4096,
            }
        }
        
        # Send waiting message
        processing_message = await update.message.reply_text("جاري معالجة الصورة... ⏳")
        
        # Make request to Gemini Vision API
        headers = {
            "Content-Type": "application/json"
        }
        
        vision_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        
        response = requests.post(
            f"{vision_url}?key={GEMINI_API_KEY}",
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200:
            response_data = response.json()
            ai_response = response_data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', 'عذراً، لم أستطع تحليل الصورة.')
            
            # Format the response text using the same formatting function
            formatted_response = format_text(ai_response)
            
            # Delete processing message
            await processing_message.delete()
            
            # Send the analysis with HTML formatting
            await update.message.reply_text(
                f"{formatted_response}{BOT_SIGNATURE}",
                reply_markup=get_base_keyboard(),
                parse_mode='HTML'
            )
        else:
            await processing_message.delete()
            error_message = f"خطأ في الAPI: {response.status_code}\n{response.text}"
            logger.error(error_message)
            await update.message.reply_text(
                f"عذراً، حدث خطأ في معالجة الصورة. الرجاء المحاولة مرة أخرى.{BOT_SIGNATURE}",
                reply_markup=get_base_keyboard(),
                parse_mode='HTML'
            )
            
    except Exception as e:
        logger.error(f"Error in handle_photo: {str(e)}")
        await update.message.reply_text(
            f"عذراً، حدث خطأ ما. الرجاء المحاولة مرة أخرى.{BOT_SIGNATURE}",
            reply_markup=get_base_keyboard(),
            parse_mode='HTML'
        )

async def admin_callback_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Wrapper for admin callback to include database."""
    query = update.callback_query
    
    if not query.from_user.username or not is_admin(query.from_user.username):
        await query.answer("عذراً، هذا الأمر متاح للمشرفين فقط.")
        return
    
    try:
        if query.data == "confirm_broadcast":
            await execute_groups_broadcast(query, context, db)
        elif query.data in ["groups_stats", "groups_search", "groups_inactive", "groups_refresh", "groups_cleanup"]:
            if query.data == "groups_stats":
                await show_groups(query, db)
            elif query.data == "groups_search":
                context.user_data['admin_state'] = 'waiting_group_search'
                await query.message.edit_text(
                    "🔍 *البحث عن مجموعة*\n\n"
                    "أرسل اسم المجموعة أو معرفها للبحث عنها",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 رجوع", callback_data="admin_groups")
                    ]]),
                    parse_mode='Markdown'
                )
            elif query.data == "groups_inactive":
                inactive_groups = [g for g in db.get_all_groups() if g.get('message_count', 0) == 0]
                message = "⚠️ *المجموعات غير النشطة*\n\n"
                
                if not inactive_groups:
                    message += "لا توجد مجموعات غير نشطة! 🎉"
                else:
                    for i, group in enumerate(inactive_groups, 1):
                        message += f"{i}. *{group.get('title', 'مجموعة غير معروفة')}*\n"
                        message += f"   📱 المعرف: `{group.get('chat_id')}`\n"
                        join_date = datetime.fromisoformat(group.get('join_date', datetime.now().isoformat()))
                        days_since_join = (datetime.now() - join_date).days
                        message += f"   ⏰ مضى على الانضمام: `{days_since_join} يوم`\n\n"
                
                await query.message.edit_text(
                    message,
                    reply_markup=get_groups_keyboard(),
                    parse_mode='Markdown'
                )
            elif query.data == "groups_refresh":
                # تحديث معلومات المجموعات
                await query.message.edit_text(
                    "🔄 جاري تحديث معلومات المجموعات...",
                    reply_markup=None
                )
                
                groups = db.get_all_groups()
                updated = 0
                removed = 0
                
                for group in groups:
                    try:
                        chat = await context.bot.get_chat(int(group['chat_id']))
                        db.update_group_info(group['chat_id'], {
                            'title': chat.title,
                            'members_count': chat.get_member_count()
                        })
                        updated += 1
                    except telegram.error.BadRequest:
                        # المجموعة غير موجودة أو تم طرد البوت
                        db.remove_group(group['chat_id'])
                        removed += 1
                    except Exception as e:
                        logging.error(f"Error updating group {group['chat_id']}: {str(e)}")
                
                await query.message.edit_text(
                    f"✅ *تم تحديث المعلومات!*\n\n"
                    f"📊 النتائج:\n"
                    f"• تم تحديث: `{updated}` مجموعة\n"
                    f"• تم حذف: `{removed}` مجموعة\n"
                    f"• المجموع: `{updated + removed}` مجموعة",
                    reply_markup=get_groups_keyboard(),
                    parse_mode='Markdown'
                )
            elif query.data == "groups_cleanup":
                inactive_groups = [g for g in db.get_all_groups() if g.get('message_count', 0) == 0]
                if not inactive_groups:
                    await query.message.edit_text(
                        "✨ لا توجد مجموعات غير نشطة للحذف!",
                        reply_markup=get_groups_keyboard()
                    )
                    return
                
                # تأكيد الحذف
                await query.message.edit_text(
                    f"⚠️ *تأكيد الحذف*\n\n"
                    f"سيتم حذف {len(inactive_groups)} مجموعة غير نشطة.\n"
                    f"هل أنت متأكد؟",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ نعم، احذف", callback_data="confirm_cleanup"),
                         InlineKeyboardButton("❌ لا، إلغاء", callback_data="admin_groups")]
                    ]),
                    parse_mode='Markdown'
                )
        else:
            await handle_admin_callback(update, context, db)
    except Exception as e:
        logging.error(f"Error in admin_callback_wrapper: {str(e)}")
        await query.message.edit_text(
            "⚠️ حدث خطأ أثناء تنفيذ العملية\nالرجاء المحاولة مرة أخرى",
            reply_markup=get_admin_keyboard()
        )

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle subscription check callback."""
    query = update.callback_query
    user_id = query.from_user.id
    
    if await check_subscription(user_id, context):
        await query.answer("✅ شكراً لك! يمكنك الآن استخدام البوت")
        await query.message.edit_text("تم التحقق من اشتراكك بنجاح! يمكنك الآن استخدام البوت ✅")
        await start(update, context)
    else:
        await query.answer("❌ عذراً، يجب عليك الاشتراك في القناة أولاً!")

async def clear_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear messages in a group chat."""
    if not update.message or not update.message.chat.type in ['group', 'supergroup']:
        await update.message.reply_text("هذا الأمر يعمل فقط في المجموعات!")
        return

    # Check if the bot has delete messages permission
    chat_member = await context.bot.get_chat_member(update.message.chat_id, context.bot.id)
    if not chat_member.can_delete_messages:
        await update.message.reply_text("عذراً، لا أملك صلاحية حذف الرسائل في هذه المجموعة!")
        return

    try:
        # Delete the command message first
        await update.message.delete()
        
        # Get the message ID of the command
        message_id = update.message.message_id
        
        # Delete 100 messages before this one (you can adjust this number)
        for i in range(message_id - 100, message_id):
            try:
                await context.bot.delete_message(update.message.chat_id, i)
            except Exception:
                continue
        
        # Send confirmation message that will be deleted after 5 seconds
        msg = await context.bot.send_message(
            update.message.chat_id,
            "تم تنظيف الرسائل! ✨"
        )
        
        # Delete the confirmation message after 5 seconds
        await asyncio.sleep(5)
        await msg.delete()
        
    except Exception as e:
        logger.error(f"Error in clear_messages: {str(e)}")
        await update.message.reply_text("حدث خطأ أثناء محاولة حذف الرسائل.")

def main() -> None:
    """Start the bot."""
    # Initialize the database
    db = Database()

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_TOKEN).connect_timeout(30).read_timeout(30).write_timeout(30).pool_timeout(30).build()

    # إنشاء معالج المجموعات
    group_handler = GroupHandler(db)

    # Add conversation handler
    application.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_subscription$"))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("clear", clear_messages))  # Add this line
    
    # معالجة الرسائل في المحادثات الخاصة فقط
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, 
        handle_message
    ))
    application.add_handler(MessageHandler(
        filters.PHOTO & filters.ChatType.PRIVATE, 
        handle_photo
    ))
    application.add_handler(CallbackQueryHandler(admin_callback_wrapper))

    # إضافة معالجات المجموعات
    application.add_handler(CommandHandler('cyber', group_handler.cyber_command))
    application.add_handler(CommandHandler('help', group_handler.help_command))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
        group_handler.handle_message
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.PHOTO,
        group_handler.handle_message
    ))

    # Start the Bot
    while True:
        try:
            application.run_polling(allowed_updates=Update.ALL_TYPES)
        except Exception as e:
            logger.error(f"An error occurred: {e}. Retrying in 10 seconds...")
            time.sleep(10)
            continue

if __name__ == "__main__":
    main()
