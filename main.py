import os
import io
import json
import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
import telebot
from telebot import types

# ----------------- COЗЛАШЛАР (СЕРВЕР МУҲИТИДАН ОЛИШ) -----------------
# Энди калитлар код ичида очиқ ёзилмайди, балки сервер тизимидан ўқиб олинади
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://gyjozjcekciwowekdvrv.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Базага уланиш
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# Веб-саҳифа муаммосиз ишлаши учун CORS созламалари
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- FASTAPI: WEB APP УЧУН API -----------------

@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

# Маҳсулотларни базадан олиш API
@app.get("/api/products")
async def get_products():
    try:
        response = supabase.table("products").select("*").order("created_at", desc=True).execute()
        return response.data
    except Exception as e:
        return {"error": str(e)}

# Банерни базадан олиш API
@app.get("/api/banner")
async def get_banner():
    try:
        response = supabase.table("banner").select("*").eq("id", 1).execute()
        if response.data:
            return response.data[0]
        return {}
    except Exception as e:
        return {"error": str(e)}

# Telegram Webhook учун йўл
@app.post(f"/webhook/{BOT_TOKEN}")
async def process_webhook(request: Request):
    update_json = await request.json()
    update = telebot.types.Update.de_json(update_json)
    bot.process_new_updates([update])
    return {"status": "ok"}


# ----------------- TELEGRAM BOT: АДМИН ПАНЕЛ ВА РОЛЛАР -----------------

# Вақтинчалик админ суҳбат ҳолатини сақлаш (телефонда навбат билан товар қўшиш учун)
user_states = {}

# Ролни текшириш функцияси
def get_user_role(telegram_id):
    try:
        res = supabase.table("users").select("role").eq("telegram_id", telegram_id).execute()
        if res.data:
            return res.data[0]['role']
        return None
    except Exception:
        return None

# Асосий клавиатуралар
def get_main_keyboard(role):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if role == 'owner':
        markup.add("➕ Yangi mahsulot", "🖼 Bannerni yangilash")
        markup.add("👥 Adminlarni boshqarish", "📦 Do'konni ko'rish")
    elif role == 'admin':
        markup.add("➕ Yangi mahsulot", "🖼 Bannerni yangilash")
        markup.add("📦 Do'konni ko'rish")
    return markup

@bot.message_with_type_handler(content_types=['text'])
@bot.message_handler(commands=['start'])
def handle_start(message):
    uid = message.from_user.id
    role = get_user_role(uid)
    
    if not role:
        # Агар фойдаланувчи базада бўлмаса, лекин у синовчи бўлса
        bot.reply_to(message, "Assalomu alaykum! Siz \"Marvarid\" do'koni botidasiz. Do'konni ko'rish uchun quyidagi tugmani bosing.", 
                     reply_markup=types.InlineKeyboardMarkup().add(
                         types.InlineKeyboardButton("🛒 Do'konni ochish", web_app=types.WebAppInfo(url=f"{SUPABASE_URL.replace('.supabase.co', '')}-shop.onrender.com"))
                     ))
        return

    if role == 'blocked':
        bot.reply_to(message, "Sizning ushbu botdan foydalanish huquqingiz cheklangan (Blocked).")
        return

    bot.send_message(message.chat.id, f"Xush kelibsiz, {message.from_user.first_name}! Rolingiz: {role.upper()}.\nTelefon orqali do'konni boshqarishingiz mumkin.", 
                     reply_markup=get_main_keyboard(role))


