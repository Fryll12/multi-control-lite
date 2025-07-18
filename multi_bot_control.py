# PHIÊN BẢN LITE - ĐÃ TÍCH HỢP LƯU/TẢI JSON - CẬP NHẬT ĐA SERVER
import discum
import threading
import time
import os
import re
import requests
import json
from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv
import uuid

load_dotenv()

# --- CẤU HÌNH ---
main_token = os.getenv("MAIN_TOKEN")
main_token_2 = os.getenv("MAIN_TOKEN_2")
main_token_3 = os.getenv("MAIN_TOKEN_3")
tokens = os.getenv("TOKENS").split(",") if os.getenv("TOKENS") else []
karuta_id = "646937666251915264"
karibbit_id = "1311684840462225440"

# --- BIẾN TRẠNG THÁI (đây là các giá trị mặc định nếu không có file settings.json) ---
bots, acc_names = [], [
    "Blacklist", "Khanh bang", "Dersale", "Venus", "WhyK", "Tan",
    "Ylang", "Nina", "Nathan", "Ofer", "White", "the Wicker", "Leader", "Tess", "Wyatt", "Daisy", "CantStop", "Token",
]
main_bot, main_bot_2, main_bot_3 = None, None, None

# Cấu hình đa server
servers = [] # Sẽ được load từ file JSON

# Cài đặt toàn cục
auto_reboot_enabled = False
auto_reboot_delay = 3600

# Timestamps - sẽ được load từ file
last_reboot_cycle_time = 0

# Các biến điều khiển luồng
auto_reboot_stop_event = threading.Event()
spam_thread, auto_reboot_thread = None, None
bots_lock = threading.Lock()
server_start_time = time.time()
bot_active_states = {}

# --- HÀM LƯU VÀ TẢI CÀI ĐẶT ---
def save_settings():
    """Lưu cài đặt lên JSONBin.io"""
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id:
        return

    settings = {
        'servers': servers,
        'auto_reboot_enabled': auto_reboot_enabled, 
        'auto_reboot_delay': auto_reboot_delay,
        'bot_active_states': bot_active_states,
        'last_reboot_cycle_time': last_reboot_cycle_time
    }
    
    headers = {
        'Content-Type': 'application/json',
        'X-Master-Key': api_key
    }
    url = f"https://api.jsonbin.io/v3/b/{bin_id}"
    
    try:
        req = requests.put(url, json=settings, headers=headers, timeout=10)
        if req.status_code == 200:
            print("[Settings] Đã lưu cài đặt lên JSONBin.io thành công.", flush=True)
        else:
            print(f"[Settings] Lỗi khi lưu cài đặt lên JSONBin.io: {req.status_code} - {req.text}", flush=True)
    except Exception as e:
        print(f"[Settings] Exception khi lưu cài đặt: {e}", flush=True)

def load_settings():
    """Tải cài đặt từ JSONBin.io"""
    global servers, auto_reboot_enabled, auto_reboot_delay, bot_active_states, last_reboot_cycle_time
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id:
        print("[Settings] Thiếu API Key hoặc Bin ID của JSONBin. Sử dụng cài đặt mặc định.", flush=True)
        return

    headers = {'X-Master-Key': api_key}
    url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"

    try:
        req = requests.get(url, headers=headers, timeout=10)
        if req.status_code == 200:
            settings = req.json().get("record", {})
            if settings: # Chỉ load nếu bin không rỗng
                servers = settings.get('servers', [])
                auto_reboot_enabled = settings.get('auto_reboot_enabled', False)
                auto_reboot_delay = settings.get('auto_reboot_delay', 3600)
                bot_active_states = settings.get('bot_active_states', {})
                last_reboot_cycle_time = settings.get('last_reboot_cycle_time', 0)
                print("[Settings] Đã tải cài đặt từ JSONBin.io.", flush=True)
            else:
                print("[Settings] JSONBin rỗng, bắt đầu với cài đặt mặc định và lưu lại.", flush=True)
                save_settings() # Lưu cài đặt mặc định lên bin lần đầu
        else:
            print(f"[Settings] Lỗi khi tải cài đặt từ JSONBin.io: {req.status_code} - {req.text}", flush=True)
    except Exception as e:
        print(f"[Settings] Exception khi tải cài đặt: {e}", flush=True)

