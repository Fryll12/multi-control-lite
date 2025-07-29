# PHIÊN BẢN NÂNG CẤP - HỖ TRỢ N TÀI KHOẢN CHÍNH & EVENT GRAB
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
main_tokens = os.getenv("MAIN_TOKENS").split(",") if os.getenv("MAIN_TOKENS") else []
tokens = os.getenv("TOKENS").split(",") if os.getenv("TOKENS") else []
karuta_id = "646937666251915264"
karibbit_id = "1311684840462225440" # Yoru Bot ID
BOT_NAMES = [ # Tên để hiển thị trên giao diện, bạn có thể thêm nếu cần
    "ALPHA", "BETA", "GAMMA", "DELTA", "EPSILON",
    "ZETA", "ETA", "THETA", "IOTA", "KAPPA", "LAMBDA", "MU"
]
sub_acc_names_str = os.getenv("SUB_ACC_NAMES")
acc_names = [name.strip() for name in sub_acc_names_str.split(',')] if sub_acc_names_str else []


# --- BIẾN TRẠNG THÁI ---
bots = []
main_bots = []
servers = [] # Thay thế farm_servers bằng cấu trúc server mạnh mẽ hơn
watermelon_grab_states = {} # Cài đặt nhặt dưa hấu toàn cục

# Cài đặt toàn cục
auto_reboot_enabled = False
auto_reboot_delay = 3600
last_reboot_cycle_time = 0

# Các biến điều khiển luồng
auto_reboot_stop_event = threading.Event()
spam_thread, auto_reboot_thread = None, None
bots_lock = threading.Lock()
server_start_time = time.time()
bot_active_states = {}


# --- HÀM LƯU VÀ TẢI CÀI ĐẶT ---
def save_settings():
    """Lưu tất cả cài đặt (servers, reboot, states) lên JSONBin.io"""
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id: return
    settings = {
        'servers': servers,
        'auto_reboot_enabled': auto_reboot_enabled,
        'auto_reboot_delay': auto_reboot_delay,
        'bot_active_states': bot_active_states,
        'last_reboot_cycle_time': last_reboot_cycle_time,
        'watermelon_grab_states': watermelon_grab_states
    }
    headers = {'Content-Type': 'application/json', 'X-Master-Key': api_key}
    url = f"https://api.jsonbin.io/v3/b/{bin_id}"
    try:
        req = requests.put(url, json=settings, headers=headers, timeout=10)
        if req.status_code == 200:
            print("[Settings] Đã lưu cài đặt lên JSONBin.io.", flush=True)
        else:
            print(f"[Settings] Lỗi khi lưu cài đặt: {req.status_code}", flush=True)
    except Exception as e:
        print(f"[Settings] Exception khi lưu cài đặt: {e}", flush=True)

def load_settings():
    """Tải tất cả cài đặt từ JSONBin.io"""
    global servers, auto_reboot_enabled, auto_reboot_delay, bot_active_states, last_reboot_cycle_time, watermelon_grab_states
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id:
        print("[Settings] Thiếu API Key/Bin ID. Dùng cài đặt mặc định.", flush=True)
        return

    headers = {'X-Master-Key': api_key}
    url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"
    try:
        req = requests.get(url, headers=headers, timeout=10)
        if req.status_code == 200:
            settings = req.json().get("record", {})
            if settings:
                servers = settings.get('servers', [])
                auto_reboot_enabled = settings.get('auto_reboot_enabled', False)
                auto_reboot_delay = settings.get('auto_reboot_delay', 3600)
                bot_active_states = settings.get('bot_active_states', {})
                last_reboot_cycle_time = settings.get('last_reboot_cycle_time', 0)
                watermelon_grab_states = settings.get('watermelon_grab_states', {})
                print("[Settings] Đã tải cài đặt từ JSONBin.io.", flush=True)
            else:
                print("[Settings] JSONBin rỗng, bắt đầu với cài đặt mặc định.", flush=True)
                save_settings()
        else:
            print(f"[Settings] Lỗi khi tải cài đặt: {req.status_code}", flush=True)
    except Exception as e:
        print(f"[Settings] Exception khi tải cài đặt: {e}", flush=True)


