import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
import telebot
from telebot import types

# ----------------- 1. СОЗЛАШЛАР (СЕРВЕР МУҲИТИДАН ОЛИШ) -----------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
# Render.com даги веб-сайтингиз манзили
WEBHOOK_URL = "https://marvarid-shop.onrender.com/webhook"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
user_states = {}

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- 2. WEBHOOK СОЗЛАМАЛАРИ (Энг муҳим қисм) -----------------
@app.on_event("startup")
async def on_startup():
    # Сервер ишга тушганда эски уланишларни тозалаб, янгисини ўрнатади
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    print("✅ Webhook muvaffaqiyatli o'rnatildi: ", WEBHOOK_URL)

@app.post("/webhook")
async def telegram_webhook(request: Request):
    # Телеграмдан келган хабарларни ботга узатиш
    if request.headers.get("content-type") == "application/json":
        json_string = await request.json()
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return {"status": "ok"}
    return {"status": "error"}

# ----------------- 3. FASTAPI: WEB APP УЧУН API -----------------
@app.get("/", response_class=HTMLResponse)
async def read_root():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "index.html topilmadi."

@app.get("/api/products")
async def get_products():
    try:
        response = supabase.table("products").select("*").order("created_at", desc=True).execute()
        return response.data
    except Exception:
        return []

@app.get("/api/banner")
async def get_banner():
    try:
        response = supabase.table("banner").select("*").eq("id", 1).execute()
        if response.data:
            return response.data[0]
        return {"title": "MARVARID STORE", "subtitle": "Haftalik yangilanishlar"}
    except Exception:
        return {"title": "MARVARID STORE", "subtitle": "Haftalik yangilanishlar"}

# ----------------- 4. TELEGRAM BOT LOGIKASI -----------------
def get_user_role(telegram_id):
    # 1. АСОСИЙ ХЎЖАЙИН УЧУН 100% КАФОЛАТ (Базани айланиб ўтамиз)
    if str(telegram_id) == "38842171" or telegram_id == 38842171:
        return 'owner'
        
    # 2. Бошқа ишчи/админлар учун базадан текширамиз
    try:
        user_id_int = int(telegram_id)
        res = supabase.table("users").select("role").eq("telegram_id", user_id_int).execute()
        
        if res.data and len(res.data) > 0:
            return res.data[0]['role']
        return None
    except Exception as e:
        print(f"Xatolik: {e}")
        return None

def get_main_keyboard(role):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if role == 'owner':
        markup.add("➕ Yangi mahsulot", "🖼 Bannerni yangilash")
        markup.add("👥 Adminlarni boshqarish", "📦 Do'konni ko'rish")
    elif role == 'admin':
        markup.add("➕ Yangi mahsulot", "🖼 Bannerni yangilash")
        markup.add("📦 Do'konni ko'rish")
    return markup

@bot.message_handler(commands=['start'])
def handle_start(message):
    uid = message.from_user.id
    role = get_user_role(uid)
    
    if not role:
        # ДИҚҚАТ: Шу ерга ID рақамни кўрсатиш коди қўшилди
        bot.send_message(message.chat.id, f"Assalomu alaykum! Siz \"Marvarid\" do'koni botidasiz.\n\n⚙️ Admin uchun ma'lumot: Sizning Telegram ID raqamingiz: {uid}", 
                     reply_markup=types.InlineKeyboardMarkup().add(
                         types.InlineKeyboardButton("🛒 Do'konni ochish", web_app=types.WebAppInfo(url="https://marvarid-shop.onrender.com"))
                     ))
        return

    if role == 'blocked':
        bot.send_message(message.chat.id, "Sizning huquqingiz cheklangan (Blocked).")
        return

    bot.send_message(message.chat.id, f"Xush kelibsiz, {message.from_user.first_name}!\nTelefon orqali do'konni boshqarishingiz mumkin.", 
                     reply_markup=get_main_keyboard(role))

