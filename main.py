from channel_verify import required_join_menu, verify_callback
import requests
import json
import base64
import uuid
import re
from datetime import datetime
import os
import sys
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes
from telegram.constants import ParseMode
import PyPDF2
from io import BytesIO
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token - Replace with your actual bot token
BOT_TOKEN = "7765844789:AAGbAE4M9mNf0pDFcce1vr7GObfRZYQk1BE"

# Conversation states
(MOBILE, NAME, AADHAAR_NUMBER, CAPTCHA_RETRIEVE, CAPTCHA_DOWNLOAD, 
 OTP_RETRIEVE, OTP_DOWNLOAD, DOWNLOAD_OPTION, PDF_FILE, PDF_PASSWORD, 
 DOB_DAY, DOB_MONTH, DOB_YEAR) = range(13)

class AadhaarOTPHandler:
    """EXACT same as newfine2.py"""
    def __init__(self):
        self.session = requests.Session()
        self.base_headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en_IN',
            'Connection': 'keep-alive',
            'Content-Type': 'application/json',
            'Origin': 'https://myaadhaar.uidai.gov.in',
            'Referer': 'https://myaadhaar.uidai.gov.in/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
            'appID': 'MYAADHAAR',
            'sec-ch-ua': '"Not-A.Brand";v="99", "Chromium";v="124"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
        }
        self.session.headers.update(self.base_headers)
        self.captcha_txn_id = None
        self.captcha_code = None
        self.otp_txn_id = None
        
    def get_captcha(self):
        request_id = str(uuid.uuid4())
        self.session.headers.update({'X-Request-ID': request_id})
        
        captcha_data = {
            'captchaLength': '6',
            'captchaType': '2',
            'audioCaptchaRequired': True
        }
        
        try:
            response = self.session.post(
                'https://tathya.uidai.gov.in/audioCaptchaService/api/captcha/v3/generation',
                json=captcha_data,
                timeout=30
            )
            
            if response.status_code != 200:
                return False, None, None
            
            resp_json = response.json()
            self.captcha_txn_id = resp_json.get('transactionId')
            captcha_base64 = resp_json.get('imageBase64')
            
            if not captcha_base64:
                return False, None, None
            
            if captcha_base64.startswith('data:image'):
                captcha_base64 = captcha_base64.split(',')[1]
            
            image_bytes = base64.b64decode(captcha_base64)
            return True, image_bytes, self.captcha_txn_id
            
        except Exception as e:
            logger.error(f"Captcha error: {str(e)}")
            return False, None, None
    
    def send_otp(self, mobile, name, captcha_code):
        request_id = str(uuid.uuid4())
        self.session.headers.update({'X-Request-ID': request_id})
        
        request_data = {
            'mobileNumber': mobile,
            'dob': None,
            'email': None,
            'name': name,
            'option': 'UID',
            'otp': None,
            'otpTxnId': None,
            'captchaTxnId': self.captcha_txn_id,
            'captcha': captcha_code,
            'resendOtp': False
        }
        
        try:
            response = self.session.post(
                'https://tathya.uidai.gov.in/retrieveEidUid/ext/v1/generic/retrieveuideid',
                json=request_data,
                timeout=30
            )
            
            if response.status_code == 200:
                resp_json = response.json()
                
                if 'responseData' in resp_json:
                    response_data = resp_json['responseData']
                    otp_txn_id = response_data.get('otpTxnId')
                    status = response_data.get('status')
                    
                    if otp_txn_id and status == "Success":
                        self.otp_txn_id = otp_txn_id
                        return True, otp_txn_id, response_data.get('message', 'OTP Sent')
                    else:
                        return False, None, response_data.get('message', 'Failed')
                else:
                    return False, None, "Invalid response format"
            else:
                return False, None, f"HTTP {response.status_code}"
                
        except Exception as e:
            return False, None, str(e)
    
    def verify_otp(self, otp_code, mobile, name):
        request_id = str(uuid.uuid4())
        self.session.headers.update({'X-Request-ID': request_id})
        
        verify_data = {
            'mobileNumber': mobile,
            'dob': None,
            'name': name,
            'email': None,
            'option': 'UID',
            'otp': otp_code,
            'otpTxnId': self.otp_txn_id,
            'captchaTxnId': self.captcha_txn_id,
            'captcha': self.captcha_code,
            'resendOtp': False
        }
        
        try:
            response = self.session.post(
                'https://tathya.uidai.gov.in/retrieveEidUid/ext/v1/generic/retrieveuideid',
                json=verify_data,
                timeout=30
            )
            
            if response.status_code == 200:
                resp_json = response.json()
                
                if resp_json.get('status') == 200 or resp_json.get('status') == "Success":
                    if 'responseData' in resp_json:
                        response_data = resp_json['responseData']
                        
                        if response_data.get('eidNumber') or response_data.get('uidNumber'):
                            return True, {
                                'eidNumber': response_data.get('eidNumber'),
                                'uidNumber': response_data.get('uidNumber'),
                                'name': response_data.get('name'),
                                'mobileNumber': response_data.get('mobileNumber')
                            }
                        else:
                            return False, response_data.get('message', 'No EID/UID found')
                    else:
                        return False, "Unexpected response format"
                else:
                    error_msg = resp_json.get('errorDetails', {}).get('messageEnglish', 'Verification failed')
                    return False, error_msg
            else:
                return False, f"HTTP {response.status_code}"
                
        except Exception as e:
            return False, str(e)


