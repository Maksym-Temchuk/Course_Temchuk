// ==========================================
// 1. ГЛОБАЛЬНИЙ СТАН (STATE MANAGEMENT)
// ==========================================
// Отримуємо дані сесії з локального сховища браузера
let currentUserId = localStorage.getItem('user_id') || null;
let currentUserEmail = localStorage.getItem('user_email') || null;

// ==========================================
// 2. ЕЛЕМЕНТИ DOM
// ==========================================
// Основний інтерфейс чату
const chatBox = document.getElementById('chat-box');
const micBtn = document.getElementById('mic-btn');
const sendBtn = document.getElementById('send-btn');
const textInput = document.getElementById('text-input');
const themeToggleBtn = document.getElementById('theme-toggle');

// Модальне вікно авторизації (Landing/Login)
const loginOverlay = document.getElementById('login-overlay');
const loginBtn = loginOverlay.querySelector('.primary-btn');
const emailInput = loginOverlay.querySelector('input[type="email"]');
const passwordInput = loginOverlay.querySelector('input[type="password"]');

// Модальне вікно налаштувань
const settingsModal = document.getElementById('settings-modal');
const openSettingsBtn = document.querySelector('.user-profile');
const closeSettingsBtn = document.querySelector('.close-modal');
const saveSettingsBtn = document.querySelector('.save-settings');
const themeSelect = document.getElementById('theme-select');

// ==========================================
// 3. ІНІЦІАЛІЗАЦІЯ ПРИ ЗАВАНТАЖЕННІ СТОРІНКИ
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    // Якщо в localStorage є ID, вважаємо користувача авторизованим
    if (currentUserId) {
        loginOverlay.classList.add('hidden'); // Ховаємо вікно входу
        updateProfileUI(currentUserEmail);    // Оновлюємо ім'я в сайдбарі
        loadUserProfileAndHistory();          // Завантажуємо чат та збірки з БД
    }
});

// Оновлення імені користувача в бічній панелі (беремо текст до @)
function updateProfileUI(email) {
    if (email) {
        const username = email.split('@')[0];
        document.querySelector('.user-profile span').innerText = username;
    }
}

// ==========================================
// 4. ЛОГІКА АВТОРИЗАЦІЇ (LOGIN)
// ==========================================
loginBtn.addEventListener('click', async () => {
    const email = emailInput.value.trim();
    const password = passwordInput.value.trim();
    
    if (!email || !password) {
        alert("Будь ласка, заповніть усі поля!");
        return;
    }
    
    // Блокуємо кнопку на час запиту
    loginBtn.disabled = true;
    loginBtn.innerText = "Вхід...";
    
    try {
        const response = await fetch('http://127.0.0.1:5000/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: email, password: password })
        });
        
        const data = await response.json();
        
        if (response.ok && data.status === "success") {
            // Зберігаємо успішну сесію
            currentUserId = data.user_id;
            currentUserEmail = data.email;
            localStorage.setItem('user_id', data.user_id);
            localStorage.setItem('user_email', data.email);
            
            // Оновлюємо інтерфейс
            loginOverlay.classList.add('hidden');
            updateProfileUI(data.email);
            
            // Витягуємо дані з бази
            await loadUserProfileAndHistory();
            
            setTimeout(() => {
                addMessage("Авторизація успішна. База даних синхронізована. Яке залізо збираємо сьогодні?", 'bot');
            }, 600);
        } else {
            alert(data.message || "Помилка авторизації. Перевірте введені дані.");
        }
    } catch (error) {
        console.error("Мережева помилка:", error);
        alert("Немає зв'язку з сервером Flask. Переконайтеся, що app.py запущено.");
    } finally {
        loginBtn.disabled = false;
        loginBtn.innerText = "Увійти";
    }
});

// Опціональна функція виходу
function logout() {
    localStorage.removeItem('user_id');
    localStorage.removeItem('user_email');
    currentUserId = null;
    currentUserEmail = null;
    loginOverlay.classList.remove('hidden');
    chatBox.innerHTML = ''; 
}

