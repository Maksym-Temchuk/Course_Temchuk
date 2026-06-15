from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from openai import OpenAI
import requests
from bs4 import BeautifulSoup
import urllib.parse
import json
import os
import re

# ==========================================
# КОНФІГУРАЦІЯ API (ГРОШОВИЙ БЕЗКОШТОВНИЙ ВАРІАНТ GROQ)
# ==========================================
GROQ_API_KEY = "gsk_YOUR_API_KEY_HERE"

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

app = Flask(__name__)
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pc_assistant.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================================
# 1. МОДЕЛІ БАЗИ ДАНИХ
# ==========================================
class User(db.Model):
    """Модель користувача системи"""
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    preferences = db.relationship('UserPreference', backref='user', uselist=False, cascade='all, delete-orphan')
    builds = db.relationship('SavedBuild', backref='user', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('ChatMessage', backref='user', lazy=True, cascade='all, delete-orphan')

class UserPreference(db.Model):
    """Апаратні та інтерфейсні налаштування користувача"""
    __tablename__ = 'user_preferences'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    theme = db.Column(db.String(10), default='dark')
    preferred_platform = db.Column(db.String(50), default='AMD')
    hardware_expertise_level = db.Column(db.String(50), default='engineer')
    willing_to_repair = db.Column(db.Boolean, default=True)

class SavedBuild(db.Model):
    """Збережені конфігурації ПК"""
    __tablename__ = 'saved_builds'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    build_name = db.Column(db.String(100), nullable=False)
    cpu = db.Column(db.String(150), nullable=True)
    motherboard = db.Column(db.String(150), nullable=True)
    gpu = db.Column(db.String(150), nullable=True)
    total_price = db.Column(db.Numeric(10, 2), nullable=True)
    saved_at = db.Column(db.DateTime, default=datetime.utcnow)

class ChatMessage(db.Model):
    """Лог повідомлень для збереження контексту листування"""
    __tablename__ = 'chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    sender = db.Column(db.String(10), nullable=False)
    text = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# ==========================================
# 2. ІНІЦІАЛІЗАЦІЯ ТА ТЕСТОВІ ДАНІ
# ==========================================
with app.app_context():
    db.create_all()
    if not User.query.first():
        hashed_password = generate_password_hash("password123")
        test_user = User(email="maksym.temchuk@kpi.ua", password_hash=hashed_password)
        db.session.add(test_user)
        db.session.commit()
        
        prefs = UserPreference(
            user_id=test_user.id, 
            theme='dark', 
            preferred_platform='AMD', 
            hardware_expertise_level='engineer',
            willing_to_repair=True
        )
        db.session.add(prefs)
        db.session.commit()

# ==========================================
# 3. МОДУЛЬ ПАРСИНГУ ЦІН (ВЕБ-СКРАПІНГ)
# ==========================================
def fetch_actual_price(search_query):
    """Скрапінг актуальних цін з маркетплейсу для нейромережі"""
    query = urllib.parse.quote_plus(search_query)
    url = f"https://ek.ua/ek-list.php?search_={query}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            price_elements = soup.find_all('div', class_='model-price-range')
            if price_elements:
                raw_price = price_elements[0].text.strip().replace('\xa0', '').replace('грн', '').strip()
                return f"{raw_price} грн"
            return "Ціна тимчасово недоступна"
        return "Помилка маркетплейсу"
    except Exception as e:
        return "Сайт магазину недоступний"

# ==========================================
# 4. ОСНОВНІ РОУТИ (АВТОРИЗАЦІЯ ТА ІСТОРІЯ)
# ==========================================
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data.get('email')).first()
    if user and check_password_hash(user.password_hash, data.get('password')):
        return jsonify({"status": "success", "user_id": user.id, "email": user.email}), 200
    return jsonify({"status": "error", "message": "Невірний email або пароль"}), 401

@app.route('/api/chat/history/<int:user_id>', methods=['GET'])
def get_chat_history(user_id):
    messages = ChatMessage.query.filter_by(user_id=user_id).order_by(ChatMessage.timestamp.asc()).all()
    return jsonify([{"sender": msg.sender, "text": msg.text} for msg in messages]), 200