# --- CÁC HÀM LOGIC BOT ---
def handle_grab(bot, msg, bot_num):
    channel_id = msg.get("channel_id")
    target_server = next((s for s in servers if s.get('main_channel_id') == channel_id), None)
    if not target_server: return

    auto_grab_enabled = target_server.get(f'auto_grab_enabled_{bot_num}', False)
    heart_threshold = target_server.get(f'heart_threshold_{bot_num}', 50)
    ktb_channel_id = target_server.get('ktb_channel_id')
    
    watermelon_grab_enabled = watermelon_grab_states.get(f'main_{bot_num}', False)

    if not auto_grab_enabled and not watermelon_grab_enabled:
        return

    if msg.get("author", {}).get("id") == karuta_id and "is dropping" not in msg.get("content", "") and not msg.get("mentions", []):
        last_drop_msg_id = msg["id"]
        
        def grab_handler():
            card_picked = False
            # BƯỚC 1: Ưu tiên nhặt thẻ theo tim (nếu được bật)
            if auto_grab_enabled and ktb_channel_id:
                time.sleep(0.5)
                try:
                    messages = bot.getMessages(channel_id, num=5).json()
                    for msg_item in messages:
                        if msg_item.get("author", {}).get("id") == karibbit_id and int(msg_item["id"]) > int(last_drop_msg_id):
                            if "embeds" in msg_item and len(msg_item["embeds"]) > 0:
                                desc = msg_item["embeds"][0].get("description", "")
                                if '♡' not in desc: continue
                                lines = desc.split('\n')
                                heart_numbers = [int(match.group(1)) if (match := re.search(r'♡(\d+)', line)) else 0 for line in lines[:3]]
                                if not any(heart_numbers): break 
                                max_num = max(heart_numbers)
                                if max_num >= heart_threshold:
                                    max_index = heart_numbers.index(max_num)
                                    delays = { 1: [0.4, 1.4, 2.1], 2: [0.7, 1.8, 2.4], 3: [0.7, 1.8, 2.4] }
                                    bot_delays = delays.get(bot_num, [0.9, 2.0, 2.6])
                                    emojis = ["1️⃣", "2️⃣", "3️⃣"]
                                    emoji, delay = emojis[max_index], bot_delays[max_index]
                                    print(f"[{target_server['name']} | Bot {bot_num}] Chọn dòng {max_index+1} với {max_num} tim -> Emoji {emoji} sau {delay}s", flush=True)
                                    def grab_action():
                                        bot.addReaction(channel_id, last_drop_msg_id, emoji)
                                        time.sleep(1)
                                        bot.sendMessage(ktb_channel_id, "kt b")
                                    threading.Timer(delay, grab_action).start()
                                    card_picked = True
                            if card_picked: break
                    if card_picked: return # Nếu đã nhặt thẻ thì không nhặt dưa hấu nữa
                except Exception as e:
                    print(f"Lỗi khi đọc Karibbit (Bot {bot_num} @ {target_server['name']}): {e}", flush=True)

            # BƯỚC 2: Kiểm tra và nhặt sự kiện Dưa hấu
            if watermelon_grab_enabled:
                try:
                    time.sleep(0.25) # Chờ 1 chút để reaction xuất hiện
                    full_msg_obj = bot.getMessage(channel_id, last_drop_msg_id).json()
                    if isinstance(full_msg_obj, list): full_msg_obj = full_msg_obj[0]
                    if 'reactions' in full_msg_obj:
                        if any(reaction['emoji']['name'] == '🍉' for reaction in full_msg_obj['reactions']):
                            print(f"[Event Grab | Bot {bot_num}] Phát hiện Dưa hấu! Tiến hành nhặt.", flush=True)
                            bot.addReaction(channel_id, last_drop_msg_id, "🍉")
                except Exception as e:
                    print(f"Lỗi khi kiểm tra sự kiện dưa hấu (Bot {bot_num}): {e}", flush=True)

        threading.Thread(target=grab_handler).start()