// ==========================================
// 5. НАЛАШТУВАННЯ ТА ТЕМАТИЗАЦІЯ (THEME)
// ==========================================
function applyTheme(isLight) {
    if (isLight) {
        document.body.classList.add('light-theme');
        themeToggleBtn.innerHTML = '<i class="fa-solid fa-sun"></i>';
        themeSelect.value = 'light';
    } else {
        document.body.classList.remove('light-theme');
        themeToggleBtn.innerHTML = '<i class="fa-solid fa-moon"></i>';
        themeSelect.value = 'dark';
    }
}

// Перемикання теми з бічної панелі
themeToggleBtn.addEventListener('click', () => {
    const isLight = !document.body.classList.contains('light-theme');
    applyTheme(isLight);
});

// Керування модальним вікном налаштувань
openSettingsBtn.addEventListener('click', () => settingsModal.classList.remove('hidden'));
closeSettingsBtn.addEventListener('click', () => settingsModal.classList.add('hidden'));

// Збереження налаштувань профілю
saveSettingsBtn.addEventListener('click', () => {
    settingsModal.classList.add('hidden');
    const isLight = themeSelect.value === 'light';
    applyTheme(isLight);
    
    addMessage("Апаратні преференції та налаштування інтерфейсу успішно збережено.", 'bot');
});

// ==========================================
// 6. ЛОГІКА ЧАТУ ТА ВІДПРАВКА ЗАПИТІВ (LLM)
// ==========================================
function addMessage(text, sender) {
    const msgDiv = document.createElement('div');
    msgDiv.classList.add('message', sender);
    
    const avatarDiv = document.createElement('div');
    avatarDiv.classList.add('msg-avatar');
    // Іконка залежить від того, хто відправив повідомлення
    avatarDiv.innerHTML = sender === 'user' ? '<i class="fa-solid fa-user"></i>' : '<i class="fa-solid fa-robot"></i>';
    
    const contentDiv = document.createElement('div');
    contentDiv.classList.add('msg-content');
    contentDiv.innerHTML = `<p>${text}</p>`;
    
    msgDiv.appendChild(avatarDiv);
    msgDiv.appendChild(contentDiv);
    chatBox.appendChild(msgDiv);
    
    // Автоматичний скрол вниз
    chatBox.scrollTop = chatBox.scrollHeight;
}

async function sendMessageToServer(message) {
    if (!message || !currentUserId) return;
    
    addMessage(message, 'user');
    
    // Індикатор "ШІ друкує..."
    const typingId = 'typing-' + Date.now();
    const typingMsg = document.createElement('div');
    typingMsg.classList.add('message', 'bot');
    typingMsg.id = typingId;
    typingMsg.innerHTML = `<div class="msg-avatar"><i class="fa-solid fa-robot"></i></div><div class="msg-content"><p>Аналізую компоненти та актуальні ціни...</p></div>`;
    chatBox.appendChild(typingMsg);
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const response = await fetch('http://127.0.0.1:5000/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message, user_id: currentUserId })
        });
        
        const data = await response.json();
        
        // Видаляємо індикатор завантаження та виводимо реальну відповідь
        document.getElementById(typingId).remove();
        addMessage(data.response, 'bot');

        // Якщо в запиті була команда "збережи", оновлюємо бічну панель
        if (message.toLowerCase().includes('збережи') || message.toLowerCase().includes('сохрани')) {
            // Затримка, щоб БД встигла записати транзакцію
            setTimeout(async () => {
                await updateBuildsSidebar();
            }, 600);
        }

    } catch (error) {
        console.error("Помилка зв'язку з сервером:", error);
        document.getElementById(typingId).remove();
        addMessage("Сервер недоступний. Перевірте консоль терміналу на наявність помилок.", 'bot');
    }
}

// Обробка кнопки "Відправити"
sendBtn.addEventListener('click', () => {
    const text = textInput.value.trim();
    if (text) {
        sendMessageToServer(text);
        textInput.value = '';
    }
});

// Відправка натисканням Enter
textInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendBtn.click();
});

// ==========================================
// 7. ГОЛОСОВИЙ ВВІД (WEB SPEECH API)
// ==========================================
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

