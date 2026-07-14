import os
import json
import gspread
from google.oauth2.service_account import Credentials
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

# Разрешения для бота на чтение таблиц
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def get_products():
    try:
        # Получаем секретный ключ из настроек Render
        creds_json = os.environ.get("GOOGLE_CREDS_JSON")
        if not creds_json:
            print("ОШИБКА: Ключ GOOGLE_CREDS_JSON не найден!")
            return []
        
        # Авторизуемся в Google
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        
        # Открываем таблицу (название должно совпадать с названием вашей таблицы!)
        sheet = client.open("Marvarid_DB").sheet1
        
        # Забираем все данные
        return sheet.get_all_records()
    except Exception as e:
        print(f"Ошибка при чтении таблицы: {e}")
        return []

@app.get("/", response_class=HTMLResponse)
async def read_root():
    # Читаем шаблон дизайна
    with open("index.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    
    # Получаем товары
    products = get_products()
    
    # Генерируем HTML-карточки для каждого товара из таблицы
    products_html = ""
    for item in products:
        name = item.get("Name", "Без названия")
        price = item.get("Price", "0")
        image = item.get("Image", "https://via.placeholder.com/150")
        desc = item.get("Desc", "")
        
        products_html += f"""
        <div class="card">
            <img src="{image}" alt="{name}">
            <div class="card-content">
                <p class="title">{name}</p>
                <div class="price">{price} сум</div>
                <p class="desc">{desc}</p>
                <button onclick="window.Telegram.WebApp.openTelegramLink('https://t.me/marvarid_almalyk')">Заказать</button>
            </div>
        </div>
        """
    
    if not products_html:
        products_html = "<p style='text-align:center; grid-column: 1 / -1;'>Товары загружаются или таблица пуста...</p>"
        
    # Вставляем сгенерированные карточки в наш HTML-шаблон
    final_html = html_content.replace("", products_html)
    return final_html

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
