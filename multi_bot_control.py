import discum
import threading
import time
import os
import re
import requests
import json
from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv

load_dotenv()

# --- CẤU HÌNH ---
main_token = os.getenv("MAIN_TOKEN")
main_token_2 = os.getenv("MAIN_TOKEN_2")
main_token_3 = os.getenv("MAIN_TOKEN_3")
tokens = os.getenv("TOKENS").split(",") if os.getenv("TOKENS") else []
main_channel_id = os.getenv("MAIN_CHANNEL_ID")
ktb_channel_id = os.getenv("KTB_CHANNEL_ID")
spam_channel_id = os.getenv("SPAM_CHANNEL_ID")
karuta_id = "646937666251915264"
karibbit_id = "1311684840462225440"

# --- BIẾN TRẠNG THÁI ---
bots, acc_names = [], [
    "Blacklist", "Khanh bang", "Dersale", "Venus", "WhyK", "Tan",
    "Ylang", "Nina", "Nathan", "Ofer", "White", "the Wicker", "Leader", "Tess", "Wyatt", "Daisy", "CantStop", "Token",
]
main_bot, main_bot_2, main_bot_3 = None, None, None
auto_grab_enabled, auto_grab_enabled_2, auto_grab_enabled_3 = False, False, False
heart_threshold, heart_threshold_2, heart_threshold_3 = 50, 50, 50
spam_enabled, auto_reboot_enabled = False, False
spam_message, spam_delay, auto_reboot_delay = "", 10, 3600
last_reboot_cycle_time, last_spam_time = 0, 0
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
    if not api_key or not bin_id: return

    settings = {
        'auto_grab_enabled': auto_grab_enabled, 'heart_threshold': heart_threshold,
        'auto_grab_enabled_2': auto_grab_enabled_2, 'heart_threshold_2': heart_threshold_2,
        'auto_grab_enabled_3': auto_grab_enabled_3, 'heart_threshold_3': heart_threshold_3,
        'spam_enabled': spam_enabled, 'spam_message': spam_message, 'spam_delay': spam_delay,
        'auto_reboot_enabled': auto_reboot_enabled, 'auto_reboot_delay': auto_reboot_delay,
        'bot_active_states': bot_active_states,
        'last_reboot_cycle_time': last_reboot_cycle_time,
        'last_spam_time': last_spam_time,
    }
    headers = {'Content-Type': 'application/json', 'X-Master-Key': api_key}
    url = f"https://api.jsonbin.io/v3/b/{bin_id}"
    try:
        req = requests.put(url, json=settings, headers=headers, timeout=10)
        if req.status_code == 200:
            print("[Settings] Đã lưu cài đặt lên JSONBin.io.", flush=True)
        else:
            print(f"[Settings] Lỗi khi lưu: {req.status_code}", flush=True)
    except Exception as e:
        print(f"[Settings] Exception khi lưu: {e}", flush=True)

def load_settings():
    """Tải cài đặt từ JSONBin.io"""
    try:
        api_key = os.getenv("JSONBIN_API_KEY")
        bin_id = os.getenv("JSONBIN_BIN_ID")
        if not api_key or not bin_id: return
        headers = {'X-Master-Key': api_key, 'X-Bin-Meta': 'false'}
        url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"
        req = requests.get(url, headers=headers, timeout=10)
        if req.status_code == 200:
            settings = req.json()
            if settings: 
                globals().update(settings)
                print("[Settings] Đã tải cài đặt từ JSONBin.", flush=True)
    except Exception: pass

def periodic_save_loop():
    """Vòng lặp nền để tự động lưu cài đặt 10 tiếng một lần."""
    while True:
        time.sleep(40000) # 36000 giây = 10 tiếng
        print("[Settings] Bắt đầu lưu định kỳ...", flush=True)
        save_settings()