@app.route('/api/builds/<int:user_id>', methods=['GET'])
def get_saved_builds(user_id):
    builds = SavedBuild.query.filter_by(user_id=user_id).order_by(SavedBuild.saved_at.desc()).all()
    return jsonify([{"id": b.id, "build_name": b.build_name, "cpu": b.cpu, "motherboard": b.motherboard, "gpu": b.gpu, "total_price": float(b.total_price) if b.total_price else 0} for b in builds]), 200

# ==========================================
# 5. ІНТЕГРАЦІЯ LLM ТА ОБРОБКА ЧАТУ
# ==========================================
@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data.get('message')
    user_id = data.get('user_id')
    
    if not user_message or not user_id:
        return jsonify({"error": "Некоректний запит"}), 400

    new_msg = ChatMessage(user_id=user_id, sender='user', text=user_message)
    db.session.add(new_msg)
    db.session.commit()
    
    # Генерація відповіді від ШІ
    prefs = UserPreference.query.filter_by(user_id=user_id).first()
    bot_reply = ask_real_llm(user_id, user_message, prefs)
    
    # Запис відповіді бота в базу
    bot_msg = ChatMessage(user_id=user_id, sender='bot', text=bot_reply)
    db.session.add(bot_msg)
    db.session.commit()

    # Мульти-патерн тригерів (відмінки, форми, суржик)
    trigger_pattern = r'(збереж|зберег|сохран|запиш|зафікс|засейв|дода|добав|занот|сейв)'
    
    if re.search(trigger_pattern, user_message.lower()):
        # Запуск надійного ізольованого парсера
        extract_and_save_build(user_id, bot_reply)
    
    return jsonify({"response": bot_reply})


def ask_real_llm(user_id, user_message, prefs):
    """Збирання контексту, парсинг цін та відправка запиту в Groq API"""
    history = ChatMessage.query.filter_by(user_id=user_id).order_by(ChatMessage.timestamp.desc()).limit(6).all()
    history.reverse()

    messages_for_api = []
    is_engineer = prefs and prefs.hardware_expertise_level == 'engineer'
    platform = prefs.preferred_platform if prefs else 'Будь-яка'
    
    sys_prompt = f"Ти — експерт з апаратного забезпечення ПК. Базова платформа користувача: {platform}. "
    if is_engineer:
        sys_prompt += "Спілкуйся технічно грамотно. Рекомендуй роботу з силовими ланцюгами, пайку SMD-компонентів та відновлення модулів. Наводь аналогії з ремонтом складної техніки, наче обслуговування плат Lenovo ThinkPad. "
    else:
        sys_prompt += "Пояснюй терміни просто і зрозуміло. "
        
    sys_prompt += (
        "\nКРИТИЧНЕ ПРАВИЛО ОЦІНКИ ЦІН: Оцінюй отримані дані з парсера критично. "
        "В Україні нові комплектуючі не можуть коштувати копійки. Наприклад, відеокарта RTX 4070 або подібна "
        "коштує в районі 25 000 - 33 000 UAH. Якщо парсер видає ціну 1 500 або 6 000 UAH — це ціна кабелю або аксесуару! "
        "Ігноруй помилкову ціну парсера і вказуй реальну ринкову вартість основного компонента. "
        "Усі ціни обов'язково вказуй у гривнях (UAH)."
    )
        
    hardware_keywords = ["ryzen", "intel", "rtx", "rx", "b650", "x670", "материн", "процесор", "відеокарта"]
    if any(kw in user_message.lower() for kw in hardware_keywords):
        price_info = fetch_actual_price(user_message)
        sys_prompt += f"\nДані з парсеру маркетплейсу: {price_info}. (Перевір адекватність цифри перед використанням!)."

    messages_for_api.append({"role": "system", "content": sys_prompt})
    
    for msg in history:
        if msg.text == user_message and msg.sender == 'user':
            continue
        role = "assistant" if msg.sender == "bot" else "user"
        messages_for_api.append({"role": role, "content": msg.text})
        
    messages_for_api.append({"role": "user", "content": user_message})
    
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages_for_api,
            max_tokens=600,
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Помилка авторизації API або сервер недоступний. Опис помилки: {str(e)}"