# --- CÁC HÀM LOGIC BOT ---
def handle_grab(bot, msg, bot_num):
    """Xử lý logic grab cho một bot cụ thể, áp dụng cho nhiều server."""
    channel_id = msg.get("channel_id")
    
    # Tìm server tương ứng với channel_id
    target_server = None
    for server in servers:
        if server.get('main_channel_id') == channel_id:
            target_server = server
            break
            
    if not target_server:
        return

    # Lấy cài đặt từ server tìm được
    grab_enabled_map = {1: 'auto_grab_enabled_1', 2: 'auto_grab_enabled_2', 3: 'auto_grab_enabled_3'}
    heart_threshold_map = {1: 'heart_threshold_1', 2: 'heart_threshold_2', 3: 'heart_threshold_3'}
    
    auto_grab_enabled = target_server.get(grab_enabled_map[bot_num], False)
    heart_threshold = target_server.get(heart_threshold_map[bot_num], 50)
    ktb_channel_id = target_server.get('ktb_channel_id')
    
    if not auto_grab_enabled or not ktb_channel_id:
        return

    if msg.get("author", {}).get("id") == karuta_id and "is dropping" not in msg.get("content", "") and not msg.get("mentions", []):
        last_drop_msg_id = msg["id"]
        
        def read_karibbit():
            time.sleep(0.5)
            try:
                messages = bot.getMessages(channel_id, num=5).json()
                for msg_item in messages:
                    if msg_item.get("author", {}).get("id") == karibbit_id and "embeds" in msg_item and len(msg_item["embeds"]) > 0:
                        desc = msg_item["embeds"][0].get("description", "")
                        lines = desc.split('\n')
                        heart_numbers = []
                        for line in lines[:3]:
                            match = re.search(r'♡(\d+)', line)
                            heart_numbers.append(int(match.group(1)) if match else 0)
                        
                        if not any(heart_numbers): break

                        max_num = max(heart_numbers)
                        if max_num >= heart_threshold:
                            max_index = heart_numbers.index(max_num)
                            
                            # Cài đặt delay khác nhau cho mỗi bot
                            delays = {
                                1: [0.4, 1.4, 2.1],
                                2: [0.7, 1.8, 2.4],
                                3: [0.7, 1.8, 2.4]
                            }
                            emojis = ["1️⃣", "2️⃣", "3️⃣"]
                            
                            emoji = emojis[max_index]
                            delay = delays[bot_num][max_index]

                            print(f"[{target_server['name']} | Bot {bot_num}] Chọn dòng {max_index+1} với {max_num} tim -> Emoji {emoji} sau {delay}s", flush=True)
                            
                            def grab_action():
                                bot.addReaction(channel_id, last_drop_msg_id, emoji)
                                time.sleep(1)
                                bot.sendMessage(ktb_channel_id, "kt b")
                            
                            threading.Timer(delay, grab_action).start()
                        break
            except Exception as e:
                print(f"Lỗi khi đọc tin nhắn Karibbit (Bot {bot_num} @ {target_server['name']}): {e}", flush=True)

        threading.Thread(target=read_karibbit).start()


def create_bot(token, is_main=False, is_main_2=False, is_main_3=False):
    bot = discum.Client(token=token, log=False)
    
    @bot.gateway.command
    def on_ready(resp):
        if resp.event.ready:
            user_data = resp.raw.get("user", {})
            if isinstance(user_data, dict):
                user_id = user_data.get("id")
                if user_id:
                    bot_type = "(ALPHA)" if is_main else "(BETA)" if is_main_2 else "(GAMMA)" if is_main_3 else ""
                    print(f"Đã đăng nhập: {user_id} {bot_type}", flush=True)

    if is_main:
        @bot.gateway.command
        def on_message(resp):
            if resp.event.message: handle_grab(bot, resp.parsed.auto(), 1)
    
    if is_main_2:
        @bot.gateway.command
        def on_message_2(resp):
            if resp.event.message: handle_grab(bot, resp.parsed.auto(), 2)

    if is_main_3:
        @bot.gateway.command
        def on_message_3(resp):
            if resp.event.message: handle_grab(bot, resp.parsed.auto(), 3)
            
    threading.Thread(target=bot.gateway.run, daemon=True).start()
    return bot