# --- CÁC HÀM LOGIC BOT ---
def reboot_bot(target_id):
    global main_bot, main_bot_2, main_bot_3
    with bots_lock:
        print(f"[Reboot] Nhận được yêu cầu reboot cho target: {target_id}", flush=True)
        if target_id == 'main_1' and main_token:
            try: 
                if main_bot: main_bot.gateway.close()
            except Exception as e: print(f"[Reboot] Lỗi khi đóng Acc Chính 1: {e}", flush=True)
            main_bot = create_bot(main_token, is_main=True)
            print("[Reboot] Acc Chính 1 đã được khởi động lại.", flush=True)
        elif target_id == 'main_2' and main_token_2:
            try: 
                if main_bot_2: main_bot_2.gateway.close()
            except Exception as e: print(f"[Reboot] Lỗi khi đóng Acc Chính 2: {e}", flush=True)
            main_bot_2 = create_bot(main_token_2, is_main_2=True)
            print("[Reboot] Acc Chính 2 đã được khởi động lại.", flush=True)
        elif target_id == 'main_3' and main_token_3:
            try: 
                if main_bot_3: main_bot_3.gateway.close()
            except Exception as e: print(f"[Reboot] Lỗi khi đóng Acc Chính 3: {e}", flush=True)
            main_bot_3 = create_bot(main_token_3, is_main_3=True)
            print("[Reboot] Acc Chính 3 đã được khởi động lại.", flush=True)

