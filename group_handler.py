from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
import requests
from config import GEMINI_API_KEY, GEMINI_API_URL, GEMINI_VISION_API_URL, BOT_SIGNATURE
import re
import html
import time
import asyncio
from datetime import datetime, timedelta
import base64
import io
import logging

logger = logging.getLogger(__name__)

class GroupHandler:
    def __init__(self, database):
        self.db = database
        self.message_history = {}  # Dictionary to store message history for each group
        self.cleanup_task = None
        
    async def start_cleanup_task(self):
        """بدء مهمة تنظيف الرسائل القديمة"""
        if self.cleanup_task is None:
            self.cleanup_task = asyncio.create_task(self.cleanup_old_messages())
            
    async def cleanup_old_messages(self):
        """تنظيف الرسائل القديمة كل ساعة"""
        while True:
            try:
                current_time = time.time()
                for chat_id in list(self.message_history.keys()):
                    # حذف الرسائل الأقدم من 24 ساعة
                    messages_to_delete = []
                    for msg_id, msg_data in self.message_history[chat_id].items():
                        if current_time - msg_data['timestamp'] >= 24 * 3600:  # 24 hours in seconds
                            messages_to_delete.append(msg_id)
                    
                    # حذف الرسائل القديمة من القاموس
                    for msg_id in messages_to_delete:
                        del self.message_history[chat_id][msg_id]
                    
                    # حذف المجموعة إذا كانت فارغة
                    if not self.message_history[chat_id]:
                        del self.message_history[chat_id]
                
            except Exception as e:
                print(f"Error in cleanup task: {str(e)}")
            
            # انتظار ساعة قبل التنظيف التالي
            await asyncio.sleep(3600)  # 1 hour in seconds

    async def start_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تسجيل المجموعة في قاعدة البيانات عند إضافة البوت"""
        chat_id = update.effective_chat.id
        chat_title = update.effective_chat.title
        
        if update.effective_chat.type in ['group', 'supergroup']:
            self.db.add_group(chat_id, chat_title)
            await update.message.reply_text(
                "شكراً لإضافتي إلى المجموعة! 🤖\n"
                "يمكنك استخدام الأمر /help للحصول على قائمة الأوامر المتاحة."
            )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض تعليمات استخدام البوت"""
        help_text = """
🤖 مرحباً بك في بوت Cyber!

الأوامر المتاحة:
• اكتب 'cyber' متبوعاً برسالتك للتحدث مع الذكاء الاصطناعي
• /cyber - للتعرف على البوت
• /help - لعرض هذه التعليمات

مثال:
cyber ما هو علم الأمن السيبراني؟
"""
        await update.message.reply_text(help_text)

    async def cyber_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """التعريف بالبوت"""
        about_text = """
🤖 مرحباً! أنا بوت Cyber المتخصص في الذكاء الاصطناعي.

يمكنني:
• الإجابة على أسئلتك المتعلقة بالأمن السيبراني
• مساعدتك في فهم المفاهيم التقنية
• التفاعل مع ردودك ومناقشاتك

للبدء، فقط اكتب 'cyber' متبوعاً بسؤالك! 🚀
"""
        await update.message.reply_text(about_text)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """التعامل مع الرسائل في المجموعات"""
        message = update.message
        chat_id = update.effective_chat.id
        
        # التأكد من تشغيل مهمة التنظيف
        await self.start_cleanup_task()
        
        # التحقق من أن الرسالة في مجموعة
        if update.effective_chat.type not in ['group', 'supergroup']:
            return

        # معالجة الصور (مع أو بدون نص)
        if message.photo:
            try:
                # الحصول على أفضل نسخة من الصورة
                photo = message.photo[-1]
                photo_file = await context.bot.get_file(photo.file_id)
                
                # تحميل الصورة
                photo_data = await photo_file.download_as_bytearray()
                
                # تحويل الصورة إلى base64
                base64_image = base64.b64encode(photo_data).decode('utf-8')
                
                # تحضير النص للتحليل
                caption = None
                if message.caption and 'cyber' in message.caption.lower():
                    # Remove the word 'cyber' and any extra spaces
                    caption = message.caption.lower().replace('cyber', '', 1).strip()
                
                if caption is not None:
                    caption = f"{caption}  )"
                    
                    # تحضير الطلب
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
                    
                    # إرسال رسالة انتظار
                    processing_msg = await message.reply_text("🔍 جاري تحليل الصورة...")
                    
                    # إرسال الطلب إلى Gemini Vision API
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
                        
                        # تعديل النص في اي مكان في الرسالة
                        parts = ai_response.split("تم تدريبي بواسطة جوجل")
                        ai_response = "تم تدريبي بواسطة جوجل وتم ربطي في البوت وبرمجتي لاتعامل مع المستخدمين من قبل وهيب الشرعبي".join(parts)
                        
                        # تنسيق النص
                        formatted_response = format_text(ai_response)
                        final_response = add_signature(formatted_response)
                        
                        # إرسال التحليل
                        sent_message = await processing_msg.edit_text(final_response, parse_mode='HTML')
                        
                        # حفظ الرد في التاريخ
                        if chat_id not in self.message_history:
                            self.message_history[chat_id] = {}
                        self.message_history[chat_id][sent_message.message_id] = {
                            'question': f"[صورة] {caption}",
                            'response': final_response,
                            'timestamp': time.time()
                        }
                    else:
                        await processing_msg.edit_text("⚠️ عذراً، حدث خطأ في معالجة الصورة. الرجاء المحاولة مرة أخرى.")
                        logger.error(f"API Error: {response.status_code}\n{response.text}")
                
            except Exception as e:
                await message.reply_text("⚠️ عذراً، حدث خطأ أثناء تحليل الصورة. الرجاء المحاولة مرة أخرى.")
                logger.error(f"Error processing image: {str(e)}")
            return

        # التحقق من نوع الرسالة
        if not message.text:
            return

        # الحالة الأولى: رسالة تبدأ بـ cyber
        if message.text.lower().strip().startswith('cyber'):
            query = message.text.lower().replace('cyber', '', 1).strip()
            if query:
                try:
                    processing_msg = await message.reply_text("🤔 جاري التفكير...")
                    response = await self.get_ai_response(query)
                    formatted_response = format_text(response)
                    full_response = f"{formatted_response}\n\n"
                    final_response = add_signature(full_response)
                    sent_message = await processing_msg.edit_text(final_response, parse_mode='HTML')
                    
                    # حفظ الرسالة والسؤال في التاريخ مع الوقت
                    if chat_id not in self.message_history:
                        self.message_history[chat_id] = {}
                    self.message_history[chat_id][sent_message.message_id] = {
                        'question': query,
                        'response': final_response,
                        'timestamp': time.time()
                    }
                except Exception as e:
                    await message.reply_text("⚠️ عذراً، حدث خطأ أثناء معالجة طلبك. الرجاء المحاولة مرة أخرى.")
            else:
                await message.reply_text("👋 مرحباً! يرجى كتابة سؤالك بعد كلمة cyber")
            return

        # الحالة الثانية: رد على رسالة البوت
        if message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
            try:
                # استرجاع السياق السابق من التاريخ
                previous_context = ""
                if chat_id in self.message_history and message.reply_to_message.message_id in self.message_history[chat_id]:
                    prev_msg = self.message_history[chat_id][message.reply_to_message.message_id]
                    previous_context = f"السؤال السابق: {prev_msg['question']}\nالإجابة السابقة: {prev_msg['response']}\nالرد الجديد: {message.text}"
                else:
                    previous_context = message.text

                processing_msg = await message.reply_text("🤔 جاري التفكير...")
                response = await self.get_ai_response(previous_context)
                formatted_response = format_text(response)
                full_response = f"{formatted_response}\n\n"
                final_response = add_signature(full_response)
                sent_message = await processing_msg.edit_text(final_response, parse_mode='HTML')
                
                # حفظ الرد الجديد في التاريخ مع الوقت
                if chat_id not in self.message_history:
                    self.message_history[chat_id] = {}
                self.message_history[chat_id][sent_message.message_id] = {
                    'question': message.text,
                    'response': final_response,
                    'timestamp': time.time()
                }
            except Exception as e:
                await message.reply_text("⚠️ عذراً، حدث خطأ أثناء معالجة ردك. الرجاء المحاولة مرة أخرى.")

    async def broadcast_message(self, context: ContextTypes.DEFAULT_TYPE, message: str):
        """إرسال رسالة إلى جميع المجموعات"""
        groups = self.db.get_all_groups()
        success_count = 0
        fail_count = 0
        
        for group in groups:
            try:
                await context.bot.send_message(chat_id=group['chat_id'], text=message)
                success_count += 1
            except Exception as e:
                fail_count += 1
                continue
        
        return success_count, fail_count

    async def get_ai_response(self, text: str) -> str:
        """الحصول على رد من Gemini API"""
        try:
            headers = {
                "Content-Type": "application/json",
            }
            
            data = {
                "contents": [{
                    "parts": [{
                        "text": f"{text} (استخدم ايموجي تفاعلي مناسب مع كل فكرة في الرد اذا كان كود برمجي مافيش داعي )"
                    }]
                }]
            }
            
            response = requests.post(
                f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
                headers=headers,
                json=data
            )
            
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get("candidates"):
                    ai_response = response_data["candidates"][0]["content"]["parts"][0]["text"]
                    
                    # تعديل النص في اي مكان في الرسالة
                    parts = ai_response.split("تم تدريبي بواسطة جوجل")
                    ai_response = "تم تدريبي بواسطة جوجل وتم ربطي في البوت وبرمجتي لاتعامل مع المستخدمين من قبل وهيب الشرعبي".join(parts)
                    
                    return ai_response
            return "عذراً، لم أستطع فهم طلبك. هل يمكنك إعادة صياغة السؤال؟"
        except Exception as e:
            raise Exception("حدث خطأ في الاتصال مع Gemini API")

    async def get_image_analysis(self, image_data: bytes, text: str) -> str:
        """تحليل الصورة باستخدام Gemini Vision API"""
        try:
            # تحويل الصورة إلى Base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            headers = {
                "Content-Type": "application/json",
            }
            
            data = {
                "contents": [{
                    "parts": [
                        {
                            "text": f"{text} (استخدم ايموجي تفاعلي مناسب مع كل فكرة في الرد)"
                        },
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": image_base64
                            }
                        }
                    ]
                }]
            }
            
            response = requests.post(
                f"{GEMINI_VISION_API_URL}?key={GEMINI_API_KEY}",
                headers=headers,
                json=data
            )
            
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get("candidates"):
                    return response_data["candidates"][0]["content"]["parts"][0]["text"]
            return "عذراً، لم أستطع تحليل الصورة. هل يمكنك المحاولة مرة أخرى؟"
        except Exception as e:
            raise Exception(f"حدث خطأ في تحليل الصورة: {str(e)}")

    async def get_image_from_url(self, url: str) -> bytes:
        """تحميل الصورة من عنوان URL"""
        try:
            response = requests.get(url)
            return response.content
        except Exception as e:
            raise Exception(f"حدث خطأ في تحميل الصورة: {str(e)}")

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