# ---- ВЛАДЕЛЕЦ МЕНЮСИ: АДМИНЛАРНИ БОШҚАРИШ ----
@bot.message_handler(func=lambda msg: msg.text == "👥 Adminlarni boshqarish")
def manage_admins(message):
    uid = message.from_user.id
    if get_user_role(uid) != 'owner':
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ Yangi admin qo'shish", callback_data="add_admin"),
        types.InlineKeyboardButton("🚫 Adminni bloklash/o'chirish", callback_data="block_admin")
    )
    bot.send_message(message.chat.id, "Adminlarni boshqarish menyusi:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["add_admin", "block_admin"])
def callback_admins(call):
    uid = call.from_user.id
    if get_user_role(uid) != 'owner':
        return
    
    if call.data == "add_admin":
        user_states[uid] = {"state": "waiting_admin_id"}
        bot.send_message(call.message.chat.id, "Yangi admin qo'shish uchun uning Telegram ID raqamini yuboring (Masalan: 123456789):")
    elif call.data == "block_admin":
        user_states[uid] = {"state": "waiting_block_id"}
        bot.send_message(call.message.chat.id, "Bloklamoqchi bo'lgan adminning Telegram ID raqamini yuboring:")


# ---- АДМИН МЕНЮСИ: ЯНГИ ТОВАР ҚЎШИШ (FSM) ----
@bot.message_handler(func=lambda msg: msg.text == "➕ Yangi mahsulot")
def add_product_start(message):
    uid = message.from_user.id
    role = get_user_role(uid)
    if role not in ['owner', 'admin']:
        return

    user_states[uid] = {"state": "waiting_product_name", "images": []}
    bot.send_message(message.chat.id, "Yangi mahsulot nomini yuboring (Masalan: Premium turk ko'ylagi):")

# Матнли хабарларни қабул қилиш ва ҳолатга қараб ишлатиш
@bot.message_handler(func=lambda msg: True)
def handle_all_messages(message):
    uid = message.from_user.id
    role = get_user_role(uid)
    state_data = user_states.get(uid)

    if not state_data:
        return

    state = state_data["state"]

    # 1. Администратор қўшиш (Owner учун)
    if state == "waiting_admin_id" and role == "owner":
        try:
            new_admin_id = int(message.text)
            supabase.table("users").insert({"telegram_id": new_admin_id, "name": "Yangi Admin", "role": "admin"}).execute()
            bot.send_message(message.chat.id, f"Muvaffaqiyatli! ID: {new_admin_id} bo'lgan foydalanuvchi Admin etib tayinlandi. ✅")
        except Exception as e:
            bot.send_message(message.chat.id, f"Xatolik yuz berdi. ID noto'g'ri bo'lishi mumkin yoki u allaqachon ro'yxatda bor.\nXatolik: {str(e)}")
        user_states.pop(uid, None)

    # 2. Администраторни блоклаш (Owner учун)
    elif state == "waiting_block_id" and role == "owner":
        try:
            block_id = int(message.text)
            supabase.table("users").update({"role": "blocked"}).eq("telegram_id", block_id).execute()
            bot.send_message(message.chat.id, f"Foydalanuvchi (ID: {block_id}) muvaffaqiyatli bloklandi. 🚫")
        except Exception as e:
            bot.send_message(message.chat.id, f"Xatolik: {str(e)}")
        user_states.pop(uid, None)

    # 3. Маҳсулот қўшиш занжири (FSM)
    elif state == "waiting_product_name":
        user_states[uid]["name"] = message.text
        user_states[uid]["state"] = "waiting_product_price"
        bot.send_message(message.chat.id, f"Mahsulot nomi: \"{message.text}\" qabul qilindi.\nEndi narxini faqat raqamlarda kiriting (Masalan: 450000):")

    elif state == "waiting_product_price":
        try:
            price = float(message.text.replace(" ", ""))
            user_states[uid]["price"] = price
            user_states[uid]["state"] = "waiting_product_category"
            
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add("Abaya & Hijob", "Ko'ylaklar", "Ro'mol & Sharflar")
            bot.send_message(message.chat.id, "Mahsulot kategoriyasini quyidagi tugmalardan tanlang:", reply_markup=markup)
        except ValueError:
            bot.send_message(message.chat.id, "Iltimos, narxni faqat raqamlarda kiriting!")

    elif state == "waiting_product_category":
        cat_map = {"Abaya & Hijob": "hijab", "Ko'ylaklar": "dress", "Ro'mol & Sharflar": "scarf"}
        category = cat_map.get(message.text, "hijab")
        user_states[uid]["category"] = category
        user_states[uid]["state"] = "waiting_product_desc"
        bot.send_message(message.chat.id, "Mahsulot ta'rifini (описание) yuboring:")

    elif state == "waiting_product_desc":
        user_states[uid]["desc"] = message.text
        user_states[uid]["state"] = "waiting_product_images"
        bot.send_message(message.chat.id, "Endi mahsulot rasmini yuboring (Bir nechta yuborsangiz ham bo'ladi, tugatgach 'TUGATISH' deb yozing yoki tugmani bosing):", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("TUGATISH"))

    elif state == "waiting_product_images" and message.text == "TUGATISH":
        if not user_states[uid]["images"]:
            bot.send_message(message.chat.id, "Iltimos, kamida bitta rasm yuboring!")
            return
        
        # Маълумотларни базага (Supabase) ёзиш
        try:
            supabase.table("products").insert({
                "name": user_states[uid]["name"],
                "price": user_states[uid]["price"],
                "category": user_states[uid]["category"],
                "images": user_states[uid]["images"],
                "description": user_states[uid]["desc"]
            }).execute()
            bot.send_message(message.chat.id, "Yangi mahsulot muvaffaqiyatli qo'shildi va Web App saytida paydo bo'ldi! 🎉✅", 
                             reply_markup=get_main_keyboard(role))
        except Exception as e:
            bot.send_message(message.chat.id, f"Bazaga yozishda xatolik: {str(e)}", reply_markup=get_main_keyboard(role))
        
        user_states.pop(uid, None)

    # 4. БАНЕРНИ ЯНГИЛАШ ҲОЛАТИ
    elif state == "waiting_banner_title":
        user_states[uid]["banner_title"] = message.text
        user_states[uid]["state"] = "waiting_banner_subtitle"
        bot.send_message(message.chat.id, "Bannerning ikkinchi qismini (subtitle) yuboring (Masalan: Haftalik yangilanishlar):")

    elif state == "waiting_banner_subtitle":
        user_states[uid]["banner_subtitle"] = message.text
        user_states[uid]["state"] = "waiting_banner_image"
        bot.send_message(message.chat.id, "Banner uchun yangi fon rasmini yuboring:")


# ---- РАСМЛАРНИ SUPABASE STORAGE'ГА ЮКЛАШ ТИЗИМИ ----
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    uid = message.from_user.id
    state_data = user_states.get(uid)
    if not state_data:
        return

    state = state_data["state"]

    # Расм файлини Телеграмдан юклаб олиш
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    file_name = f"{message.photo[-1].file_id}.jpg"

    # Supabase Storage (marvarid-images папкаси)га юклаш
    try:
        supabase.storage.from_("marvarid-images").upload(
            path=file_name,
            file=downloaded_file,
            file_options={"content-type": "image/jpeg"}
        )
        
        # Расмнинг очиқ юкланиш манзили (Public URL)
        public_url = f"{SUPABASE_URL}/storage/v1/object/public/marvarid-images/{file_name}"
        
        # Маҳсулот расмларига қўшиш
        if state == "waiting_product_images":
            user_states[uid]["images"].append(public_url)
            bot.send_message(message.chat.id, f"Rasm muvaffaqiyatli yuklandi! 📸 (Jami: {len(user_states[uid]['images'])} ta rasm). Yana rasm yuborishingiz mumkin.")
        
        # Банер расми сифатида янгилаш
        elif state == "waiting_banner_image":
            # Базадаги банерни янгилаш
            supabase.table("banner").update({
                "title": user_states[uid]["banner_title"],
                "subtitle": user_states[uid]["banner_subtitle"],
                "image_url": public_url
            }).eq("id", 1).execute()
            
            bot.send_message(message.chat.id, "Banner muvaffaqiyatli yangilandi! 🖼✅", reply_markup=get_main_keyboard(get_user_role(uid)))
            user_states.pop(uid, None)

    except Exception as e:
        bot.send_message(message.chat.id, f"Rasmni saqlashda xatolik yuz berdi: {str(e)}")


# ---- БАНЕРНИ ЯНГИЛАШНИ БОШЛАШ ----
@bot.message_handler(func=lambda msg: msg.text == "🖼 Bannerni yangilash")
def banner_update_start(message):
    uid = message.from_user.id
    role = get_user_role(uid)
    if role not in ['owner', 'admin']:
        return

    user_states[uid] = {"state": "waiting_banner_title"}
    bot.send_message(message.chat.id, "Yangi Banner sarlavhasini (Title) yuboring (Masalan: YANGI TO'PLAM yoki AKSIYA 20%):")


# Webhook уланишини созлаш
import threading
import time

def run_bot():
    # Эски вебҳук созламаларини тозалаш
    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception as e:
        print(f"Webhook тозалашда хатолик: {e}")
        
    print("Bot polling rejimida muvaffaqiyatli ishga tushdi...")
    # Бот доимий ишлаб туриши ва хатоликларда тўхтаб қолмаслиги учун
    bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=10)

# Бот FastAPI (веб-сайт) ишига халақит бермаслиги учун уни алоҳида оқимда (Thread) ишга туширамиз
bot_thread = threading.Thread(target=run_bot)
bot_thread.daemon = True
bot_thread.start()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