def create_bot(token, is_main=False, is_main_2=False, is_main_3=False):
    bot = discum.Client(token=token, log=False)
    @bot.gateway.command
    def on_ready(resp):
        if resp.event.ready:
            user_data = resp.raw.get("user")
            if isinstance(user_data, dict):
                user_id = user_data.get("id")
                if user_id:
                    if is_main: bot_type = "(ALPHA)"
                    elif is_main_2: bot_type = "(BETA)"
                    elif is_main_3: bot_type = "(GAMMA)"
                    else: bot_type = ""
                    print(f"Đã đăng nhập: {user_id} {bot_type}", flush=True)

    @bot.gateway.command
    def on_message(resp):
        if resp.event.message:
            msg = resp.parsed.auto()
            # Grab cho Bot 1
            if is_main and auto_grab_enabled and msg.get("author", {}).get("id") == karuta_id and msg.get("channel_id") == main_channel_id and "is dropping" not in msg.get("content", "") and not msg.get("mentions", []):
                last_drop_msg_id = msg["id"]
                def read_karibbit():
                    time.sleep(0.5)
                    try:
                        messages = bot.getMessages(main_channel_id, num=5).json()
                        for msg_item in messages:
                            if msg_item.get("author", {}).get("id") == karibbit_id and "embeds" in msg_item and len(msg_item["embeds"]) > 0:
                                desc = msg_item["embeds"][0].get("description", "")
                                lines = desc.split('\n')
                                heart_numbers = [int(re.search(r'♡(\d+)', line).group(1)) if re.search(r'♡(\d+)', line) else 0 for line in lines[:3]]
                                max_num = max(heart_numbers)
                                if sum(heart_numbers) > 0 and max_num >= heart_threshold:
                                    max_index = heart_numbers.index(max_num)
                                    emoji, delay = [("1️⃣", 0.4), ("2️⃣", 1.4), ("3️⃣", 2.1)][max_index]
                                    print(f"[Bot 1] Chọn dòng {max_index+1} với {max_num} tim -> Emoji {emoji} sau {delay}s", flush=True)
                                    def grab():
                                        bot.addReaction(main_channel_id, last_drop_msg_id, emoji)
                                        time.sleep(1); bot.sendMessage(ktb_channel_id, "kt b")
                                    threading.Timer(delay, grab).start()
                                break
                    except Exception as e: print(f"Lỗi khi đọc tin nhắn (Bot 1): {e}", flush=True)
                threading.Thread(target=read_karibbit).start()
            
            # Grab cho Bot 2
            if is_main_2 and auto_grab_enabled_2 and msg.get("author", {}).get("id") == karuta_id and msg.get("channel_id") == main_channel_id and "is dropping" not in msg.get("content", "") and not msg.get("mentions", []):
                last_drop_msg_id = msg["id"]
                def read_karibbit_2():
                    time.sleep(0.5)
                    try:
                        messages = bot.getMessages(main_channel_id, num=5).json()
                        for msg_item in messages:
                            if msg_item.get("author", {}).get("id") == karibbit_id and "embeds" in msg_item and len(msg_item["embeds"]) > 0:
                                desc = msg_item["embeds"][0].get("description", "")
                                lines = desc.split('\n')
                                heart_numbers = [int(re.search(r'♡(\d+)', line).group(1)) if re.search(r'♡(\d+)', line) else 0 for line in lines[:3]]
                                max_num = max(heart_numbers)
                                if sum(heart_numbers) > 0 and max_num >= heart_threshold_2:
                                    max_index = heart_numbers.index(max_num)
                                    emoji, delay = [("1️⃣", 0.7), ("2️⃣", 1.8), ("3️⃣", 2.4)][max_index]
                                    print(f"[Bot 2] Chọn dòng {max_index+1} với {max_num} tim -> Emoji {emoji} sau {delay}s", flush=True)
                                    def grab_2():
                                        bot.addReaction(main_channel_id, last_drop_msg_id, emoji)
                                        time.sleep(1); bot.sendMessage(ktb_channel_id, "kt b")
                                    threading.Timer(delay, grab_2).start()
                                break
                    except Exception as e: print(f"Lỗi khi đọc tin nhắn (Bot 2): {e}", flush=True)
                threading.Thread(target=read_karibbit_2).start()
                
            # Grab cho Bot 3
            if is_main_3 and auto_grab_enabled_3 and msg.get("author", {}).get("id") == karuta_id and msg.get("channel_id") == main_channel_id and "is dropping" not in msg.get("content", "") and not msg.get("mentions", []):
                last_drop_msg_id = msg["id"]
                def read_karibbit_3():
                    time.sleep(0.5)
                    try:
                        messages = bot.getMessages(main_channel_id, num=5).json()
                        for msg_item in messages:
                            if msg_item.get("author", {}).get("id") == karibbit_id and "embeds" in msg_item and len(msg_item["embeds"]) > 0:
                                desc = msg_item["embeds"][0].get("description", "")
                                lines = desc.split('\n')
                                heart_numbers = [int(re.search(r'♡(\d+)', line).group(1)) if re.search(r'♡(\d+)', line) else 0 for line in lines[:3]]
                                max_num = max(heart_numbers)
                                if sum(heart_numbers) > 0 and max_num >= heart_threshold_3:
                                    max_index = heart_numbers.index(max_num)
                                    emoji, delay = [("1️⃣", 0.7), ("2️⃣", 1.8), ("3️⃣", 2.4)][max_index]
                                    print(f"[Bot 3] Chọn dòng {max_index+1} với {max_num} tim -> Emoji {emoji} sau {delay}s", flush=True)
                                    def grab_3():
                                        bot.addReaction(main_channel_id, last_drop_msg_id, emoji)
                                        time.sleep(1); bot.sendMessage(ktb_channel_id, "kt b")
                                    threading.Timer(delay, grab_3).start()
                                break
                    except Exception as e: print(f"Lỗi khi đọc tin nhắn (Bot 3): {e}", flush=True)
                threading.Thread(target=read_karibbit_3).start()

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
                if main_bot: reboot_bot('main_1'); time.sleep(5)
                if main_bot_2: reboot_bot('main_2'); time.sleep(5)
                if main_bot_3: reboot_bot('main_3')
                last_reboot_cycle_time = time.time()
        except Exception as e:
            print(f"[ERROR in auto_reboot_loop] {e}", flush=True); time.sleep(60)
    print("[Reboot] Luồng tự động reboot đã dừng.", flush=True)