@bot.message_handler(func=lambda msg: msg.text == "👥 Adminlarni boshqarish")
def manage_admins(message):
    uid = message.from_user.id
    if get_user_role(uid) != 'owner': return
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ Yangi admin qo'shish", callback_data="add_admin"),
        types.InlineKeyboardButton("🚫 Adminni bloklash/o'chirish", callback_data="block_admin")
    )
    bot.send_message(message.chat.id, "Adminlarni boshqarish:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["add_admin", "block_admin"])
def callback_admins(call):
    uid = call.from_user.id
    if get_user_role(uid) != 'owner': return
    if call.data == "add_admin":
        user_states[uid] = {"state": "waiting_admin_id"}
        bot.send_message(call.message.chat.id, "Yangi admin qo'shish uchun uning Telegram ID raqamini yuboring:")
    elif call.data == "block_admin":
        user_states[uid] = {"state": "waiting_block_id"}
        bot.send_message(call.message.chat.id, "Bloklamoqchi bo'lgan adminning Telegram ID raqamini yuboring:")

@bot.message_handler(func=lambda msg: msg.text == "➕ Yangi mahsulot")
def add_product_start(message):
    uid = message.from_user.id
    if get_user_role(uid) not in ['owner', 'admin']: return
    user_states[uid] = {"state": "waiting_product_name", "images": []}
    bot.send_message(message.chat.id, "Yangi mahsulot nomini yuboring:")

@bot.message_handler(func=lambda msg: msg.text == "📦 Do'konni ko'rish")
def view_store_btn(message):
    bot.send_message(message.chat.id, "🛒 Do'konni ochish uchun tugmani bosing:", 
                     reply_markup=types.InlineKeyboardMarkup().add(
                         types.InlineKeyboardButton("🛒 Do'konni ochish", web_app=types.WebAppInfo(url="https://marvarid-shop.onrender.com"))
                     ))

@bot.message_handler(func=lambda msg: msg.text == "🖼 Bannerni yangilash")
def banner_update_start(message):
    uid = message.from_user.id
    if get_user_role(uid) not in ['owner', 'admin']: return
    user_states[uid] = {"state": "waiting_banner_title"}
    bot.send_message(message.chat.id, "Yangi Banner sarlavhasini (Title) yuboring:")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    uid = message.from_user.id
    state_data = user_states.get(uid)
    if not state_data: return
    state = state_data["state"]
    
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    file_name = f"{message.photo[-1].file_id}.jpg"

    try:
        supabase.storage.from_("marvarid-images").upload(path=file_name, file=downloaded_file, file_options={"content-type": "image/jpeg"})
        public_url = f"{SUPABASE_URL}/storage/v1/object/public/marvarid-images/{file_name}"
        
        if state == "waiting_product_images":
            user_states[uid]["images"].append(public_url)
            bot.send_message(message.chat.id, f"Rasm yuklandi! 📸 (Jami: {len(user_states[uid]['images'])} ta). Yana rasm yuboring yoki 'TUGATISH' deb yozing.")
        elif state == "waiting_banner_image":
            supabase.table("banner").update({"title": user_states[uid]["banner_title"], "subtitle": user_states[uid]["banner_subtitle"], "image_url": public_url}).eq("id", 1).execute()
            bot.send_message(message.chat.id, "Banner yangilandi! 🖼✅", reply_markup=get_main_keyboard(get_user_role(uid)))
            user_states.pop(uid, None)
    except Exception as e:
        bot.send_message(message.chat.id, f"Xatolik: {str(e)}")

@bot.message_handler(func=lambda msg: True)
def handle_all_messages(message):
    uid = message.from_user.id
    role = get_user_role(uid)
    state_data = user_states.get(uid)
    if not state_data: return
    state = state_data["state"]

    if state == "waiting_admin_id" and role == "owner":
        try:
            new_id = int(message.text)
            supabase.table("users").insert({"telegram_id": new_id, "name": "Admin", "role": "admin"}).execute()
            bot.send_message(message.chat.id, f"Muvaffaqiyatli! Admin qo'shildi. ✅")
        except: bot.send_message(message.chat.id, "Xato: ID raqam notog'ri yoki allaqachon bor.")
        user_states.pop(uid, None)

    elif state == "waiting_block_id" and role == "owner":
        try:
            block_id = int(message.text)
            supabase.table("users").update({"role": "blocked"}).eq("telegram_id", block_id).execute()
            bot.send_message(message.chat.id, f"Bloklandi. 🚫")
        except: bot.send_message(message.chat.id, "Xato yuz berdi.")
        user_states.pop(uid, None)

    elif state == "waiting_product_name":
        user_states[uid]["name"] = message.text
        user_states[uid]["state"] = "waiting_product_price"
        bot.send_message(message.chat.id, "Narxini kiriting (faqat raqamda):")

    elif state == "waiting_product_price":
        try:
            user_states[uid]["price"] = float(message.text.replace(" ", ""))
            user_states[uid]["state"] = "waiting_product_category"
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add("Abaya & Hijob", "Ko'ylaklar", "Ro'mol & Sharflar")
            bot.send_message(message.chat.id, "Kategoriyani tanlang:", reply_markup=markup)
        except ValueError:
            bot.send_message(message.chat.id, "Faqat raqam kiriting!")

    elif state == "waiting_product_category":
        cat_map = {"Abaya & Hijob": "hijab", "Ko'ylaklar": "dress", "Ro'mol & Sharflar": "scarf"}
        user_states[uid]["category"] = cat_map.get(message.text, "hijab")
        user_states[uid]["state"] = "waiting_product_desc"
        bot.send_message(message.chat.id, "Mahsulot ta'rifini (описание) yuboring:")

    elif state == "waiting_product_desc":
        user_states[uid]["desc"] = message.text
        user_states[uid]["state"] = "waiting_product_images"
        bot.send_message(message.chat.id, "Rasm юборинг ва тугатгач 'TUGATISH' деб ёзинг:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("TUGATISH"))

    elif state == "waiting_product_images" and message.text == "TUGATISH":
        if not user_states[uid]["images"]:
            bot.send_message(message.chat.id, "Kamida bitta rasm yuboring!")
            return
        try:
            supabase.table("products").insert({
                "name": user_states[uid]["name"],
                "price": user_states[uid]["price"],
                "category": user_states[uid]["category"],
                "images": user_states[uid]["images"],
                "description": user_states[uid]["desc"]
            }).execute()
            bot.send_message(message.chat.id, "Mahsulot muvaffaqiyatli qo'shildi! 🎉", reply_markup=get_main_keyboard(role))
        except Exception as e:
            bot.send_message(message.chat.id, f"Xatolik: {str(e)}", reply_markup=get_main_keyboard(role))
        user_states.pop(uid, None)

    elif state == "waiting_banner_title":
        user_states[uid]["banner_title"] = message.text
        user_states[uid]["state"] = "waiting_banner_subtitle"
        bot.send_message(message.chat.id, "Banner subtitle қисмини юборинг:")

    elif state == "waiting_banner_subtitle":
        user_states[uid]["banner_subtitle"] = message.text
        user_states[uid]["state"] = "waiting_banner_image"
        bot.send_message(message.chat.id, "Banner учун расм юборинг:")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