def create_bot(token, bot_identifier, is_main=False):
    bot = discum.Client(token=token, log=False)
    @bot.gateway.command
    def on_ready(resp):
        if resp.event.ready:
            user = resp.raw.get("user", {})
            if isinstance(user, dict) and (user_id := user.get("id")):
                bot_name = ""
                if is_main:
                    bot_name_index = bot_identifier - 1
                    bot_name = BOT_NAMES[bot_name_index] if bot_name_index < len(BOT_NAMES) else f"MAIN_{bot_identifier}"
                else:
                    bot_name = acc_names[bot_identifier] if bot_identifier < len(acc_names) else f"Sub {bot_identifier+1}"
                print(f"Đã đăng nhập: {user.get('username')} ({bot_name})", flush=True)

    if is_main:
        @bot.gateway.command
        def on_message(resp):
            if resp.event.message:
                handle_grab(bot, resp.parsed.auto(), bot_identifier)
            
    threading.Thread(target=bot.gateway.run, daemon=True).start()
    return bot

# --- VÒNG LẶP NỀN ---
def auto_reboot_loop():
    global last_reboot_cycle_time, main_bots
    while not auto_reboot_stop_event.is_set():
        try:
            if auto_reboot_enabled and (time.time() - last_reboot_cycle_time) >= auto_reboot_delay:
                print("[Reboot] Bắt đầu chu kỳ reboot tự động...", flush=True)
                with bots_lock:
                    rebooted_bots = []
                    for i, bot in enumerate(main_bots):
                        if bot and bot_active_states.get(f'main_{i+1}', False):
                            bot.gateway.close()
                            time.sleep(2) # Chờ đóng kết nối
                            new_bot = create_bot(main_tokens[i], bot_identifier=(i+1), is_main=True)
                            rebooted_bots.append(new_bot)
                            print(f"Đã reboot bot chính thứ {i+1}", flush=True)
                            time.sleep(5)
                        else:
                            rebooted_bots.append(bot) # Giữ lại bot cũ nếu không hoạt động
                    main_bots = rebooted_bots
                last_reboot_cycle_time = time.time()
                save_settings()
                print("[Reboot] Chu kỳ reboot tự động hoàn tất.", flush=True)
            
            interrupted = auto_reboot_stop_event.wait(timeout=60)
            if interrupted: break
        except Exception as e:
            print(f"[ERROR in auto_reboot_loop] {e}", flush=True)
            time.sleep(60)
    print("[Reboot] Luồng tự động reboot đã dừng.", flush=True)
    
def periodic_save_loop():
    while True:
        time.sleep(300) # Lưu mỗi 5 phút
        print("[Settings] Bắt đầu lưu định kỳ...", flush=True)
        save_settings()

def spam_loop():
    active_server_threads = {}
    while True:
        try:
            for server in servers:
                server_id = server.get('id')
                spam_is_on = server.get('spam_enabled') and server.get('spam_message') and server.get('spam_channel_id')
                
                if spam_is_on and server_id not in active_server_threads:
                    print(f"[Spam Control] Bắt đầu luồng spam cho: {server.get('name')}", flush=True)
                    stop_event = threading.Event()
                    thread = threading.Thread(target=spam_for_server, args=(server, stop_event), daemon=True)
                    thread.start()
                    active_server_threads[server_id] = (thread, stop_event)
                elif not spam_is_on and server_id in active_server_threads:
                    print(f"[Spam Control] Dừng luồng spam cho: {server.get('name')}", flush=True)
                    _, stop_event = active_server_threads.pop(server_id)
                    stop_event.set()
            
            # Dọn dẹp các thread đã chết
            for server_id, (thread, _) in list(active_server_threads.items()):
                if not thread.is_alive():
                    del active_server_threads[server_id]
            
            time.sleep(5)
        except Exception as e:
            print(f"[ERROR in spam_loop_manager] {e}", flush=True)
            time.sleep(5)