def spam_loop():
    global last_spam_time
    while True:
        try:
            if spam_enabled and spam_message:
                if (time.time() - last_spam_time) >= spam_delay:
                    with bots_lock:
                        bots_to_spam = [bot for i, bot in enumerate(bots) if bot and bot_active_states.get(f'sub_{i}', False)]
                    for bot in bots_to_spam:
                        if not spam_enabled: break
                        try:
                            bot.sendMessage(spam_channel_id, spam_message)
                        except Exception as e: print(f"Lỗi gửi spam: {e}", flush=True)
                        time.sleep(2)
                    if spam_enabled:
                        last_spam_time = time.time()
            time.sleep(1)
        except Exception as e:
            print(f"[ERROR in spam_loop] {e}", flush=True); time.sleep(1)


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
        :root { --primary-bg: #0a0a0a; --secondary-bg: #1a1a1a; --panel-bg: #111111; --border-color: #333333; --blood-red: #8b0000; --dark-red: #550000; --bone-white: #f8f8ff; --necro-green: #228b22; --text-primary: #f0f0f0; --text-secondary: #cccccc; }
        body { font-family: 'Courier Prime', monospace; background: var(--primary-bg); color: var(--text-primary); margin: 0; padding: 0;}
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { text-align: center; margin-bottom: 30px; padding: 20px; border-bottom: 2px solid var(--blood-red); }
        .title { font-family: 'Nosifer', cursive; font-size: 3rem; color: var(--blood-red); }
        .main-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; }
        .panel { background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 25px; }
        .panel h2 { font-family: 'Orbitron', cursive; font-size: 1.4rem; margin-bottom: 20px; text-transform: uppercase; border-bottom: 2px solid; padding-bottom: 10px; color: var(--bone-white); }
        .panel h2 i { margin-right: 10px; }
        .btn { background: var(--secondary-bg); border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 4px; cursor: pointer; font-family: 'Orbitron', monospace; font-weight: 700; text-transform: uppercase; width: 100%; }
        .input-group { display: flex; align-items: stretch; gap: 10px; margin-bottom: 15px; }
        .input-group input, .input-group textarea { flex-grow: 1; background: #000; border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 4px; font-family: 'Courier Prime', monospace; }
        .grab-section { margin-bottom: 15px; padding: 15px; background: rgba(0,0,0,0.2); border-radius: 8px;}
        .grab-section h3 { margin-top:0; display: flex; justify-content: space-between; align-items: center;}
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
                        <div class="status-row"><span><i class="fas fa-redo"></i> Auto Reboot</span><div><span id="reboot-timer" class="timer-display">--:--:--</span> <span id="reboot-status-badge" class="status-badge inactive">OFF</span></div></div>
                        <div class="status-row"><span><i class="fas fa-broadcast-tower"></i> Auto Spam</span><div><span id="spam-timer" class="timer-display">--:--:--</span><span id="spam-status-badge" class="status-badge inactive">OFF</span></div></div>
                        <div class="status-row"><span><i class="fas fa-server"></i> Uptime</span><div><span id="uptime-timer" class="timer-display">--:--:--</span></div></div> 
                    </div>
                    <div id="bot-status-list" class="bot-status-grid"></div>
                </div>
            </div>
            <div class="panel">
                <h2><i class="fas fa-crosshairs"></i> Soul Harvest</h2>
                <div class="grab-section"><h3>ALPHA NODE <span id="harvest-status-1" class="status-badge">OFF</span></h3><div class="input-group"><input type="number" id="heart-threshold-1" value="50" min="0"><button type="button" id="harvest-toggle-1" class="btn">ENABLE</button></div></div>
                <div class="grab-section"><h3>BETA NODE <span id="harvest-status-2" class="status-badge">OFF</span></h3><div class="input-group"><input type="number" id="heart-threshold-2" value="50" min="0"><button type="button" id="harvest-toggle-2" class="btn">ENABLE</button></div></div>
                <div class="grab-section"><h3>GAMMA NODE <span id="harvest-status-3" class="status-badge">OFF</span></h3><div class="input-group"><input type="number" id="heart-threshold-3" value="50" min="0"><button type="button" id="harvest-toggle-3" class="btn">ENABLE</button></div></div>
            </div>
            <div class="panel">
                 <h2><i class="fas fa-skull"></i> Auto Resurrection</h2>
                <div class="input-group"><label>Interval (s)</label><input type="number" id="auto-reboot-delay" value="3600"></div>
                <button type="button" id="auto-reboot-toggle-btn" class="btn">ENABLE AUTO REBOOT</button>
            </div>
            <div class="panel">
                <h2><i class="fas fa-paper-plane"></i> Auto Broadcast</h2>
                <div class="input-group"><label>Message</label><textarea id="spam-message" rows="2"></textarea></div>
                <div class="input-group"><label>Delay (s)</label><input type="number" id="spam-delay" value="10"></div>
                <button type="button" id="spam-toggle-btn" class="btn">ENABLE SPAM</button>
            </div>
        </div>
    </div>
<script>
    document.addEventListener('DOMContentLoaded', function () {
        const msgStatusContainer = document.getElementById('msg-status-container');
        const msgStatusText = document.getElementById('msg-status-text');
        function showStatusMessage(message) {
            if (!message) return;
            msgStatusText.textContent = message;
            msgStatusContainer.style.display = 'block';
            setTimeout(() => { msgStatusContainer.style.display = 'none'; }, 3000);
        }
        async function postData(url = '', data = {}) {
            try {
                const response = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await response.json();
                showStatusMessage(result.message);
                setTimeout(fetchStatus, 500);
                return result;
            } catch (error) {
                console.error('Error:', error);
                showStatusMessage('Server communication error.');
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
        function updateElement(id, { textContent, className, value }) {
            const el = document.getElementById(id);
            if (!el) return;
            if (textContent !== undefined) el.textContent = textContent;
            if (className !== undefined) el.className = className;
            if (value !== undefined) el.value = value;
        }
        async function fetchStatus() {
            try {
                const response = await fetch('/status');
                const data = await response.json();
                
                updateElement('reboot-timer', { textContent: formatTime(data.reboot_countdown) });
                updateElement('reboot-status-badge', { textContent: data.reboot_enabled ? 'ON' : 'OFF', className: `status-badge ${data.reboot_enabled ? 'active' : 'inactive'}` });
                updateElement('auto-reboot-toggle-btn', { textContent: `${data.reboot_enabled ? 'DISABLE' : 'ENABLE'} AUTO REBOOT`});

                updateElement('spam-timer', { textContent: formatTime(data.spam_countdown) });
                updateElement('spam-status-badge', { textContent: data.spam_enabled ? 'ON' : 'OFF', className: `status-badge ${data.spam_enabled ? 'active' : 'inactive'}` });
                updateElement('spam-toggle-btn', { textContent: `${data.spam_enabled ? 'DISABLE' : 'ENABLE'} SPAM`});

                const serverUptimeSeconds = (Date.now() / 1000) - data.server_start_time;
                updateElement('uptime-timer', { textContent: formatTime(serverUptimeSeconds) });
                
                updateElement('harvest-status-1', { textContent: data.grab_text, className: `status-badge ${data.grab_status}` });
                updateElement('harvest-toggle-1', { textContent: data.grab_action });
                updateElement('harvest-status-2', { textContent: data.grab_text_2, className: `status-badge ${data.grab_status_2}` });
                updateElement('harvest-toggle-2', { textContent: data.grab_action_2 });
                updateElement('harvest-status-3', { textContent: data.grab_text_3, className: `status-badge ${data.grab_status_3}` });
                updateElement('harvest-toggle-3', { textContent: data.grab_action_3 });
                
                const listContainer = document.getElementById('bot-status-list');
                listContainer.innerHTML = ''; 
                const allBots = [...data.bot_statuses.main_bots, ...data.bot_statuses.sub_accounts];
                allBots.forEach(bot => {
                    const item = document.createElement('div');
                    item.className = 'bot-status-item';
                    if (bot.type === 'main') item.classList.add('bot-main');
                    const buttonText = bot.is_active ? 'ONLINE' : 'OFFLINE';
                    const buttonClass = bot.is_active ? 'btn-rise' : 'btn-rest';
                    item.innerHTML = `<span>${bot.name}</span><button type="button" data-target="${bot.reboot_id}" class="btn-toggle-state ${buttonClass}">${buttonText}</button>`;
                    listContainer.appendChild(item);
                });

            } catch (error) { console.error('Error fetching status:', error); }
        }
        setInterval(fetchStatus, 1000);

        // Event Listeners
        document.getElementById('harvest-toggle-1').addEventListener('click', () => postData('/api/harvest_toggle', { node: 1, threshold: document.getElementById('heart-threshold-1').value }));
        document.getElementById('harvest-toggle-2').addEventListener('click', () => postData('/api/harvest_toggle', { node: 2, threshold: document.getElementById('heart-threshold-2').value }));
        document.getElementById('harvest-toggle-3').addEventListener('click', () => postData('/api/harvest_toggle', { node: 3, threshold: document.getElementById('heart-threshold-3').value }));
        
        document.getElementById('auto-reboot-toggle-btn').addEventListener('click', () => postData('/api/reboot_toggle_auto', { delay: document.getElementById('auto-reboot-delay').value }));
        
        document.getElementById('spam-toggle-btn').addEventListener('click', () => postData('/api/broadcast_toggle', {
            type: 'spam',
            message: document.getElementById('spam-message').value,
            delay: document.getElementById('spam-delay').value
        }));
        
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
    grab_status, grab_text, grab_action = ("active", "ON", "DISABLE") if auto_grab_enabled else ("inactive", "OFF", "ENABLE")
    grab_status_2, grab_text_2, grab_action_2 = ("active", "ON", "DISABLE") if auto_grab_enabled_2 else ("inactive", "OFF", "ENABLE")
    grab_status_3, grab_text_3, grab_action_3 = ("active", "ON", "DISABLE") if auto_grab_enabled_3 else ("inactive", "OFF", "ENABLE")
    spam_action = "DISABLE" if spam_enabled else "ENABLE"
    reboot_action = "DISABLE" if auto_reboot_enabled else "ENABLE"

    return render_template_string(HTML_TEMPLATE, 
        grab_status=grab_status, grab_text=grab_text, grab_action=grab_action, heart_threshold=heart_threshold,
        grab_status_2=grab_status_2, grab_text_2=grab_text_2, grab_action_2=grab_action_2, heart_threshold_2=heart_threshold_2,
        grab_status_3=grab_status_3, grab_text_3=grab_text_3, grab_action_3=grab_action_3, heart_threshold_3=heart_threshold_3,
        spam_message=spam_message, spam_delay=spam_delay, spam_action=spam_action,
        auto_reboot_delay=auto_reboot_delay, reboot_action=reboot_action
    )

@app.route("/api/harvest_toggle", methods=['POST'])
def api_harvest_toggle():
    global auto_grab_enabled, heart_threshold, auto_grab_enabled_2, heart_threshold_2, auto_grab_enabled_3, heart_threshold_3
    data = request.get_json()
    node = data.get('node')
    threshold = int(data.get('threshold', 50))
    msg = ""
    if node == 1: auto_grab_enabled = not auto_grab_enabled; heart_threshold = threshold; msg = f"Auto Grab 1 was {'ENABLED' if auto_grab_enabled else 'DISABLED'}"
    elif node == 2: auto_grab_enabled_2 = not auto_grab_enabled_2; heart_threshold_2 = threshold; msg = f"Auto Grab 2 was {'ENABLED' if auto_grab_enabled_2 else 'DISABLED'}"
    elif node == 3: auto_grab_enabled_3 = not auto_grab_enabled_3; heart_threshold_3 = threshold; msg = f"Auto Grab 3 was {'ENABLED' if auto_grab_enabled_3 else 'DISABLED'}"
    return jsonify({'status': 'success', 'message': msg})

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
        msg = "Auto Reboot ENABLED."
    else:
        if auto_reboot_stop_event: auto_reboot_stop_event.set()
        auto_reboot_thread = None
        msg = "Auto Reboot DISABLED."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/broadcast_toggle", methods=['POST'])
def api_broadcast_toggle():
    global spam_enabled, spam_message, spam_delay, spam_thread, last_spam_time
    data = request.get_json()
    msg = ""
    if data.get('type') == 'spam':
        spam_message, spam_delay = data.get("message", "").strip(), int(data.get("delay", 10))
        if not spam_enabled and spam_message:
            spam_enabled = True
            last_spam_time = time.time()
            msg = "Spam ENABLED."
            if spam_thread is None or not spam_thread.is_alive():
                spam_thread = threading.Thread(target=spam_loop, daemon=True)
                spam_thread.start()
        else: 
            spam_enabled = False
            msg = "Spam DISABLED."
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

@app.route("/status")
def status():
    now = time.time()
    reboot_countdown = (last_reboot_cycle_time + auto_reboot_delay - now) if auto_reboot_enabled else 0
    spam_countdown = (last_spam_time + spam_delay - now) if spam_enabled else 0

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
        'reboot_enabled': auto_reboot_enabled, 'reboot_countdown': reboot_countdown,
        'spam_enabled': spam_enabled, 'spam_countdown': spam_countdown,
        'bot_statuses': bot_statuses,
        'server_start_time': server_start_time,
        'grab_status': "active" if auto_grab_enabled else "inactive", 'grab_text': "ON" if auto_grab_enabled else "OFF", 'grab_action': "DISABLE" if auto_grab_enabled else "ENABLE",
        'grab_status_2': "active" if auto_grab_enabled_2 else "inactive", 'grab_text_2': "ON" if auto_grab_enabled_2 else "OFF", 'grab_action_2': "DISABLE" if auto_grab_enabled_2 else "ENABLE",
        'grab_status_3': "active" if auto_grab_enabled_3 else "inactive", 'grab_text_3': "ON" if auto_grab_enabled_3 else "OFF", 'grab_action_3': "DISABLE" if auto_grab_enabled_3 else "ENABLE",
    })

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print("Đang khởi tạo các bot...", flush=True)
    with bots_lock:
        if main_token: 
            main_bot = create_bot(main_token, is_main=True)
            if 'main_1' not in bot_active_states:
                bot_active_states['main_1'] = True
                
        if main_token_2: 
            main_bot_2 = create_bot(main_token_2, is_main_2=True)
            if 'main_2' not in bot_active_states:
                bot_active_states['main_2'] = True
                
        if main_token_3: 
            main_bot_3 = create_bot(main_token_3, is_main_3=True)
            if 'main_3' not in bot_active_states:
                bot_active_states['main_3'] = True
                
        for i, token in enumerate(tokens):
            if token.strip():
                bots.append(create_bot(token.strip()))
                if f'sub_{i}' not in bot_active_states:
                    bot_active_states[f'sub_{i}'] = True

    print("Đang khởi tạo các luồng nền...", flush=True)
    if spam_thread is None or not spam_thread.is_alive():
        spam_thread = threading.Thread(target=spam_loop, daemon=True)
        spam_thread.start()
    
    if auto_reboot_enabled:
        if auto_reboot_thread is None or not auto_reboot_thread.is_alive():
            auto_reboot_stop_event = threading.Event()
            auto_reboot_thread = threading.Thread(target=auto_reboot_loop, daemon=True)
            auto_reboot_thread.start()
    
    port = int(os.environ.get("PORT", 10000))
    print(f"Khởi động Web Server tại http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

}