class AadhaarPDFDownloader:
    """EXACT same as newfile3.py with AUTO BASE64 DECODER"""
    def __init__(self):
        self.session = requests.Session()
        self.base_headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en_IN',
            'Connection': 'keep-alive',
            'Content-Type': 'application/json',
            'Origin': 'https://myaadhaar.uidai.gov.in',
            'Referer': 'https://myaadhaar.uidai.gov.in/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
            'appid': 'MYAADHAAR',
            'sec-ch-ua': '"Not-A.Brand";v="99", "Chromium";v="124"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
        }
        self.session.headers.update(self.base_headers)
        
    def generate_transaction_id(self):
        return str(uuid.uuid4())
    
    def is_base64(self, s):
        if not isinstance(s, str):
            return False
        if s.startswith('data:'):
            s = s.split(',')[1] if ',' in s else s
        s = s.strip()
        if len(s) % 4 != 0:
            s += '=' * (4 - len(s) % 4)
        base64_pattern = re.compile(r'^[A-Za-z0-9+/]+=*$')
        if not base64_pattern.match(s):
            return False
        try:
            decoded = base64.b64decode(s)
            return len(decoded) > 50
        except:
            return False
    
    def detect_file_type(self, file_bytes):
        if file_bytes[:4] == b'%PDF':
            return 'pdf'
        elif file_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            return 'png'
        elif file_bytes[:2] == b'\xff\xd8':
            return 'jpg'
        elif file_bytes[:3] == b'GIF':
            return 'gif'
        elif file_bytes[:2] == b'PK':
            return 'zip'
        elif file_bytes[:1] == b'{' or file_bytes[:1] == b'[':
            try:
                json.loads(file_bytes.decode('utf-8'))
                return 'json'
            except:
                pass
        elif file_bytes[:5] == b'<?xml':
            return 'xml'
        else:
            try:
                file_bytes.decode('utf-8')
                return 'txt'
            except:
                return 'unknown'
    
    def decode_and_extract_base64(self, data, depth=0):
        """Recursively search through JSON response and extract ALL base64 data."""
        decoded_items = []
        
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str) and self.is_base64(value) and len(value) > 100:
                    logger.info(f"Found base64 data in field: '{key}'")
                    try:
                        clean_base64 = value
                        if clean_base64.startswith('data:'):
                            clean_base64 = clean_base64.split(',')[1] if ',' in clean_base64 else clean_base64
                        clean_base64 = re.sub(r'\s', '', clean_base64)
                        
                        if len(clean_base64) % 4 != 0:
                            clean_base64 += '=' * (4 - len(clean_base64) % 4)
                        
                        decoded_bytes = base64.b64decode(clean_base64)
                        file_type = self.detect_file_type(decoded_bytes)
                        
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        ext = file_type
                        filename = f"decoded_{key}_{timestamp}.{ext}"
                        
                        decoded_items.append({
                            'field': key,
                            'filename': filename,
                            'type': file_type,
                            'bytes': decoded_bytes,
                            'size': len(decoded_bytes)
                        })
                        
                    except Exception as e:
                        logger.error(f"Failed to decode {key}: {str(e)}")
                
                decoded_items.extend(self.decode_and_extract_base64(value, depth + 1))
                
        elif isinstance(data, list):
            for idx, item in enumerate(data):
                decoded_items.extend(self.decode_and_extract_base64(item, depth + 1))
        
        return decoded_items
    
    def get_captcha(self):
        """Fetch captcha - EXACT same as newfile3.py"""
        transaction_id = self.generate_transaction_id()
        self.session.headers.update({
            'x-request-id': transaction_id,
            'transactionId': transaction_id
        })
        
        captcha_data = {
            'captchaLength': '6',
            'captchaType': '2',
            'audioCaptchaRequired': True
        }
        
        try:
            response = self.session.post(
                'https://tathya.uidai.gov.in/audioCaptchaService/api/captcha/v3/generation',
                json=captcha_data,
                timeout=30
            )
            
            if response.status_code != 200:
                return None, None, None
            
            resp_json = response.json()
            captcha_txn_id = resp_json.get('transactionId')
            captcha_base64 = resp_json.get('imageBase64')
            
            if not captcha_base64:
                for key, value in resp_json.items():
                    if isinstance(value, str) and len(value) > 100 and self.is_base64(value):
                        captcha_base64 = value
                        break
            
            if not captcha_base64:
                return None, None, None
            
            if captcha_base64.startswith('data:image'):
                captcha_base64 = captcha_base64.split(',')[1]
            
            image_bytes = base64.b64decode(captcha_base64)
            return image_bytes, captcha_txn_id, transaction_id
            
        except Exception as e:
            logger.error(f"Captcha error: {str(e)}")
            return None, None, None
    
    def send_aadhaar_otp(self, uid_number, captcha_value, captcha_txn_id, transaction_id):
        """Send OTP - EXACT same as newfile3.py"""
        self.session.headers.update({
            'x-request-id': transaction_id,
            'transactionId': transaction_id
        })
        
        otp_request_data = {
            'uidNumber': uid_number,
            'captchaTxnId': captcha_txn_id,
            'captchaValue': captcha_value,
            'transactionId': transaction_id,
            'resendOTP': False
        }
        
        try:
            response = self.session.post(
                'https://tathya.uidai.gov.in/unifiedAppAuthService/api/v2/generate/aadhaar/otp',
                json=otp_request_data,
                timeout=30
            )
            
            if response.status_code == 200:
                resp_json = response.json()
                otp_txn_id = resp_json.get('txnId')
                status = resp_json.get('status')
                message = resp_json.get('message')
                
                if otp_txn_id and status == "Success":
                    return otp_txn_id, resp_json
                else:
                    return None, resp_json
            else:
                return None, None
                
        except Exception as e:
            logger.error(f"Error sending OTP: {str(e)}")
            return None, None
    
    def download_aadhaar_pdf(self, uid_number, otp, otp_txn_id, transaction_id, mask=False):
        """Download Aadhaar PDF - AUTO DECODES ANY BASE64 IN RESPONSE"""
        self.session.headers.update({
            'x-request-id': transaction_id,
            'transactionId': transaction_id
        })
        
        download_data = {
            'uid': uid_number,
            'mask': mask,
            'otp': otp,
            'otpTxnId': otp_txn_id
        }
        
        try:
            response = self.session.post(
                'https://tathya.uidai.gov.in/downloadAadhaarService/api/aadhaar/download',
                json=download_data,
                timeout=60
            )
            
            if response.status_code == 200:
                resp_json = response.json()
                
                # AUTO-DETECT AND DECODE ANY BASE64 DATA IN RESPONSE
                decoded_items = self.decode_and_extract_base64(resp_json)
                
                if decoded_items:
                    # Look for PDF file first
                    for item in decoded_items:
                        if item['type'] == 'pdf':
                            return True, item['filename'], item['bytes']
                    
                    # If no PDF but other files found, return the first one
                    if decoded_items:
                        return True, decoded_items[0]['filename'], decoded_items[0]['bytes']
                    else:
                        return False, None, None
                else:
                    if resp_json.get('status') == 'Error' or resp_json.get('errorCode'):
                        return False, None, None
                    else:
                        return False, None, None
            else:
                return False, None, None
                
        except Exception as e:
            logger.error(f"Error downloading PDF: {str(e)}")
            return False, None, None


