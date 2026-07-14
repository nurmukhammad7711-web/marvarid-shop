import os
import json
import gspread
from google.oauth2.service_account import Credentials
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def get_products():
    try:
        creds_json = os.environ.get("GOOGLE_CREDS_JSON")
        if not creds_json:
            return []
        
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        
        sheet = client.open("Marvarid_DB").sheet1
        return sheet.get_all_records()
    except Exception as e:
        print(f"Ошибка: {e}")
        return []

@app.get("/")
async def read_root():
    with open("index.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    
    products = get_products()
    products_html = ""
    
    for item in products:
        # Игнорируем пустые строки из таблицы
        name = str(item.get("Name", "")).strip()
        if not name:
            continue
            
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
        products_html = "<p style='text-align:center; grid-column: 1 / -1;'>Товары скоро появятся...</p>"
        
    final_html = html_content.replace("<!-- PRODUCTS_PLACEHOLDER -->", products_html)
    
    # Принудительный рендеринг в формате HTML
    return HTMLResponse(content=final_html)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