def spam_for_server(server_config, stop_event):
    server_name = server_config.get('name')
    channel_id = server_config.get('spam_channel_id')
    message = server_config.get('spam_message')
    while not stop_event.is_set():
        try:
            with bots_lock:
                active_bots = [bot for i, bot in enumerate(main_bots) if bot and bot_active_states.get(f'main_{i+1}', False)]
            
            delay = server_config.get('spam_delay', 10)
            for bot in active_bots:
                if stop_event.is_set(): break
                try:
                    bot.sendMessage(channel_id, message)
                    time.sleep(2) 
                except Exception as e:
                    print(f"Lỗi gửi spam từ bot tới {server_name}: {e}", flush=True)
            
            if not stop_event.is_set():
                stop_event.wait(timeout=delay)
        except Exception as e:
            print(f"[ERROR in spam_for_server {server_name}] {e}", flush=True)
            stop_event.wait(timeout=10)

# --- GIAO DIỆN WEB ---
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shadow Network Control</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Courier+Prime:wght@400;700&family=Nosifer&display=swap" rel="stylesheet">
    <style>
        :root { --primary-bg: #0a0a0a; --secondary-bg: #1a1a1a; --panel-bg: #111111; --border-color: #333333; --blood-red: #8b0000; --dark-red: #550000; --bone-white: #f8f8ff; --necro-green: #228b22; --text-primary: #f0f0f0; --text-secondary: #cccccc; }
        body { font-family: 'Courier Prime', monospace; background: var(--primary-bg); color: var(--text-primary); margin: 0; padding: 20px;}
        .container { max-width: 1800px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; padding: 20px; border-bottom: 2px solid var(--blood-red); }
        .title { font-family: 'Nosifer', cursive; font-size: 2.5rem; color: var(--blood-red); }
        .main-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(550px, 1fr)); gap: 20px; }
        .panel { background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 25px; position: relative;}
        .panel h2 { font-family: 'Orbitron', cursive; font-size: 1.4rem; margin-bottom: 20px; text-transform: uppercase; border-bottom: 2px solid; padding-bottom: 10px; color: var(--bone-white); }
        .panel h2 i { margin-right: 10px; }
        .btn { background: var(--secondary-bg); border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 4px; cursor: pointer; font-family: 'Orbitron', monospace; font-weight: 700; text-transform: uppercase; width: 100%; }
        .btn-small { padding: 5px 10px; font-size: 0.9em; width: auto;}
        .input-group { display: flex; align-items: stretch; margin-bottom: 15px; }
        .input-group label { background: #000; border: 1px solid var(--border-color); border-right: 0; padding: 10px 15px; border-radius: 4px 0 0 4px; display:flex; align-items:center; min-width: 140px;}
        .input-group input, .input-group textarea { flex-grow: 1; background: #000; border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 0 4px 4px 0; font-family: 'Courier Prime', monospace; }
        .grab-section { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; padding: 10px; background: rgba(0,0,0,0.2); border-radius: 8px;}
        .grab-section h3 { margin: 0; font-size: 1em; width: 80px; flex-shrink: 0; }
        .grab-section .input-group { margin-bottom: 0; flex-grow: 1; margin-left: 15px;}
        .msg-status { text-align: center; color: var(--necro-green); padding: 12px; border: 1px dashed var(--border-color); border-radius: 4px; margin-bottom: 20px; display: none; }
        .status-panel, .global-settings-panel { grid-column: 1 / -1; }
        .status-grid { display: grid; grid-template-columns: 1fr 2fr; gap: 20px; align-items: start;}
        .status-col { display: flex; flex-direction: column; gap: 15px; }
        .status-row { display: flex; justify-content: space-between; align-items: center; padding: 12px; background: rgba(0,0,0,0.6); border-radius: 8px; }
        .timer-display { font-size: 1.2em; font-weight: 700; }
        .bot-status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; }
        .bot-status-item { display: flex; justify-content: space-between; align-items: center; padding: 5px 8px; background: rgba(0,0,0,0.3); border-radius: 4px; }
        .btn-toggle-state { padding: 3px 5px; font-size: 0.9em; border-radius: 4px; cursor: pointer; text-transform: uppercase; background: transparent; font-weight: 700; border: none; }
        .btn-rise { color: var(--necro-green); } .btn-rest { color: var(--dark-red); }
        .bot-main span:first-child { color: #FF4500; font-weight: 700; }
        .add-server-btn { display: flex; align-items: center; justify-content: center; min-height: 200px; border: 2px dashed var(--border-color); cursor: pointer; transition: all 0.3s ease; }
        .add-server-btn:hover { background: var(--secondary-bg); border-color: var(--blood-red); }
        .add-server-btn i { font-size: 3rem; color: var(--text-secondary); }
        .btn-delete-server { position: absolute; top: 15px; right: 15px; background: var(--dark-red); border: 1px solid var(--blood-red); color: var(--bone-white); width: auto; padding: 5px 10px; border-radius: 8px; }
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
                <div class="status-grid">
                     <div class="status-col">
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

            <div class="panel global-settings-panel">
                <h2><i class="fas fa-globe"></i> Global Event Settings</h2>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-watermelon-slice"></i> Watermelon Grab (All Servers)</h3>
                    <div id="global-watermelon-grid" class="bot-status-grid" style="grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));">
                        </div>
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
                    <h3><i class="fas fa-crosshairs"></i> Soul Harvest (Card Grab)</h3>
                    {% for bot in main_bots_info %}
                    <div class="grab-section">
                        <h3>{{ bot.name }}</h3>
                        <div class="input-group">
                             <label style="min-width: 50px;">♡ &gt;=</label>
                            <input type="number" class="harvest-threshold" data-node="{{ bot.id }}" value="{{ server['heart_threshold_' + bot.id|string] or 50 }}" min="0">
                            <button type="button" class="btn btn-small harvest-toggle" data-node="{{ bot.id }}">
                                {{ 'DISABLE' if server['auto_grab_enabled_' + bot.id|string] else 'ENABLE' }}
                            </button>
                        </div>
                    </div>
                    {% endfor %}
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
        
        function showStatusMessage(message, isError = false) { if (!message) return; msgStatusText.textContent = message; msgStatusContainer.style.color = isError ? 'var(--blood-red)' : 'var(--necro-green)'; msgStatusContainer.style.display = 'block'; setTimeout(() => { msgStatusContainer.style.display = 'none'; }, 4000); }
        async function postData(url = '', data = {}) {
            try {
                const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
                if (!response.ok) { throw new Error(`HTTP error! Status: ${response.status}`); }
                const result = await response.json();
                showStatusMessage(result.message, result.status !== 'success');
                if (result.status === 'success') {
                    if (result.reload) { setTimeout(() => window.location.reload(), 500); }
                    else { setTimeout(fetchStatus, 500); } // Refresh status after successful action
                }
                return result;
            } catch (error) { console.error('Error:', error); showStatusMessage('Server communication error.', true); }
        }
        function formatTime(seconds) { if (isNaN(seconds) || seconds < 0) return "--:--:--"; seconds = Math.floor(seconds); const h = Math.floor(seconds / 3600).toString().padStart(2, '0'); const m = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0'); const s = (seconds % 60).toString().padStart(2, '0'); return `${h}:${m}:${s}`; }
        function updateElement(element, { textContent, className, value, innerHTML }) { if (!element) return; if (textContent !== undefined) element.textContent = textContent; if (className !== undefined) element.className = className; if (value !== undefined) element.value = value; if (innerHTML !== undefined) element.innerHTML = innerHTML; }
        
        async function fetchStatus() {
            try {
                const response = await fetch('/status');
                const data = await response.json();
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

                const wmGrid = document.getElementById('global-watermelon-grid');
                wmGrid.innerHTML = '';
                if (data.watermelon_grab_states && data.bot_statuses) {
                    data.bot_statuses.main_bots.forEach(bot => {
                        const botNodeId = bot.reboot_id;
                        const isEnabled = data.watermelon_grab_states[botNodeId];
                        const item = document.createElement('div');
                        item.className = 'bot-status-item';
                        item.innerHTML = `<span>${bot.name}</span>
                            <button type="button" class="btn btn-small watermelon-toggle" data-node="${botNodeId}">
                                <i class="fas fa-watermelon-slice"></i>&nbsp;${isEnabled ? 'DISABLE' : 'ENABLE'}
                            </button>`;
                        wmGrid.appendChild(item);
                    });
                }
                
                data.servers.forEach(serverData => {
                    const serverPanel = document.querySelector(`.server-panel[data-server-id="${serverData.id}"]`);
                    if (!serverPanel) return;
                    serverPanel.querySelectorAll('.harvest-toggle').forEach(btn => {
                        const node = btn.dataset.node;
                        updateElement(btn, { textContent: serverData[`auto_grab_enabled_${node}`] ? 'DISABLE' : 'ENABLE' });
                    });
                    updateElement(serverPanel.querySelector('.broadcast-toggle'), { textContent: serverData.spam_enabled ? 'DISABLE' : 'ENABLE' });
                    // Note: Spam timer is not implemented in this version to reduce complexity
                });
            } catch (error) { console.error('Error fetching status:', error); }
        }
        
        setInterval(fetchStatus, 2000); // Refresh every 2 seconds
        
        document.body.addEventListener('click', e => {
            const button = e.target.closest('button');
            if (!button) return;

            if (button.classList.contains('watermelon-toggle')) {
                postData('/api/watermelon_toggle', { node: button.dataset.node });
                return;
            }

            const serverPanel = button.closest('.server-panel');
            if (serverPanel) {
                const serverId = serverPanel.dataset.serverId;
                if (button.classList.contains('harvest-toggle')) { 
                    const thresholdInput = serverPanel.querySelector(`.harvest-threshold[data-node="${button.dataset.node}"]`); 
                    postData('/api/harvest_toggle', { server_id: serverId, node: button.dataset.node, threshold: thresholdInput.value }); 
                } else if (button.classList.contains('broadcast-toggle')) { 
                    const message = serverPanel.querySelector('.spam-message').value; 
                    const delay = serverPanel.querySelector('.spam-delay').value; 
                    postData('/api/broadcast_toggle', { server_id: serverId, message: message, delay: delay }); 
                } else if (button.classList.contains('btn-delete-server')) { 
                    if(confirm('Are you sure you want to delete this server configuration?')) { postData('/api/delete_server', { server_id: serverId }); } 
                }
                return;
            }
            
            if (button.id === 'auto-reboot-toggle-btn') {
                postData('/api/reboot_toggle_auto', { delay: document.getElementById('auto-reboot-delay').value });
            } else if (button.matches('#bot-status-list button[data-target]')) {
                postData('/api/toggle_bot_state', { target: button.dataset.target });
            } else if (button.closest('#add-server-btn')) {
                const name = prompt("Enter a name for the new server:", "New Server"); 
                if (name) { postData('/api/add_server', { name: name }); }
            }
        });

        document.body.addEventListener('change', e => {
            const target = e.target;
            const serverPanel = target.closest('.server-panel');
            if (serverPanel && target.classList.contains('channel-input')) {
                const serverId = serverPanel.dataset.serverId;
                const payload = { server_id: serverId, [target.dataset.field]: target.value };
                postData('/api/update_server_channels', payload);
            }
        });

        fetchStatus(); // Initial fetch
    });
</script>
</body>
</html>
"""

# --- FLASK ROUTES ---
@app.route("/")
def index():
    sorted_servers = sorted(servers, key=lambda s: s.get('name', ''))
    main_bots_info = [
        {"id": i + 1, "name": BOT_NAMES[i] if i < len(BOT_NAMES) else f"MAIN_{i+1}"}
        for i in range(len(main_tokens))
    ]
    return render_template_string(HTML_TEMPLATE, servers=sorted_servers, auto_reboot_enabled=auto_reboot_enabled, auto_reboot_delay=auto_reboot_delay, main_bots_info=main_bots_info)

@app.route("/api/add_server", methods=['POST'])
def api_add_server():
    data = request.get_json()
    name = data.get('name')
    if not name: return jsonify({'status': 'error', 'message': 'Tên server là bắt buộc.'}), 400
    
    new_server = {
        "id": f"server_{uuid.uuid4().hex}", "name": name,
        "main_channel_id": "", "ktb_channel_id": "", "spam_channel_id": "",
        "spam_enabled": False, "spam_message": "", "spam_delay": 10
    }
    for i in range(len(main_tokens)):
        bot_num = i + 1
        new_server[f'auto_grab_enabled_{bot_num}'] = False
        new_server[f'heart_threshold_{bot_num}'] = 50

    servers.append(new_server)
    save_settings()
    return jsonify({'status': 'success', 'message': f'Server "{name}" đã được thêm.', 'reload': True})

@app.route("/api/delete_server", methods=['POST'])
def api_delete_server():
    global servers
    server_id = request.get_json().get('server_id')
    server_name = "Unknown"
    original_len = len(servers)
    
    filtered_servers = [s for s in servers if s.get('id') != server_id]
    
    if len(filtered_servers) < original_len:
        servers = filtered_servers
        save_settings()
        return jsonify({'status': 'success', 'message': f'Server đã được xóa.', 'reload': True})
    return jsonify({'status': 'error', 'message': 'Không tìm thấy server.'}), 404

@app.route("/api/update_server_channels", methods=['POST'])
def api_update_server_channels():
    data = request.get_json()
    server = next((s for s in servers if s.get('id') == data.get('server_id')), None)
    if not server: return jsonify({'status': 'error', 'message': 'Không tìm thấy server.'}), 404
    
    updated_fields = []
    for field in ['main_channel_id', 'ktb_channel_id', 'spam_channel_id']:
        if field in data:
            server[field] = data[field]
            updated_fields.append(field.replace('_', ' ').replace(' id', '').title())
            
    if updated_fields:
        save_settings()
        return jsonify({'status': 'success', 'message': f'Kênh {", ".join(updated_fields)} đã được cập nhật cho {server["name"]}.'})
    return jsonify({'status': 'no_change', 'message': 'Không có gì thay đổi.'})

@app.route("/api/harvest_toggle", methods=['POST'])
def api_harvest_toggle():
    data = request.get_json()
    server = next((s for s in servers if s.get('id') == data.get('server_id')), None)
    node = data.get('node')
    if not server or not node: return jsonify({'status': 'error', 'message': 'Yêu cầu không hợp lệ.'}), 400
    
    grab_key = f'auto_grab_enabled_{node}'
    threshold_key = f'heart_threshold_{node}'
    server[grab_key] = not server.get(grab_key, False)
    server[threshold_key] = int(data.get('threshold', 50))
    state = "BẬT" if server[grab_key] else "TẮT"
    bot_name_index = int(node)-1
    bot_name = BOT_NAMES[bot_name_index] if bot_name_index < len(BOT_NAMES) else f"MAIN_{node}"
    msg = f"Nhặt thẻ cho {bot_name} đã được {state} tại server {server['name']}."
    save_settings()
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/watermelon_toggle", methods=['POST'])
def api_watermelon_toggle():
    global watermelon_grab_states
    data = request.get_json()
    node = data.get('node') # e.g., 'main_1'
    if not node or node not in watermelon_grab_states:
        return jsonify({'status': 'error', 'message': 'Bot không hợp lệ.'}), 404
    
    watermelon_grab_states[node] = not watermelon_grab_states.get(node, False)
    state = "BẬT" if watermelon_grab_states[node] else "TẮT"
    try:
        bot_name_index = int(node.split('_')[1]) - 1
        bot_name = BOT_NAMES[bot_name_index] if bot_name_index < len(BOT_NAMES) else node.upper()
    except (IndexError, ValueError):
        bot_name = node.upper()

    msg = f"Nhặt Dưa Hấu Toàn Cục đã được {state} cho {bot_name}."
    save_settings()
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/broadcast_toggle", methods=['POST'])
def api_broadcast_toggle():
    data = request.get_json()
    server = next((s for s in servers if s.get('id') == data.get('server_id')), None)
    if not server: return jsonify({'status': 'error', 'message': 'Không tìm thấy server.'}), 404
    
    server['spam_message'] = data.get("message", "").strip()
    server['spam_delay'] = int(data.get("delay", 10))
    server['spam_enabled'] = not server.get('spam_enabled', False)
    
    if server['spam_enabled'] and (not server['spam_message'] or not server['spam_channel_id']):
        server['spam_enabled'] = False
        return jsonify({'status': 'error', 'message': f'Cần có tin nhắn và kênh spam cho server {server["name"]}.'})
    
    msg = f"Spam đã được {'BẬT' if server['spam_enabled'] else 'TẮT'} cho server {server['name']}."
    save_settings()
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/reboot_toggle_auto", methods=['POST'])
def api_reboot_toggle_auto():
    global auto_reboot_enabled, auto_reboot_delay, auto_reboot_thread, auto_reboot_stop_event, last_reboot_cycle_time
    data = request.get_json()
    auto_reboot_enabled = not auto_reboot_enabled
    auto_reboot_delay = int(data.get("delay", 3600))
    if auto_reboot_enabled:
        last_reboot_cycle_time = time.time()
        if auto_reboot_thread is None or not auto_reboot_thread.is_alive():
            auto_reboot_stop_event = threading.Event()
            auto_reboot_thread = threading.Thread(target=auto_reboot_loop, daemon=True)
            auto_reboot_thread.start()
        msg = "Auto Reboot Toàn Cục ĐÃ BẬT."
    else:
        if auto_reboot_stop_event: auto_reboot_stop_event.set()
        auto_reboot_thread = None
        msg = "Auto Reboot Toàn Cục ĐÃ TẮT."
    save_settings()
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/toggle_bot_state", methods=['POST'])
def api_toggle_bot_state():
    target = request.get_json().get('target')
    if target in bot_active_states:
        bot_active_states[target] = not bot_active_states[target]
        state_text = "KÍCH HOẠT" if bot_active_states[target] else "NGHỈ"
        save_settings()
        return jsonify({'status': 'success', 'message': f"Mục tiêu {target.upper()} đã được đặt thành {state_text}."})
    return jsonify({'status': 'error', 'message': 'Không tìm thấy mục tiêu.'}), 404

@app.route("/status")
def status():
    now = time.time()
    reboot_countdown = (last_reboot_cycle_time + auto_reboot_delay - now) if auto_reboot_enabled else 0
        
    with bots_lock:
        main_bot_statuses = [
            {"name": BOT_NAMES[i] if i < len(BOT_NAMES) else f"MAIN_{i+1}", "reboot_id": f"main_{i+1}", "is_active": bot_active_states.get(f"main_{i+1}", False), "type": "main"} 
            for i, bot in enumerate(main_bots)
        ]
        sub_bot_statuses = [
            {"name": acc_names[i] if i < len(acc_names) else f"Sub {i+1}", "reboot_id": f"sub_{i}", "is_active": bot_active_states.get(f"sub_{i}", False), "type": "sub"}
            for i, bot in enumerate(bots)
        ]

    return jsonify({
        'reboot_enabled': auto_reboot_enabled, 
        'reboot_countdown': reboot_countdown,
        'bot_statuses': {"main_bots": main_bot_statuses, "sub_accounts": sub_bot_statuses},
        'server_start_time': server_start_time,
        'servers': servers,
        'watermelon_grab_states': watermelon_grab_states
    })

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    load_settings()
    
    print("Đang khởi tạo các bot...", flush=True)
    with bots_lock:
        for i, token in enumerate(main_tokens):
            if token.strip():
                bot_num = i + 1
                bot_id = f"main_{bot_num}"
                main_bots.append(create_bot(token.strip(), bot_identifier=bot_num, is_main=True))
                if bot_id not in bot_active_states: bot_active_states[bot_id] = True
                if bot_id not in watermelon_grab_states: watermelon_grab_states[bot_id] = False
        
        for i, token in enumerate(tokens):
            if token.strip():
                bot_id = f'sub_{i}'
                bots.append(create_bot(token.strip(), bot_identifier=i, is_main=False))
                if bot_id not in bot_active_states: bot_active_states[bot_id] = True

    print("Đang khởi tạo các luồng nền...", flush=True)
    threading.Thread(target=periodic_save_loop, daemon=True).start()
    threading.Thread(target=spam_loop, daemon=True).start()
    
    if auto_reboot_enabled:
        auto_reboot_stop_event = threading.Event()
        auto_reboot_thread = threading.Thread(target=auto_reboot_loop, daemon=True)
        auto_reboot_thread.start()
    
    port = int(os.environ.get("PORT", 10000))
    print(f"Khởi động Web Server tại http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