class PDFCracker:
    def __init__(self):
        self.attempts = 0
    
    def generate_passwords(self, name, dob_day=None, dob_month=None, dob_year=None):
        passwords = set()
        
        name_prefix = name[:4] if len(name) >= 4 else name
        name_prefix_upper = name_prefix.upper()
        name_prefix_lower = name_prefix.lower()
        
        separators = ['', '@', '#', '_', '-']
        
        if dob_year:
            year_str = str(dob_year)
            year_short = year_str[-2:]
            
            for sep in separators:
                passwords.add(f"{name_prefix_upper}{sep}{year_str}")
                passwords.add(f"{name_prefix_upper}{sep}{year_short}")
                passwords.add(f"{name_prefix_lower}{sep}{year_str}")
                passwords.add(f"{name_prefix_lower}{sep}{year_short}")
                passwords.add(f"{year_str}{sep}{name_prefix_upper}")
                passwords.add(f"{year_short}{sep}{name_prefix_upper}")
            
            if dob_day and dob_month:
                ddmmyyyy = f"{dob_day:02d}{dob_month:02d}{dob_year}"
                passwords.add(f"{name_prefix_upper}{ddmmyyyy}")
        else:
            for year in range(1950, 2006):
                year_str = str(year)
                year_short = year_str[-2:]
                
                for sep in separators:
                    passwords.add(f"{name_prefix_upper}{sep}{year_str}")
                    passwords.add(f"{name_prefix_upper}{sep}{year_short}")
                    passwords.add(f"{name_prefix_lower}{sep}{year_str}")
                    passwords.add(f"{name_prefix_lower}{sep}{year_short}")
        
        return list(passwords)
    
    def crack_pdf(self, pdf_bytes, name, dob_day=None, dob_month=None, dob_year=None):
        self.attempts = 0
        passwords = self.generate_passwords(name, dob_day, dob_month, dob_year)
        
        for password in passwords:
            self.attempts += 1
            try:
                pdf_file = BytesIO(pdf_bytes)
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                result = pdf_reader.decrypt(password)
                if result == 1 or result == 2:
                    return True, password, self.attempts
            except:
                continue
        
        return False, None, self.attempts