# --- CÁC VÒNG LẶP NỀN ---
def auto_reboot_loop():
    global last_reboot_cycle_time
    while not auto_reboot_stop_event.is_set():
        try:
            interrupted = auto_reboot_stop_event.wait(timeout=60)
            if interrupted: break

            if auto_reboot_enabled and (time.time() - last_reboot_cycle_time) >= auto_reboot_delay:
                print("[Reboot] Hết thời gian chờ, tiến hành reboot 3 tài khoản chính.", flush=True)
                # Logic reboot vẫn giữ nguyên vì nó reboot bot, không phải server
                if main_bot: main_bot.gateway.close(); time.sleep(2); create_bot(main_token, is_main=True); time.sleep(5)
                if main_bot_2: main_bot_2.gateway.close(); time.sleep(2); create_bot(main_token_2, is_main_2=True); time.sleep(5)
                if main_bot_3: main_bot_3.gateway.close(); time.sleep(2); create_bot(main_token_3, is_main_3=True)
                last_reboot_cycle_time = time.time()
                save_settings()

        except Exception as e:
            print(f"[ERROR in auto_reboot_loop] {e}", flush=True)
            time.sleep(60)
    print("[Reboot] Luồng tự động reboot đã dừng.", flush=True)


def spam_loop():
    while True:
        try:
            bots_to_spam = [bot for i, bot in enumerate(bots) if bot and bot_active_states.get(f'sub_{i}', False)]
            
            for server in servers:
                if server.get('spam_enabled') and server.get('spam_message') and server.get('spam_channel_id'):
                    last_spam_time = server.get('last_spam_time', 0)
                    spam_delay = server.get('spam_delay', 10)
                    
                    if (time.time() - last_spam_time) >= spam_delay:
                        for bot in bots_to_spam:
                            if not server.get('spam_enabled'): break # Kiểm tra lại phòng khi bị tắt giữa chừng
                            try:
                                bot.sendMessage(server['spam_channel_id'], server['spam_message'])
                            except Exception as e:
                                print(f"Lỗi gửi spam tới server {server['name']}: {e}", flush=True)
                            time.sleep(2) # Delay giữa các bot
                        
                        if server.get('spam_enabled'):
                            server['last_spam_time'] = time.time()
            time.sleep(1)
        except Exception as e:
            print(f"[ERROR in spam_loop] {e}", flush=True)
            time.sleep(1)

def periodic_save_loop():
    """Vòng lặp nền để tự động lưu cài đặt 10 tiếng một lần."""
    while True:
        time.sleep(36000) # 10 tiếng
        print("[Settings] Bắt đầu lưu định kỳ (10 giờ)...", flush=True)
        save_settings()
        
app = Flask(__name__)