if (SpeechRecognition) {
    const recognition = new SpeechRecognition();
    recognition.lang = 'uk-UA'; // Встановлено українську мову
    recognition.interimResults = false;

    recognition.onstart = () => {
        micBtn.classList.add('recording');
        textInput.placeholder = "Слухаю запит...";
    };

    recognition.onresult = (event) => {
        // Щойно голос розпізнано, відразу відправляємо текст на сервер
        sendMessageToServer(event.results[0][0].transcript);
    };

    recognition.onerror = (event) => {
        console.error("Помилка мікрофона:", event.error);
        textInput.placeholder = "Помилка розпізнавання голосу. Спробуйте ще раз.";
    };

    recognition.onend = () => {
        micBtn.classList.remove('recording');
        textInput.placeholder = "Скажи або напиши, що потрібно зібрати...";
    };

    micBtn.addEventListener('click', () => {
        if (micBtn.classList.contains('recording')) {
            recognition.stop();
        } else {
            recognition.start();
        }
    });
} else {
    micBtn.style.display = 'none';
    console.warn("Web Speech API не підтримується у цьому браузері.");
}

// ==========================================
// 8. ДИНАМІЧНЕ ЗАВАНТАЖЕННЯ З БАЗИ ДАНИХ
// ==========================================

// Загальна функція ініціалізації даних профілю
async function loadUserProfileAndHistory() {
    if (!currentUserId) return;
    
    // 1. Відновлюємо історію чату (Memory)
    try {
        const historyResponse = await fetch(`http://127.0.0.1:5000/api/chat/history/${currentUserId}`);
        if (historyResponse.ok) {
            const messages = await historyResponse.json();
            chatBox.innerHTML = ''; // Очищаємо стартові заглушки HTML
            
            if (messages.length === 0) {
                addMessage("Привіт! Я твій асистент з підбору ПК. Готовий вислухати вимоги або бюджет.", 'bot');
            } else {
                messages.forEach(msg => {
                    addMessage(msg.text, msg.sender);
                });
            }
        }
    } catch (error) {
        console.error("Помилка завантаження логів чату:", error);
    }

    // 2. Відмальовуємо ліву панель зі збірками
    await updateBuildsSidebar();
}

// Оновлення сайдбару зі збереженими конфігураціями
async function updateBuildsSidebar() {
    if (!currentUserId) return;
    
    try {
        const buildsResponse = await fetch(`http://127.0.0.1:5000/api/builds/${currentUserId}`);
        if (buildsResponse.ok) {
            const builds = await buildsResponse.json();
            renderSavedBuilds(builds);
        }
    } catch (error) {
        console.error("Не вдалося завантажити збірки з БД:", error);
    }
}

// Рендеринг списку збірок у DOM
function renderSavedBuilds(builds) {
    const historyList = document.querySelector('.history-list');
    historyList.innerHTML = ''; // Очищаємо список
    
    if (builds.length === 0) {
        historyList.innerHTML = `<li class="history-item" style="color: var(--text-secondary); font-size: 13px; cursor: default;">Немає збережених конфігурацій</li>`;
        return;
    }
    
    builds.forEach(build => {
        const li = document.createElement('li');
        li.classList.add('history-item');
        
        // Якщо ціна 0 (заглушка), не виводимо її
        const priceTag = build.total_price > 0 ? ` (~${build.total_price} грн)` : '';
        li.innerHTML = `<i class="fa-solid fa-desktop"></i> <span>${build.build_name}${priceTag}</span>`;
        
        // Клік по збірці в сайдбарі виводить її деталі прямо у вікно чату
        li.addEventListener('click', () => {
            const details = `Специфікація конфігурації "${build.build_name}":\n` +
                            `• Процесор: ${build.cpu || 'Не вибрано'}\n` +
                            `• Материнська плата: ${build.motherboard || 'Не вибрано'}\n` +
                            `• Відеокарта: ${build.gpu || 'Не вибрано'}\n` +
                            `• Орієнтовна вартість: ${build.total_price} грн.`;
            addMessage(details, 'bot');
        });
        
        historyList.appendChild(li);
    });
}