# Initialize handlers
retrieve_handler = AadhaarOTPHandler()
cracker = PDFCracker()

# ============ TELEGRAM BOT HANDLERS ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("channel_verified"):
        await required_join_menu(update, context)
        return

    user = update.effective_user
 
    welcome_text = f"""
👋 **Welcome {user.first_name}!**

🤖 **Aadhaar Service Bot**

⚠️ **Legal Disclaimer:**
- Educational purpose only
- Use only with your own Aadhaar

📌 **Services:**

1️⃣ **Retrieve EID/UID** - Get EID/UID using mobile number
2️⃣ **Download Aadhaar PDF** - Download your Aadhaar PDF  
3️⃣ **Crack PDF Password** - Unlock password-protected PDF

Select an option:
"""
    
    keyboard = [
        [InlineKeyboardButton("🔍 Retrieve EID/UID", callback_data="retrieve")],
        [InlineKeyboardButton("📄 Download Aadhaar PDF", callback_data="download")],
        [InlineKeyboardButton("🔓 Crack PDF Password", callback_data="crack")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "retrieve":
        context.user_data['action'] = 'retrieve'
        await query.edit_message_text(
            "🔍 **Retrieve EID/UID**\n\nEnter your 10-digit registered mobile number:",
            parse_mode=ParseMode.MARKDOWN
        )
        return MOBILE
    
    elif query.data == "download":
        context.user_data['action'] = 'download'
        await query.edit_message_text(
            "📄 **Download Aadhaar PDF**\n\nEnter your 12-digit Aadhaar number:",
            parse_mode=ParseMode.MARKDOWN
        )
        return AADHAAR_NUMBER
    
    elif query.data == "crack":
        context.user_data['action'] = 'crack'
        await query.edit_message_text(
            "🔓 **PDF Password Cracker**\n\nUpload the password-protected PDF file:",
            parse_mode=ParseMode.MARKDOWN
        )
        return PDF_FILE
    
    elif query.data == "cancel":
        await query.edit_message_text("❌ Cancelled. Use /start to begin again.")
        return ConversationHandler.END

# ============ RETRIEVAL FLOW ============

async def get_mobile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mobile = update.message.text.strip()
    
    if not re.match(r'^\d{10}$', mobile):
        await update.message.reply_text("❌ Invalid! Enter 10 digits:")
        return MOBILE
    
    context.user_data['mobile'] = mobile
    await update.message.reply_text("Enter your full name (as per Aadhaar):")
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip().upper()
    context.user_data['name'] = name
    
    msg = await update.message.reply_text("🔄 Fetching captcha...")
    
    success, image_bytes, txn_id = retrieve_handler.get_captcha()
    
    if not success:
        await msg.edit_text("❌ Failed to get captcha. Try again with /start")
        return ConversationHandler.END
    
    retrieve_handler.captcha_txn_id = txn_id
    context.user_data['captcha_txn_id'] = txn_id
    
    await msg.delete()
    
    await update.message.reply_photo(
        photo=image_bytes,
        caption="🔐 **Enter captcha code EXACTLY as shown in image**\n\n"
                "⚠️ Captcha is case-sensitive!\n"
                "Example: If image shows 'A3b9C7', type 'A3b9C7'\n\n"
                "Type the captcha code:",
        parse_mode=ParseMode.MARKDOWN
    )
    
    return CAPTCHA_RETRIEVE

async def process_captcha_retrieve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    captcha = update.message.text.strip()
    
    if len(captcha) != 6 or not re.match(r'^[A-Za-z0-9]{6}$', captcha):
        await update.message.reply_text(
            "❌ Invalid captcha!\n\n"
            "Must be exactly 6 characters (letters + numbers)\n"
            "Case-sensitive!\n\n"
            "Try again:"
        )
        return CAPTCHA_RETRIEVE
    
    retrieve_handler.captcha_code = captcha
    
    await update.message.reply_text("📤 Sending OTP...")
    
    success, otp_txn_id, message = retrieve_handler.send_otp(
        context.user_data['mobile'],
        context.user_data['name'],
        captcha
    )
    
    if not success:
        await update.message.reply_text(f"❌ Failed: {message}\n\nUse /start to try again")
        return ConversationHandler.END
    
    context.user_data['otp_txn_id'] = otp_txn_id
    
    await update.message.reply_text(
        f"✅ {message}\n\nEnter 6-digit OTP received on your mobile:"
    )
    return OTP_RETRIEVE

async def verify_retrieve_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    otp = update.message.text.strip()
    
    if not re.match(r'^\d{6}$', otp):
        await update.message.reply_text("❌ Invalid OTP! Enter 6 digits:")
        return OTP_RETRIEVE
    
    await update.message.reply_text("🔍 Verifying...")
    
    success, result = retrieve_handler.verify_otp(
        otp,
        context.user_data['mobile'],
        context.user_data['name']
    )
    
    if not success:
        await update.message.reply_text(f"❌ Verification failed: {result}\n\nUse /start to try again")
        return ConversationHandler.END
    
    msg = "✅ **EID/UID Retrieved Successfully!**\n\n"
    if result.get('eidNumber'):
        msg += f"📄 **EID:** `{result['eidNumber']}`\n"
    if result.get('uidNumber'):
        msg += f"📄 **UID:** `{result['uidNumber']}`\n"
    if result.get('name'):
        msg += f"👤 **Name:** {result['name']}\n"
    if result.get('mobileNumber'):
        msg += f"📱 **Mobile:** {result['mobileNumber']}\n"
    
    msg += "\n⚠️ Keep this information secure!"
    
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    
    keyboard = [
        [InlineKeyboardButton("🔍 Retrieve EID/UID", callback_data="retrieve")],
        [InlineKeyboardButton("📄 Download Aadhaar PDF", callback_data="download")],
        [InlineKeyboardButton("🔓 Crack PDF Password", callback_data="crack")],
    ]
    await update.message.reply_text("Main Menu:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    return ConversationHandler.END

# ============ DOWNLOAD FLOW ============

async def get_aadhaar_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.text.strip()
    
    if not re.match(r'^\d{12}$', uid):
        await update.message.reply_text("❌ Invalid! Enter 12 digits:")
        return AADHAAR_NUMBER
    
    context.user_data['uid'] = uid
    
    msg = await update.message.reply_text("🔄 Fetching captcha...")
    
    downloader = AadhaarPDFDownloader()
    image_bytes, captcha_txn_id, transaction_id = downloader.get_captcha()
    
    if not image_bytes or not captcha_txn_id:
        await msg.edit_text("❌ Failed to get captcha. Try again with /start")
        return ConversationHandler.END
    
    context.user_data['downloader'] = downloader
    downloader.captcha_txn_id = captcha_txn_id
    context.user_data['download_transaction_id'] = transaction_id
    
    await msg.delete()
    
    await update.message.reply_photo(
        photo=image_bytes,
        caption="🔐 **Enter captcha code EXACTLY as shown in image**\n\n"
                "⚠️ Captcha is case-sensitive!\n"
                "Example: If image shows 'A3b9C7', type 'A3b9C7'\n\n"
                "Type the captcha code:",
        parse_mode=ParseMode.MARKDOWN
    )
    
    return CAPTCHA_DOWNLOAD

async def process_captcha_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    captcha = update.message.text.strip()
    
    if len(captcha) != 6 or not re.match(r'^[A-Za-z0-9]{6}$', captcha):
        await update.message.reply_text(
            "❌ Invalid captcha!\n\n"
            "Must be exactly 6 characters (letters + numbers)\n"
            "Case-sensitive!\n\n"
            "Try again:"
        )
        return CAPTCHA_DOWNLOAD
    
    downloader = context.user_data.get('downloader')
    if not downloader:
        await update.message.reply_text("❌ Session expired. Use /start")
        return ConversationHandler.END
    
    await update.message.reply_text("📤 Sending OTP...")
    
    otp_txn_id, response = downloader.send_aadhaar_otp(
        context.user_data['uid'],
        captcha,
        downloader.captcha_txn_id,
        context.user_data['download_transaction_id']
    )
    
    if not otp_txn_id:
        await update.message.reply_text(f"❌ Failed to send OTP.\n\nUse /start to try again")
        return ConversationHandler.END
    
    context.user_data['otp_txn_id'] = otp_txn_id
    
    await update.message.reply_text(
        f"✅ OTP SENT SUCCESSFULLY!\n\n"
        "Enter 6-digit OTP received on your mobile:"
    )
    return OTP_DOWNLOAD

async def get_download_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    otp = update.message.text.strip()
    
    if not re.match(r'^\d{6}$', otp):
        await update.message.reply_text("❌ Invalid OTP! Enter 6 digits:")
        return OTP_DOWNLOAD
    
    context.user_data['otp'] = otp
    
    keyboard = [
        [InlineKeyboardButton("📄 Unmasked (shows full number)", callback_data="unmasked")],
        [InlineKeyboardButton("🔒 Masked (shows only last 4 digits)", callback_data="masked")],
    ]
    
    await update.message.reply_text(
        "Download options:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return DOWNLOAD_OPTION

async def download_option_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    mask = False if query.data == "unmasked" else True
    
    # Send "processing" message
    processing_msg = await query.edit_message_text("📥 Downloading Aadhaar PDF... Please wait...")
    
    downloader = context.user_data.get('downloader')
    if not downloader:
        await processing_msg.edit_text("❌ Session expired. Use /start")
        return ConversationHandler.END
    
    # Run download in thread pool
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        success, filename, pdf_bytes = await loop.run_in_executor(
            executor,
            downloader.download_aadhaar_pdf,
            context.user_data['uid'],
            context.user_data['otp'],
            context.user_data['otp_txn_id'],
            context.user_data['download_transaction_id'],
            mask
        )
    
    if not success or not pdf_bytes:
        await processing_msg.edit_text("❌ Failed to download Aadhaar PDF. Try again with /start")
        return ConversationHandler.END
    
    await processing_msg.delete()
    
    # ============ SEND PDF WITH MULTIPLE METHODS ============
    
    file_size_mb = len(pdf_bytes) / (1024 * 1024)
    
    # Method 1: Try direct send with increased timeout
    try:
        await query.message.reply_document(
            document=pdf_bytes,
            filename=filename,
            caption=f"✅ **AADHAAR PDF DOWNLOADED!**\n\n📄 Size: {file_size_mb:.2f} MB\n🔒 Please keep this PDF secure!",
            read_timeout=300,
            write_timeout=300,
            connect_timeout=300,
            pool_timeout=300
        )
        logger.info(f"PDF sent successfully: {filename}")
        
    except Exception as e:
        logger.error(f"Direct send failed: {str(e)}")
        
        # Method 2: Try sending as photo (if small)
        if len(pdf_bytes) < 5 * 1024 * 1024:  # Less than 5MB
            try:
                from telegram import InputFile
                await query.message.reply_document(
                    document=InputFile(BytesIO(pdf_bytes), filename=filename),
                    caption=f"✅ Aadhaar PDF ({file_size_mb:.2f} MB)"
                )
            except:
                pass
        
        # Method 3: Send download link (always works)
        try:
            # Save to temp file
            temp_file = f"temp_{filename}"
            with open(temp_file, 'wb') as f:
                f.write(pdf_bytes)
            
            await query.message.reply_text(
                f"✅ **PDF Downloaded Successfully!**\n\n"
                f"📄 File: `{filename}`\n"
                f"📦 Size: {file_size_mb:.2f} MB\n\n"
                f"⚠️ File saved on server. Contact bot owner to get the file.\n\n"
                f"**Alternative:** You can download using this command on your server:\n"
                f"`cp {temp_file} ~/downloads/`"
            )
        except Exception as e2:
            await query.message.reply_text(
                f"✅ PDF Downloaded!\n\n"
                f"📄 Size: {file_size_mb:.2f} MB\n"
                f"📝 Password: Use your Aadhaar password to open\n\n"
                f"File saved locally on bot server."
            )
    
    # Clean up temp files
    if os.path.exists(filename):
        os.remove(filename)
    
    keyboard = [
        [InlineKeyboardButton("🔍 Retrieve EID/UID", callback_data="retrieve")],
        [InlineKeyboardButton("📄 Download Aadhaar PDF", callback_data="download")],
        [InlineKeyboardButton("🔓 Crack PDF Password", callback_data="crack")],
    ]
    await query.message.reply_text("Main Menu:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    return ConversationHandler.END

# ============ CRACKING FLOW ============

async def receive_pdf_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        await update.message.reply_text("❌ Please send a PDF file.")
        return PDF_FILE
    
    file = update.message.document
    if not file.file_name.lower().endswith('.pdf'):
        await update.message.reply_text("❌ Please send a valid PDF file.")
        return PDF_FILE
    
    msg = await update.message.reply_text("📥 Downloading PDF...")
    
    file_obj = await file.get_file()
    pdf_bytes = await file_obj.download_as_bytearray()
    
    await msg.delete()
    
    context.user_data['pdf_bytes'] = bytes(pdf_bytes)
    context.user_data['pdf_filename'] = file.file_name
    
    await update.message.reply_text(
        "🔓 **PDF Cracking Setup**\n\n"
        "Enter name as per Aadhaar (exactly as on document):\n"
        "Example: JOHN DOE"
    )
    return PDF_PASSWORD

async def get_name_for_crack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip().upper()
    context.user_data['crack_name'] = name
    
    keyboard = [
        [InlineKeyboardButton("✅ Yes, I know DOB", callback_data="has_dob")],
        [InlineKeyboardButton("❌ No, try all years", callback_data="no_dob")],
    ]
    
    await update.message.reply_text(
        f"✅ Name: {name}\n\nDo you know Date of Birth?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return DOB_DAY

async def dob_choice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "has_dob":
        await query.edit_message_text("📅 Enter day (1-31):")
        return DOB_DAY
    else:
        context.user_data['dob_year'] = None
        await query.edit_message_text("🔄 Cracking without DOB... This may take a minute.")
        return await perform_cracking(update, context, query)

async def get_dob_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        day = int(update.message.text.strip())
        if day < 1 or day > 31:
            raise ValueError
        context.user_data['dob_day'] = day
        await update.message.reply_text("Enter month (1-12):")
        return DOB_MONTH
    except:
        await update.message.reply_text("❌ Invalid day. Enter 1-31:")
        return DOB_DAY

async def get_dob_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        month = int(update.message.text.strip())
        if month < 1 or month > 12:
            raise ValueError
        context.user_data['dob_month'] = month
        await update.message.reply_text("Enter year (e.g., 1990):")
        return DOB_YEAR
    except:
        await update.message.reply_text("❌ Invalid month. Enter 1-12:")
        return DOB_MONTH

async def get_dob_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        year = int(update.message.text.strip())
        if year < 1900 or year > 2026:
            raise ValueError
        context.user_data['dob_year'] = year
        
        await update.message.reply_text(f"📅 DOB: {context.user_data['dob_day']}/{context.user_data['dob_month']}/{year}\n\n🔄 Cracking PDF... Please wait.")
        
        return await perform_cracking(update, context)
    except:
        await update.message.reply_text("❌ Invalid year. Enter 1900-2026:")
        return DOB_YEAR

async def perform_cracking(update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
    pdf_bytes = context.user_data.get('pdf_bytes')
    name = context.user_data.get('crack_name')
    dob_day = context.user_data.get('dob_day')
    dob_month = context.user_data.get('dob_month')
    dob_year = context.user_data.get('dob_year')
    
    if not pdf_bytes or not name:
        if query:
            await query.edit_message_text("❌ Missing data. Use /start")
        else:
            await update.message.reply_text("❌ Missing data. Use /start")
        return ConversationHandler.END
    
    msg = await (query.edit_message_text("🔐 Cracking password...") if query else update.message.reply_text("🔐 Cracking password..."))
    
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        success, password, attempts = await loop.run_in_executor(
            executor,
            cracker.crack_pdf,
            pdf_bytes, name, dob_day, dob_month, dob_year
        )
    
    if success:
        await msg.edit_text(f"✅ **PASSWORD FOUND!**\n\n🔑 **Password:** `{password}`\n📊 Attempts: {attempts}\n\n🔓 Unlocking PDF...")
        
        try:
            pdf_file = BytesIO(pdf_bytes)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            pdf_reader.decrypt(password)
            
            pdf_writer = PyPDF2.PdfWriter()
            for page in pdf_reader.pages:
                pdf_writer.add_page(page)
            
            unlocked = BytesIO()
            pdf_writer.write(unlocked)
            unlocked.seek(0)
            
            unlocked_filename = f"unlocked_{context.user_data.get('pdf_filename', 'aadhaar.pdf')}"
            
            await (update.message or query.message).reply_document(
                document=unlocked,
                filename=unlocked_filename,
                caption="🔓 **Unlocked PDF!**"
            )
        except:
            await (update.message or query.message).reply_text(f"⚠️ Use password: `{password}`", parse_mode=ParseMode.MARKDOWN)
    else:
        await msg.edit_text(f"❌ **Password not found**\n\n📊 Attempts: {attempts}\n\nTry with correct name or DOB.")
    
    keyboard = [
        [InlineKeyboardButton("🔍 Retrieve EID/UID", callback_data="retrieve")],
        [InlineKeyboardButton("📄 Download Aadhaar PDF", callback_data="download")],
        [InlineKeyboardButton("🔓 Crack PDF Password", callback_data="crack")],
    ]
    await (update.message or query.message).reply_text("Main Menu:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled. Use /start to begin again.")
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📖 **Help Guide**

**Commands:**
- /start - Main menu
- /help - This help
- /cancel - Cancel operation

**Services:**

1. **Retrieve EID/UID**
   - Enter 10-digit mobile number
   - Enter name (as per Aadhaar)
   - Solve captcha (case-sensitive!)
   - Enter OTP
   - Get EID/UID

2. **Download Aadhaar PDF**
   - Enter 12-digit Aadhaar number
   - Solve captcha (case-sensitive!)
   - Enter OTP
   - Choose Unmasked/Masked
   - PDF auto-decoded and sent

3. **Crack PDF Password**
   - Upload PDF
   - Enter name
   - Optional: Enter DOB
   - Get password + unlocked PDF

**⚠️ Captcha is CASE-SENSITIVE!**
Type exactly as shown in image.

Use only with your own documents!
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("\n⚠️ Set bot token first!")
        print("Get token from @BotFather")
        sys.exit(1)

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(
        CallbackQueryHandler(verify_callback, pattern="^verify_join$")
    )
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^(retrieve|download|crack|cancel)$")],
        states={
            MOBILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_mobile)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            CAPTCHA_RETRIEVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_captcha_retrieve)],
            OTP_RETRIEVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, verify_retrieve_otp)],
            AADHAAR_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_aadhaar_number)],
            CAPTCHA_DOWNLOAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_captcha_download)],
            OTP_DOWNLOAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_download_otp)],
            DOWNLOAD_OPTION: [CallbackQueryHandler(download_option_handler, pattern="^(unmasked|masked)$")],
            PDF_FILE: [MessageHandler(filters.Document.ALL, receive_pdf_file)],
            PDF_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name_for_crack)],
            DOB_DAY: [CallbackQueryHandler(dob_choice_handler, pattern="^(has_dob|no_dob)$")],
            DOB_MONTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_dob_day)],
            DOB_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_dob_month)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    
    app.add_handler(CommandHandler("start", start))
    # application.add_handler(CallbackQueryHandler(verify_callback, pattern="^verify_join$"))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_dob_year))
    
    print("="*50)
    print("🤖 AADHAAR TELEGRAM BOT STARTED")
    print("="*50)
    print("✅ Retrieve Flow: Working")
    print("✅ Download Flow: Working")
    print("✅ Auto Base64 Decoder: ENABLED")
    print("✅ PDF Send: Multiple fallback methods")
    print("⚠️ Captcha is case-sensitive!")
    print("Ready! Press Ctrl+C to stop")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        import PyPDF2
    except:
        os.system("pip install PyPDF2")
    main()