# --- GIAO DIỆN WEB ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Karuta Deep - Shadow Network Control</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Creepster&family=Orbitron:wght@400;700;900&family=Courier+Prime:wght@400;700&family=Nosifer&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary-bg: #0a0a0a; --secondary-bg: #1a1a1a; --panel-bg: #111111; --border-color: #333333;
            --blood-red: #8b0000; --dark-red: #550000; --bone-white: #f8f8ff;
            --necro-green: #228b22; --text-primary: #f0f0f0; --text-secondary: #cccccc;
        }
        body { font-family: 'Courier Prime', monospace; background: var(--primary-bg); color: var(--text-primary); margin: 0; padding: 0;}
        .container { max-width: 1600px; margin: 0 auto; padding: 20px; }
        .header { text-align: center; margin-bottom: 30px; padding: 20px; border-bottom: 2px solid var(--blood-red); }
        .title { font-family: 'Nosifer', cursive; font-size: 3rem; color: var(--blood-red); }
        .main-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(450px, 1fr)); gap: 20px; }
        .panel { background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 25px; position: relative;}
        .panel h2 { font-family: 'Orbitron', cursive; font-size: 1.4rem; margin-bottom: 20px; text-transform: uppercase; border-bottom: 2px solid; padding-bottom: 10px; color: var(--bone-white); }
        .panel h2 i { margin-right: 10px; }
        .btn { background: var(--secondary-bg); border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 4px; cursor: pointer; font-family: 'Orbitron', monospace; font-weight: 700; text-transform: uppercase; width: 100%; }
        .btn-small { padding: 5px 10px; font-size: 0.9em;}
        .input-group { display: flex; align-items: stretch; gap: 10px; margin-bottom: 15px; }
        .input-group label { background: #000; border: 1px solid var(--border-color); border-right: 0; padding: 10px 15px; border-radius: 4px 0 0 4px; display:flex; align-items:center; min-width: 120px;}
        .input-group input, .input-group textarea { flex-grow: 1; background: #000; border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 0 4px 4px 0; font-family: 'Courier Prime', monospace; }
        .grab-section { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; padding: 15px; background: rgba(0,0,0,0.2); border-radius: 8px;}
        .grab-section h3 { margin: 0; display: flex; align-items: center; gap: 10px; }
        .grab-section .input-group { margin-bottom: 0; flex-grow: 1; margin-left: 20px;}
        .msg-status { text-align: center; color: var(--necro-green); padding: 12px; border: 1px dashed var(--border-color); border-radius: 4px; margin-bottom: 20px; display: none; }
        .status-panel { grid-column: 1 / -1; }
        .status-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
        .status-row { display: flex; justify-content: space-between; align-items: center; padding: 12px; background: rgba(0,0,0,0.4); border-radius: 8px; }
        .timer-display { font-size: 1.2em; font-weight: 700; }
        .status-badge { padding: 4px 10px; border-radius: 15px; text-transform: uppercase; font-size: 0.8em; }
        .status-badge.active { background: var(--necro-green); color: #000; }
        .status-badge.inactive { background: var(--dark-red); color: var(--text-secondary); }
        .bot-status-container { display: grid; grid-template-columns: 1fr 2fr; gap: 20px; margin-top: 15px; border-top: 1px solid var(--border-color); padding-top: 15px; }
        .bot-status-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
        .bot-status-item { display: flex; justify-content: space-between; align-items: center; padding: 5px 8px; background: rgba(0,0,0,0.3); border-radius: 4px; }
        .btn-toggle-state { padding: 3px 5px; font-size: 0.9em; border-radius: 4px; cursor: pointer; text-transform: uppercase; background: transparent; font-weight: 700; border: none; }
        .btn-rise { color: var(--necro-green); } .btn-rest { color: var(--dark-red); }
        .bot-main span:first-child { color: #FF4500; font-weight: 700; }
        .add-server-btn { display: flex; align-items: center; justify-content: center; min-height: 200px; border: 2px dashed var(--border-color); cursor: pointer; transition: all 0.3s ease; }
        .add-server-btn:hover { background: var(--secondary-bg); border-color: var(--blood-red); }
        .add-server-btn i { font-size: 3rem; color: var(--text-secondary); }
        .btn-delete-server { position: absolute; top: 15px; right: 15px; background: var(--dark-red); border: 1px solid var(--blood-red); color: var(--bone-white); width: auto; padding: 5px 10px; border-radius: 50%; }
        .server-sub-panel { border-top: 1px solid var(--border-color); margin-top: 20px; padding-top: 20px;}
        .flex-row { display:flex; gap: 10px; align-items: center;}
    </style>
</head>
<body>
    <div class="container">
        <div class="header"> <h1 class="title">Shadow Network Control</h1> </div>
        <div id="msg-status-container" class="msg-status"> <span id="msg-status-text"></span></div>
        <div class="main-grid">
            <div class="panel status-panel">
                <h2><i class="fas fa-heartbeat"></i> System Status</h2>
                <div class="bot-status-container">
                    <div class="status-grid">
                         <div class="status-row">
                            <span><i class="fas fa-redo"></i> Auto Reboot</span>
                            <div class="flex-row">
                                <input type="number" id="auto-reboot-delay" value="{{ auto_reboot_delay }}" style="width: 80px; text-align: right; padding: 5px;">
                                <span id="reboot-timer" class="timer-display">--:--:--</span>
                                <button type="button" id="auto-reboot-toggle-btn" class="btn btn-small">{{ 'DISABLE' if auto_reboot_enabled else 'ENABLE' }}</button>
                            </div>
                        </div>
                        <div class="status-row">
                            <span><i class="fas fa-server"></i> Uptime</span>
                            <div><span id="uptime-timer" class="timer-display">--:--:--</span></div>
                        </div>
                    </div>
                    <div id="bot-status-list" class="bot-status-grid"></div>
                </div>
            </div>

            {% for server in servers %}
            <div class="panel server-panel" data-server-id="{{ server.id }}">
                <button class="btn-delete-server" title="Delete Server"><i class="fas fa-times"></i></button>
                <h2><i class="fas fa-server"></i> {{ server.name }}</h2>
                
                <div class="server-sub-panel">
                    <h3><i class="fas fa-cogs"></i> Channel Config</h3>
                    <div class="input-group"><label>Main Channel ID</label><input type="text" class="channel-input" data-field="main_channel_id" value="{{ server.main_channel_id or '' }}"></div>
                    <div class="input-group"><label>KTB Channel ID</label><input type="text" class="channel-input" data-field="ktb_channel_id" value="{{ server.ktb_channel_id or '' }}"></div>
                    <div class="input-group"><label>Spam Channel ID</label><input type="text" class="channel-input" data-field="spam_channel_id" value="{{ server.spam_channel_id or '' }}"></div>
                </div>

                <div class="server-sub-panel">
                    <h3><i class="fas fa-crosshairs"></i> Soul Harvest</h3>
                    <div class="grab-section">
                        <h3>ALPHA</h3>
                        <div class="input-group">
                            <input type="number" class="harvest-threshold" data-node="1" value="{{ server.heart_threshold_1 or 50 }}" min="0">
                            <button type="button" class="btn harvest-toggle" data-node="1">
                                {{ 'DISABLE' if server.auto_grab_enabled_1 else 'ENABLE' }}
                            </button>
                        </div>
                    </div>
                    <div class="grab-section">
                        <h3>BETA</h3>
                        <div class="input-group">
                            <input type="number" class="harvest-threshold" data-node="2" value="{{ server.heart_threshold_2 or 50 }}" min="0">
                            <button type="button" class="btn harvest-toggle" data-node="2">
                                {{ 'DISABLE' if server.auto_grab_enabled_2 else 'ENABLE' }}
                            </button>
                        </div>
                    </div>
                     <div class="grab-section">
                        <h3>GAMMA</h3>
                        <div class="input-group">
                            <input type="number" class="harvest-threshold" data-node="3" value="{{ server.heart_threshold_3 or 50 }}" min="0">
                            <button type="button" class="btn harvest-toggle" data-node="3">
                                {{ 'DISABLE' if server.auto_grab_enabled_3 else 'ENABLE' }}
                            </button>
                        </div>
                    </div>
                </div>
                
                <div class="server-sub-panel">
                    <h3><i class="fas fa-paper-plane"></i> Auto Broadcast</h3>
                    <div class="input-group"><label>Message</label><textarea class="spam-message" rows="2">{{ server.spam_message or '' }}</textarea></div>
                    <div class="input-group">
                         <label>Delay (s)</label>
                         <input type="number" class="spam-delay" value="{{ server.spam_delay or 10 }}">
                         <span class="timer-display spam-timer">--:--:--</span>
                    </div>
                    <button type="button" class="btn broadcast-toggle">{{ 'DISABLE' if server.spam_enabled else 'ENABLE' }}</button>
                </div>
            </div>
            {% endfor %}

            <div class="panel add-server-btn" id="add-server-btn">
                <i class="fas fa-plus"></i>
            </div>
        </div>
    </div>
<script>
    document.addEventListener('DOMContentLoaded', function () {
        const msgStatusContainer = document.getElementById('msg-status-container');
        const msgStatusText = document.getElementById('msg-status-text');
        const mainGrid = document.querySelector('.main-grid');

        function showStatusMessage(message, isError = false) {
            if (!message) return;
            msgStatusText.textContent = message;
            msgStatusContainer.style.color = isError ? 'var(--blood-red)' : 'var(--necro-green)';
            msgStatusContainer.style.display = 'block';
            setTimeout(() => { msgStatusContainer.style.display = 'none'; }, 4000);
        }

        async function postData(url = '', data = {}) {
            try {
                const response = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await response.json();
                showStatusMessage(result.message, result.status !== 'success');
                if (result.status === 'success' && url !== '/api/save_settings') {
                    fetch('/api/save_settings', { method: 'POST' });
                    if (result.reload) {
                        setTimeout(() => window.location.reload(), 500);
                    }
                }
                setTimeout(fetchStatus, 500); // Refresh status after action
                return result;
            } catch (error) {
                console.error('Error:', error);
                showStatusMessage('Server communication error.', true);
            }
        }

        function formatTime(seconds) {
            if (isNaN(seconds) || seconds < 0) return "--:--:--";
            seconds = Math.floor(seconds);
            const h = Math.floor(seconds / 3600).toString().padStart(2, '0');
            const m = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
            const s = (seconds % 60).toString().padStart(2, '0');
            return `${h}:${m}:${s}`;
        }

        function updateElement(element, { textContent, className, value }) {
            if (!element) return;
            if (textContent !== undefined) element.textContent = textContent;
            if (className !== undefined) element.className = className;
            if (value !== undefined) element.value = value;
        }

        async function fetchStatus() {
            try {
                const response = await fetch('/status');
                const data = await response.json();
                
                // --- Update Global Status ---
                updateElement(document.getElementById('reboot-timer'), { textContent: formatTime(data.reboot_countdown) });
                updateElement(document.getElementById('auto-reboot-toggle-btn'), { textContent: data.reboot_enabled ? 'DISABLE' : 'ENABLE' });
                
                const serverUptimeSeconds = (Date.now() / 1000) - data.server_start_time;
                updateElement(document.getElementById('uptime-timer'), { textContent: formatTime(serverUptimeSeconds) });
                
                const botListContainer = document.getElementById('bot-status-list');
                botListContainer.innerHTML = ''; 
                const allBots = [...data.bot_statuses.main_bots, ...data.bot_statuses.sub_accounts];
                allBots.forEach(bot => {
                    const item = document.createElement('div');
                    item.className = 'bot-status-item';
                    if (bot.type === 'main') item.classList.add('bot-main');
                    const buttonText = bot.is_active ? 'ONLINE' : 'OFFLINE';
                    const buttonClass = bot.is_active ? 'btn-rise' : 'btn-rest';
                    item.innerHTML = `<span>${bot.name}</span><button type="button" data-target="${bot.reboot_id}" class="btn-toggle-state ${buttonClass}">${buttonText}</button>`;
                    botListContainer.appendChild(item);
                });

                // --- Update Per-Server Status ---
                data.servers.forEach(serverData => {
                    const serverPanel = document.querySelector(`.server-panel[data-server-id="${serverData.id}"]`);
                    if (!serverPanel) return;

                    // Harvest toggles
                    for(let i = 1; i <= 3; i++){
                        const btn = serverPanel.querySelector(`.harvest-toggle[data-node="${i}"]`);
                        updateElement(btn, { textContent: serverData[`auto_grab_enabled_${i}`] ? 'DISABLE' : 'ENABLE' });
                    }
                    
                    // Spam toggle
                    const spamToggleBtn = serverPanel.querySelector('.broadcast-toggle');
                    updateElement(spamToggleBtn, { textContent: serverData.spam_enabled ? 'DISABLE' : 'ENABLE' });
                    const spamTimer = serverPanel.querySelector('.spam-timer');
                    updateElement(spamTimer, { textContent: formatTime(serverData.spam_countdown)});

                });

            } catch (error) { console.error('Error fetching status:', error); }
        }
        setInterval(fetchStatus, 1000);

        // --- Event Listeners using Delegation ---
        mainGrid.addEventListener('click', e => {
            const target = e.target;
            const serverPanel = target.closest('.server-panel');
            if (!serverPanel) return;

            const serverId = serverPanel.dataset.serverId;
            
            // Harvest Toggle
            if (target.classList.contains('harvest-toggle')) {
                const node = target.dataset.node;
                const thresholdInput = serverPanel.querySelector(`.harvest-threshold[data-node="${node}"]`);
                postData('/api/harvest_toggle', { server_id: serverId, node: node, threshold: thresholdInput.value });
            }

            // Broadcast Toggle
            if (target.classList.contains('broadcast-toggle')) {
                const message = serverPanel.querySelector('.spam-message').value;
                const delay = serverPanel.querySelector('.spam-delay').value;
                postData('/api/broadcast_toggle', { server_id: serverId, message: message, delay: delay });
            }
            
            // Delete Server
            if (target.closest('.btn-delete-server')) {
                if(confirm('Are you sure you want to delete this server configuration?')) {
                    postData('/api/delete_server', { server_id: serverId });
                }
            }
        });

        mainGrid.addEventListener('change', e => {
            const target = e.target;
            const serverPanel = target.closest('.server-panel');
            if (!serverPanel) return;
            const serverId = serverPanel.dataset.serverId;

            // Channel ID change
            if(target.classList.contains('channel-input')) {
                const payload = { server_id: serverId };
                payload[target.dataset.field] = target.value;
                postData('/api/update_server_channels', payload);
            }
        });

        // Add Server Button
        document.getElementById('add-server-btn').addEventListener('click', () => {
            const name = prompt("Enter a name for the new server:", "New Server");
            if (name) {
                postData('/api/add_server', { name: name });
            }
        });

        // Global controls
        document.getElementById('auto-reboot-toggle-btn').addEventListener('click', () => {
             postData('/api/reboot_toggle_auto', { delay: document.getElementById('auto-reboot-delay').value });
        });
        
        document.getElementById('bot-status-list').addEventListener('click', e => {
            if(e.target.matches('button[data-target]')) {
                postData('/api/toggle_bot_state', { target: e.target.dataset.target });
            }
        });
    });
</script>
</body>
</html>
"""

# --- FLASK ROUTES ---
@app.route("/")
def index():
    # Sort servers by name for consistent order
    sorted_servers = sorted(servers, key=lambda s: s.get('name', ''))
    return render_template_string(HTML_TEMPLATE, servers=sorted_servers, auto_reboot_enabled=auto_reboot_enabled, auto_reboot_delay=auto_reboot_delay)

# --- SERVER MANAGEMENT API ---
@app.route("/api/add_server", methods=['POST'])
def api_add_server():
    data = request.get_json()
    name = data.get('name')
    if not name:
        return jsonify({'status': 'error', 'message': 'Server name is required.'}), 400
    
    new_server = {
        "id": f"server_{uuid.uuid4().hex}",
        "name": name,
        "main_channel_id": "",
        "ktb_channel_id": "",
        "spam_channel_id": "",
        "auto_grab_enabled_1": False, "heart_threshold_1": 50,
        "auto_grab_enabled_2": False, "heart_threshold_2": 50,
        "auto_grab_enabled_3": False, "heart_threshold_3": 50,
        "spam_enabled": False, "spam_message": "", "spam_delay": 10, "last_spam_time": 0
    }
    servers.append(new_server)
    return jsonify({'status': 'success', 'message': f'Server "{name}" added.', 'reload': True})

@app.route("/api/delete_server", methods=['POST'])
def api_delete_server():
    global servers
    data = request.get_json()
    server_id = data.get('server_id')
    
    server_to_delete = next((s for s in servers if s.get('id') == server_id), None)
    if server_to_delete:
        servers = [s for s in servers if s.get('id') != server_id]
        return jsonify({'status': 'success', 'message': f'Server "{server_to_delete.get("name")}" deleted.', 'reload': True})
    return jsonify({'status': 'error', 'message': 'Server not found.'}), 404

@app.route("/api/update_server_channels", methods=['POST'])
def api_update_server_channels():
    data = request.get_json()
    server_id = data.get('server_id')
    server = next((s for s in servers if s.get('id') == server_id), None)
    if not server:
        return jsonify({'status': 'error', 'message': 'Server not found.'}), 404
    
    updated_fields = []
    if 'main_channel_id' in data:
        server['main_channel_id'] = data['main_channel_id']
        updated_fields.append('Main Channel')
    if 'ktb_channel_id' in data:
        server['ktb_channel_id'] = data['ktb_channel_id']
        updated_fields.append('KTB Channel')
    if 'spam_channel_id' in data:
        server['spam_channel_id'] = data['spam_channel_id']
        updated_fields.append('Spam Channel')

    return jsonify({'status': 'success', 'message': f'{", ".join(updated_fields)} updated for {server["name"]}.'})

# --- CONTROL APIs (MODIFIED FOR MULTI-SERVER) ---
@app.route("/api/harvest_toggle", methods=['POST'])
def api_harvest_toggle():
    data = request.get_json()
    server_id = data.get('server_id')
    node = data.get('node')
    threshold = int(data.get('threshold', 50))
    
    server = next((s for s in servers if s.get('id') == server_id), None)
    if not server or not node:
        return jsonify({'status': 'error', 'message': 'Invalid request.'}), 400
        
    grab_key = f'auto_grab_enabled_{node}'
    threshold_key = f'heart_threshold_{node}'
    
    server[grab_key] = not server.get(grab_key, False)
    server[threshold_key] = threshold
    
    state = "ENABLED" if server[grab_key] else "DISABLED"
    msg = f"Harvest Node {node} was {state} for server {server['name']}."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/broadcast_toggle", methods=['POST'])
def api_broadcast_toggle():
    data = request.get_json()
    server_id = data.get('server_id')
    
    server = next((s for s in servers if s.get('id') == server_id), None)
    if not server:
        return jsonify({'status': 'error', 'message': 'Server not found.'}), 404

    server['spam_message'] = data.get("message", "").strip()
    server['spam_delay'] = int(data.get("delay", 10))

    if not server.get('spam_enabled') and server['spam_message'] and server['spam_channel_id']:
        server['spam_enabled'] = True
        server['last_spam_time'] = time.time()
        msg = f"Spam ENABLED for {server['name']}."
    else:
        server['spam_enabled'] = False
        msg = f"Spam DISABLED for {server['name']}."
        
    return jsonify({'status': 'success', 'message': msg})


# --- GLOBAL CONTROL APIS (UNCHANGED LOGIC) ---
@app.route("/api/reboot_toggle_auto", methods=['POST'])
def api_reboot_toggle_auto():
    global auto_reboot_enabled, auto_reboot_delay, auto_reboot_thread, auto_reboot_stop_event, last_reboot_cycle_time
    data = request.get_json()
    auto_reboot_enabled = not auto_reboot_enabled
    auto_reboot_delay = int(data.get("delay", 3600))
    msg = ""
    if auto_reboot_enabled:
        last_reboot_cycle_time = time.time()
        if auto_reboot_thread is None or not auto_reboot_thread.is_alive():
            auto_reboot_stop_event = threading.Event()
            auto_reboot_thread = threading.Thread(target=auto_reboot_loop, daemon=True)
            auto_reboot_thread.start()
        msg = "Global Auto Reboot ENABLED."
    else:
        if auto_reboot_stop_event: auto_reboot_stop_event.set()
        auto_reboot_thread = None
        msg = "Global Auto Reboot DISABLED."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/toggle_bot_state", methods=['POST'])
def api_toggle_bot_state():
    data = request.get_json()
    target = data.get('target')
    msg = ""
    if target in bot_active_states:
        bot_active_states[target] = not bot_active_states[target]
        state_text = "AWAKENED" if bot_active_states[target] else "DORMANT"
        msg = f"Target {target.upper()} has been set to {state_text}."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/save_settings", methods=['POST'])
def api_save_settings():
    save_settings()
    return jsonify({'status': 'success', 'message': 'Settings saved.'})


# --- STATUS ENDPOINT ---
@app.route("/status")
def status():
    now = time.time()
    reboot_countdown = (last_reboot_cycle_time + auto_reboot_delay - now) if auto_reboot_enabled else 0
    
    # Add countdown to each server object
    for server in servers:
        if server.get('spam_enabled'):
            server['spam_countdown'] = (server.get('last_spam_time', 0) + server.get('spam_delay', 10) - now)
        else:
            server['spam_countdown'] = 0

    bot_statuses = {
        "main_bots": [
            {"name": "ALPHA", "status": main_bot is not None, "reboot_id": "main_1", "is_active": bot_active_states.get('main_1', False), "type": "main"},
            {"name": "BETA", "status": main_bot_2 is not None, "reboot_id": "main_2", "is_active": bot_active_states.get('main_2', False), "type": "main"},
            {"name": "GAMMA", "status": main_bot_3 is not None, "reboot_id": "main_3", "is_active": bot_active_states.get('main_3', False), "type": "main"}
        ],
        "sub_accounts": []
    }
    with bots_lock:
        bot_statuses["sub_accounts"] = [
            {"name": acc_names[i] if i < len(acc_names) else f"Sub {i+1}", "status": bot is not None, "reboot_id": f"sub_{i}", "is_active": bot_active_states.get(f'sub_{i}', False), "type": "sub"}
            for i, bot in enumerate(bots)
        ]
    
    return jsonify({
        'reboot_enabled': auto_reboot_enabled, 
        'reboot_countdown': reboot_countdown,
        'bot_statuses': bot_statuses,
        'server_start_time': server_start_time,
        'servers': servers
    })

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    load_settings()
    
    print("Đang khởi tạo các bot...", flush=True)
    with bots_lock:
        if main_token: 
            main_bot = create_bot(main_token, is_main=True)
            if 'main_1' not in bot_active_states: bot_active_states['main_1'] = True
        if main_token_2: 
            main_bot_2 = create_bot(main_token_2, is_main_2=True)
            if 'main_2' not in bot_active_states: bot_active_states['main_2'] = True
        if main_token_3: 
            main_bot_3 = create_bot(main_token_3, is_main_3=True)
            if 'main_3' not in bot_active_states: bot_active_states['main_3'] = True
                
        for i, token in enumerate(tokens):
            if token.strip():
                bots.append(create_bot(token.strip()))
                if f'sub_{i}' not in bot_active_states: bot_active_states[f'sub_{i}'] = True

    print("Đang khởi tạo các luồng nền...", flush=True)
    threading.Thread(target=periodic_save_loop, daemon=True).start()
    
    # Start spam thread regardless, it will check internally if it needs to do anything
    spam_thread = threading.Thread(target=spam_loop, daemon=True)
    spam_thread.start()
    
    if auto_reboot_enabled:
        auto_reboot_stop_event = threading.Event()
        auto_reboot_thread = threading.Thread(target=auto_reboot_loop, daemon=True)
        auto_reboot_thread.start()
    
    port = int(os.environ.get("PORT", 10000))
    print(f"Khởi động Web Server tại http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