# ==========================================
# 6. НАДІЙНИЙ ІЗОЛЬОВАНИЙ ПОСТРОЧНИЙ ПАРСЕР
# ==========================================
def extract_and_save_build(user_id, current_bot_reply):
    """
    Аналізує історію чату, знаходить ОСТАННЮ РЕАЛЬНУ збірку комплектуючих,
    повністю ігноруючи сервісні повідомлення специфікацій, та записує її в базу.
    """
    try:
        # Збільшуємо ліміт перегляду повідомлень, щоб точно знайти реальний конфіг
        last_messages = ChatMessage.query.filter_by(user_id=user_id).order_by(ChatMessage.timestamp.desc()).limit(15).all()
        
        build_text = ""
        for msg in last_messages:
            if msg.sender == 'bot':
                text_lower = msg.text.lower()
                # КРИТИЧНИЙ ФІЛЬТР: Повідомлення має містити залізо, але НЕ бути системною специфікацією
                if "процесор" in text_lower and ("відеокарта" in text_lower or "материн" in text_lower):
                    if "специфікація" not in text_lower and "орієнтовна вартість" not in text_lower:
                        build_text = msg.text
                        break
        
        # Якщо в базі порожньо, використовуємо поточну відповідь бота
        if not build_text:
            text_lower = current_bot_reply.lower()
            if "специфікація" not in text_lower and "орієнтовна вартість" not in text_lower:
                build_text = current_bot_reply
            else:
                build_text = current_bot_reply

        # Дефолтні значення для чистого відображення
        cpu = "Не вибрано"
        motherboard = "Не вибрано"
        gpu = "Не вибрано"
        price = 0.0

        if build_text:
            lines = build_text.split('\n')
            for line in lines:
                line_clean = line.strip()
                line_lower = line_clean.lower()
                
                if not line_clean or "специфікація" in line_lower:
                    continue
                
                # Построчний розбір через двокрапку (усуває проблеми з розміткою ** та списками)
                if ":" in line_clean:
                    parts = line_clean.split(":", 1)
                    key = parts[0].lower()
                    value = parts[1].strip().replace("**", "").replace("*", "")
                    
                    # Очищаємо найменування від цінових приписок у рядку компонента (наприклад, "- близько 30 000 UAH")
                    value_clean = re.split(r'\s*[\-—–]\s*близько|\s*близько|\s*[\-—–]\s*\d+|\s*~', value, flags=re.IGNORECASE)[0].strip()
                    
                    if "процесор" in key:
                        cpu = value_clean[:140]
                    elif "материнська" in key or "плата" in key:
                        motherboard = value_clean[:140]
                    elif "відеокарта" in key:
                        gpu = value_clean[:140]
                    elif "вартість" in key or "ціна" in key or "бюджет" in key:
                        # Парсинг підсумкового цінового показника збірки
                        clean_price_str = value.replace(" ", "")
                        digits = re.search(r'\d+', clean_price_str)
                        if digits:
                            price = float(digits.group())

        # АВТОМАТИЧНА НУМЕРАЦІЯ ТА ГЕНЕРАЦІЯ УНІКАЛЬНОГО ЗАГОЛОВКА
        existing_count = SavedBuild.query.filter_by(user_id=user_id).count()
        build_num = existing_count + 1
        
        gpu_tag = ""
        if gpu and gpu != "Не вибрано":
            model_extract = re.search(r'(rtx\s?\d+|rx\s?\d+|gtx\s?\d+|arc\s?\d+)', gpu, re.IGNORECASE)
            if model_extract:
                gpu_tag = f" ({model_extract.group().upper()})"
            else:
                gpu_tag = f" ({' '.join(gpu.split()[:2])})"

        build_name = f"Збірка №{build_num}{gpu_tag}"

        # Запис валідованих даних у базу
        new_build = SavedBuild(
            user_id=user_id,
            build_name=build_name,
            cpu=cpu,
            motherboard=motherboard,
            gpu=gpu,
            total_price=price
        )
        db.session.add(new_build)
        db.session.commit()
        print(f"Збірку '{build_name}' успішно зафіксовано в системі!")

    except Exception as e:
        print(f"Помилка роботи парсера: {e}")
        existing_count = SavedBuild.query.filter_by(user_id=user_id).count()
        new_build = SavedBuild(
            user_id=user_id,
            build_name=f"Збірка №{existing_count + 1}",
            cpu="Помилка автоматичного парсингу",
            total_price=0
        )
        db.session.add(new_build)
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True, port=5000)