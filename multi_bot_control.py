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

# Không còn sử dụng các biến cố định này nữa, chúng sẽ nằm trong server_configs
# main_channel_id = os.getenv("MAIN_CHANNEL_ID")
# ktb_channel_id = os.getenv("KTB_CHANNEL_ID")
# spam_channel_id = os.getenv("SPAM_CHANNEL_ID")

karuta_id = "646937666251915264"
karibbit_id = "1311684840462225440"

# Đường dẫn file cấu hình động
CONFIG_FILE = "dynamic_configs.json"

# --- BIẾN TRẠNG THÁI (đây là các giá trị mặc định nếu không có file settings.json) ---
bots, acc_names = [], [
    "Blacklist", "Khanh bang", "Dersale", "Venus", "WhyK", "Tan",
    "Ylang", "Nina", "Nathan", "Ofer", "White", "the Wicker", "Leader", "Tess", "Wyatt", "Daisy", "CantStop", "Token",
]
main_bot, main_bot_2, main_bot_3 = None, None, None

# auto_grab_enabled, heart_threshold sẽ được quản lý trong auto_grab_configs
# Loại bỏ các biến toàn cục cũ
# auto_grab_enabled, auto_grab_enabled_2, auto_grab_enabled_3 = False, False, False
# heart_threshold, heart_threshold_2, heart_threshold_3 = 50, 50, 50

spam_enabled, auto_reboot_enabled = False, False
spam_message, spam_delay, auto_reboot_delay = "", 10, 3600

# Timestamps - sẽ được load từ file
last_reboot_cycle_time, last_spam_time = 0, 0

# Các biến điều khiển luồng
auto_reboot_stop_event = threading.Event()
spam_thread, auto_reboot_thread = None, None
bots_lock = threading.Lock()
server_start_time = time.time()
bot_active_states = {} # active/inactive states of individual bots

# Cấu trúc mới để lưu trữ cấu hình cho từng bot chính và kênh spam toàn cục
auto_grab_configs = {
    "main_1": {"enabled": False, "threshold": 50, "grab_channels": [], "ktb_channel": ""},
    "main_2": {"enabled": False, "threshold": 50, "grab_channels": [], "ktb_channel": ""},
    "main_3": {"enabled": False, "threshold": 50, "grab_channels": [], "ktb_channel": ""},
}
global_spam_channels = [] # Danh sách các channel ID cho spam

# --- HÀM LƯU VÀ TẢI CÀI ĐẶT ---
def save_settings():
    """Lưu cài đặt lên JSONBin.io hoặc vào file local."""
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")

    settings = {
        'auto_grab_configs': auto_grab_configs, # Lưu cấu hình grab mới
        'global_spam_channels': global_spam_channels, # Lưu kênh spam toàn cục
        'spam_enabled': spam_enabled, 'spam_message': spam_message, 'spam_delay': spam_delay,
        'auto_reboot_enabled': auto_reboot_enabled, 'auto_reboot_delay': auto_reboot_delay,
        'bot_active_states': bot_active_states,
        'last_reboot_cycle_time': last_reboot_cycle_time,
        'last_spam_time': last_spam_time,
    }
    
    if api_key and bin_id:
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
    else:
        # Lưu vào file local nếu không có JSONBin.io cấu hình
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(settings, f, indent=4)
            print("[Settings] Đã lưu cài đặt vào file local thành công.", flush=True)
        except Exception as e:
            print(f"[Settings] Lỗi khi lưu cài đặt vào file local: {e}", flush=True)


def load_settings():
    """Tải cài đặt từ JSONBin.io hoặc từ file local."""
    global auto_grab_configs, global_spam_channels, spam_enabled, spam_message, spam_delay, auto_reboot_enabled, auto_reboot_delay, last_reboot_cycle_time, last_spam_time, bot_active_states

    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")

    loaded_settings = {}
    if api_key and bin_id:
        headers = {
            'X-Master-Key': api_key
        }
        url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"

        try:
            req = requests.get(url, headers=headers, timeout=10)
            if req.status_code == 200:
                loaded_settings = req.json().get("record", {})
                if loaded_settings:
                    print("[Settings] Đã tải cài đặt từ JSONBin.io.", flush=True)
                else:
                    print("[Settings] JSONBin rỗng, sẽ lưu cài đặt mặc định sau khi khởi tạo.", flush=True)
            else:
                print(f"[Settings] Lỗi khi tải cài đặt từ JSONBin.io: {req.status_code} - {req.text}", flush=True)
        except Exception as e:
            print(f"[Settings] Exception khi tải cài đặt từ JSONBin.io: {e}", flush=True)
    else:
        # Tải từ file local nếu không có JSONBin.io cấu hình
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    loaded_settings = json.load(f)
                print("[Settings] Đã tải cài đặt từ file local.", flush=True)
            except json.JSONDecodeError:
                print("[Settings] Lỗi đọc file cấu hình động, sẽ tạo mới.", flush=True)
            except Exception as e:
                print(f"[Settings] Lỗi khi tải cài đặt từ file local: {e}", flush=True)
        else:
            print("[Settings] Không tìm thấy file cấu hình local, sẽ bắt đầu với cài đặt mặc định.", flush=True)

    # Áp dụng các cài đặt đã tải
    auto_grab_configs.update(loaded_settings.get("auto_grab_configs", {
        "main_1": {"enabled": False, "threshold": 50, "grab_channels": [], "ktb_channel": ""},
        "main_2": {"enabled": False, "threshold": 50, "grab_channels": [], "ktb_channel": ""},
        "main_3": {"enabled": False, "threshold": 50, "grab_channels": [], "ktb_channel": ""},
    }))
    global_spam_channels = loaded_settings.get("global_spam_channels", [])
    
    spam_enabled = loaded_settings.get("spam_enabled", False)
    spam_message = loaded_settings.get("spam_message", "")
    spam_delay = loaded_settings.get("spam_delay", 10)
    auto_reboot_enabled = loaded_settings.get("auto_reboot_enabled", False)
    auto_reboot_delay = loaded_settings.get("auto_reboot_delay", 3600)
    bot_active_states.update(loaded_settings.get("bot_active_states", {}))
    last_reboot_cycle_time = loaded_settings.get("last_reboot_cycle_time", time.time())
    last_spam_time = loaded_settings.get("last_spam_time", time.time())

    # Đảm bảo các cấu hình mặc định tồn tại nếu chưa có
    for bot_key in ["main_1", "main_2", "main_3"]:
        if bot_key not in auto_grab_configs:
            auto_grab_configs[bot_key] = {'enabled': False, 'threshold': 50, 'grab_channels': [], 'ktb_channel': ''}


# --- CÁC HÀM LOGIC BOT ---
def reboot_bot(target_id):
    global main_bot, main_bot_2, main_bot_3, bots
    with bots_lock:
        print(f"[Reboot] Nhận được yêu cầu reboot cho target: {target_id}", flush=True)
        if target_id == 'main_1' and main_token:
            try: 
                if main_bot: main_bot.gateway.close()
            except Exception as e: print(f"[Reboot] Lỗi khi đóng Acc Chính 1: {e}", flush=True)
            main_bot = create_bot(main_token, "main_1")
            print("[Reboot] Acc Chính 1 đã được khởi động lại.", flush=True)
        elif target_id == 'main_2' and main_token_2:
            try: 
                if main_bot_2: main_bot_2.gateway.close()
            except Exception as e: print(f"[Reboot] Lỗi khi đóng Acc Chính 2: {e}", flush=True)
            main_bot_2 = create_bot(main_token_2, "main_2")
            print("[Reboot] Acc Chính 2 đã được khởi động lại.", flush=True)
        elif target_id == 'main_3' and main_token_3:
            try: 
                if main_bot_3: main_bot_3.gateway.close()
            except Exception as e: print(f"[Reboot] Lỗi khi đóng Acc Chính 3: {e}", flush=True)
            main_bot_3 = create_bot(main_token_3, "main_3")
            print("[Reboot] Acc Chính 3 đã được khởi động lại.", flush=True)
        elif target_id.startswith('sub_'):
            idx = int(target_id.split('_')[1])
            if idx < len(bots) and tokens[idx]:
                try:
                    if bots[idx]: bots[idx].gateway.close()
                except Exception as e: print(f"[Reboot] Lỗi khi đóng Acc Phụ {idx+1}: {e}", flush=True)
                bots[idx] = create_bot(tokens[idx], f"sub_{idx}")
                print(f"[Reboot] Acc Phụ {idx+1} đã được khởi động lại.", flush=True)


def create_bot(token, bot_id):
    bot = discum.Client(token=token, log=False)
    bot.bot_id = bot_id # Store bot_id for easy access
    
    # Gán các thông tin kênh từ cấu hình động
    if bot_id.startswith("main_") and bot_id in auto_grab_configs:
        bot.grab_channels = auto_grab_configs[bot_id]["grab_channels"]
        bot.ktb_channel = auto_grab_configs[bot_id]["ktb_channel"]
    else: # Đối với các sub bot, grab_channels và ktb_channel không áp dụng
        bot.grab_channels = []
        bot.ktb_channel = None
    
    # Tất cả các bot đều sẽ sử dụng danh sách kênh spam toàn cục
    bot.spam_channels_list = global_spam_channels 

    @bot.gateway.command
    def on_ready(resp):
        if resp.event.ready:
            user_data = resp.raw.get("user")
            if isinstance(user_data, dict):
                user_id = user_data.get("id")
                if user_id:
                    bot_type = ""
                    if bot_id == "main_1": bot_type = "(ALPHA)"
                    elif bot_id == "main_2": bot_type = "(BETA)"
                    elif bot_id == "main_3": bot_type = "(GAMMA)"
                    print(f"Đã đăng nhập: {user_id} {bot_type} (Bot ID: {bot_id})", flush=True)

    @bot.gateway.command
    def on_message(resp):
        global auto_grab_configs
        if resp.event.message:
            msg = resp.parsed.auto()
            author_id = msg.get("author", {}).get("id")
            channel_id = msg.get("channel_id")
            content = msg.get("content", "")
            mentions = msg.get("mentions", [])
            
            # Logic cho Auto Grab (chỉ áp dụng cho các bot chính và nếu tính năng bật)
            if bot.bot_id.startswith("main_") and bot.bot_id in auto_grab_configs and auto_grab_configs[bot.bot_id]["enabled"] and bot_active_states.get(bot.bot_id, False):
                # Kiểm tra xem tin nhắn có ở TRONG DANH SÁCH KÊNH GRAB của bot hay không
                if author_id == karuta_id and channel_id in bot.grab_channels and "is dropping" not in content and not mentions:
                    last_drop_msg_id = msg["id"]
                    current_channel_id_for_grab = channel_id # Capture channel ID for this specific drop
                    
                    def read_karibbit():
                        time.sleep(0.5)
                        try:
                            # Lấy tin nhắn từ kênh hiện tại của drop
                            messages = bot.getMessages(current_channel_id_for_grab, num=5).json()
                            for msg_item in messages:
                                if msg_item.get("author", {}).get("id") == karibbit_id and "embeds" in msg_item and len(msg_item["embeds"]) > 0:
                                    desc = msg_item["embeds"][0].get("description", "")
                                    lines = desc.split('\n')
                                    heart_numbers = []
                                    for line in lines[:3]:
                                        match = re.search(r'♡(\d+)', line)
                                        if match:
                                            heart_numbers.append(int(match.group(1)))
                                        else:
                                            heart_numbers.append(0)
                                    max_num = max(heart_numbers)
                                    current_threshold = auto_grab_configs[bot.bot_id]["threshold"]

                                    if sum(heart_numbers) > 0 and max_num >= current_threshold:
                                        max_index = heart_numbers.index(max_num)
                                        # Có thể điều chỉnh delay cho từng bot/kênh nếu muốn, ví dụ:
                                        # delays = {"main_1": [0.4, 1.4, 2.1], "main_2": [0.7, 1.8, 2.4], "main_3": [0.7, 1.8, 2.4]}
                                        # emoji, delay = [("1️⃣", delays[bot.bot_id][0]), ("2️⃣", delays[bot.bot_id][1]), ("3️⃣", delays[bot.bot_id][2])][max_index]
                                        # Sử dụng delay cố định như cũ để không thay đổi logic core
                                        emoji, delay = [("1️⃣", 0.4), ("2️⃣", 1.4), ("3️⃣", 2.1)][max_index] 
                                        
                                        print(f"[{bot.bot_id}] Chọn dòng {max_index+1} với {max_num} tim (>= {current_threshold}) tại kênh {current_channel_id_for_grab} -> Emoji {emoji} sau {delay}s", flush=True)
                                        def grab():
                                            bot.addReaction(current_channel_id_for_grab, last_drop_msg_id, emoji)
                                            time.sleep(1)
                                            if bot.ktb_channel: # Chỉ gửi kt b nếu kênh KTB được cấu hình
                                                bot.sendMessage(bot.ktb_channel, "kt b")
                                        threading.Timer(delay, grab).start()
                                    break
                        except Exception as e: print(f"Lỗi khi đọc tin nhắn Karibbit ({bot.bot_id}) tại kênh {current_channel_id_for_grab}: {e}", flush=True)
                    threading.Thread(target=read_karibbit).start()

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
                print("[Reboot] Hết thời gian chờ, tiến hành reboot các tài khoản chính và phụ đang hoạt động.", flush=True)
                with bots_lock:
                    if main_bot and bot_active_states.get('main_1', False): reboot_bot('main_1'); time.sleep(5)
                    if main_bot_2 and bot_active_states.get('main_2', False): reboot_bot('main_2'); time.sleep(5)
                    if main_bot_3 and bot_active_states.get('main_3', False): reboot_bot('main_3'); time.sleep(5)
                    
                    # Reboot các sub bot đang active
                    for i, bot_instance in enumerate(bots):
                        # Cần kiểm tra bot_instance có tồn tại và bot_active_states có lưu trạng thái không
                        if bot_instance and bot_active_states.get(f'sub_{i}', False):
                            reboot_bot(f'sub_{i}')
                            time.sleep(5) # Giãn cách giữa các lần reboot

                last_reboot_cycle_time = time.time()
                save_settings() # Lưu trạng thái sau khi reboot
        except Exception as e:
            print(f"[ERROR in auto_reboot_loop] {e}", flush=True)
            time.sleep(60)
    print("[Reboot] Luồng tự động reboot đã dừng.", flush=True)

def spam_loop():
    global last_spam_time, spam_message, spam_delay, spam_enabled, global_spam_channels
    while True:
        try:
            if spam_enabled and spam_message and global_spam_channels: # Chỉ spam nếu có kênh được cấu hình
                if (time.time() - last_spam_time) >= spam_delay:
                    with bots_lock:
                        # Lấy tất cả các bot đang hoạt động (main và sub)
                        all_active_bots = []
                        if main_bot and bot_active_states.get('main_1', False): all_active_bots.append(main_bot)
                        if main_bot_2 and bot_active_states.get('main_2', False): all_active_bots.append(main_bot_2)
                        if main_bot_3 and bot_active_states.get('main_3', False): all_active_bots.append(main_bot_3)
                        all_active_bots.extend([bot for i, bot in enumerate(bots) if bot and bot_active_states.get(f'sub_{i}', False)])

                    for bot_instance in all_active_bots:
                        if not spam_enabled: break # Dừng nếu spam bị tắt giữa chừng
                        # Mỗi bot sẽ spam vào DANH SÁCH KÊNH SPAM TOÀN CỤC được gán cho nó
                        for channel_id in bot_instance.spam_channels_list: 
                            if not spam_enabled: break # Kiểm tra lại trạng thái
                            try:
                                print(f"[{bot_instance.bot_id}] Gửi spam '{spam_message}' đến kênh {channel_id}", flush=True)
                                bot_instance.sendMessage(channel_id, spam_message)
                                time.sleep(2) # Giãn cách giữa các tin nhắn spam để tránh rate limit
                            except Exception as e:
                                print(f"Lỗi gửi spam từ bot {bot_instance.bot_id} đến kênh {channel_id}: {e}", flush=True)
                        time.sleep(5) # Giãn cách giữa các bot để tránh rate limit

                    if spam_enabled:
                        last_spam_time = time.time()
            time.sleep(1)
        except Exception as e:
            print(f"[ERROR in spam_loop] {e}", flush=True)
            time.sleep(1)

def periodic_save_loop():
    """Vòng lặp nền để tự động lưu cài đặt 10 tiếng một lần."""
    while True:
        time.sleep(36000) # Chờ 36000 giây (10 tiếng)
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
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { text-align: center; margin-bottom: 30px; padding: 20px; border-bottom: 2px solid var(--blood-red); }
        .title { font-family: 'Nosifer', cursive; font-size: 3rem; color: var(--blood-red); }
        .main-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; }
        .panel { background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 25px; }
        .panel h2 { font-family: 'Orbitron', cursive; font-size: 1.4rem; margin-bottom: 20px; text-transform: uppercase; border-bottom: 2px solid; padding-bottom: 10px; color: var(--bone-white); }
        .panel h2 i { margin-right: 10px; }
        .btn { background: var(--secondary-bg); border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 4px; cursor: pointer; font-family: 'Orbitron', monospace; font-weight: 700; text-transform: uppercase; width: 100%; transition: background-color 0.3s ease; }
        .btn:hover { background-color: #333; }
        .input-group { display: flex; align-items: stretch; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; }
        .input-group label { flex: 0 0 100px; line-height: 2.2; color: var(--text-secondary); }
        .input-group input, .input-group textarea { flex-grow: 1; background: #000; border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 4px; font-family: 'Courier Prime', monospace; }
        .grab-section { margin-bottom: 15px; padding: 15px; background: rgba(0,0,0,0.2); border-radius: 8px;}
        .grab-section h3 { margin-top:0; display: flex; justify-content: space-between; align-items: center; color: var(--bone-white);}
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

        /* New Server Panel Styles */
        .modal { display: none; position: fixed; z-index: 1; left: 0; top: 0; width: 100%; height: 100%; overflow: auto; background-color: rgba(0,0,0,0.7); align-items: center; justify-content: center; }
        .modal-content { background-color: var(--panel-bg); margin: auto; padding: 30px; border: 1px solid var(--border-color); width: 80%; max-width: 600px; border-radius: 10px; position: relative;}
        .close-button { color: var(--text-secondary); float: right; font-size: 28px; font-weight: bold; position: absolute; top: 10px; right: 15px; cursor: pointer;}
        .close-button:hover, .close-button:focus { color: var(--bone-white); text-decoration: none; cursor: pointer; }
        .modal-content h2 { color: var(--bone-white); margin-bottom: 20px; }
        .form-row { margin-bottom: 15px; }
        .form-row label { display: block; margin-bottom: 5px; color: var(--text-secondary); }
        .form-row input, .form-row textarea { width: calc(100% - 22px); } /* Account for padding */
        .form-row input[type="text"] { width: 100%; } /* full width */
        .form-row input[type="number"] { width: 80px; }
        .btn-add-server { background-color: var(--necro-green); color: #000; border: none; }
        .btn-add-server:hover { background-color: #3cb371; }
        .info-text { font-size: 0.8em; color: var(--text-secondary); margin-top: -10px; margin-bottom: 10px; }
        select {
            width: 100%; padding: 10px; background: #000; border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 4px;
        }
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
                <h2><i class="fas fa-crosshairs"></i> Soul Harvest (Main Bots)</h2>
                {% for bot_key in main_bot_keys %}
                {% set config = auto_grab_configs[bot_key] %}
                <div class="grab-section">
                    <h3>
                        {{ bot_names_map[bot_key] }} NODE 
                        <span id="harvest-status-{{ loop.index }}" class="status-badge {{ 'active' if config.enabled else 'inactive' }}">
                            {{ 'ON' if config.enabled else 'OFF' }}
                        </span>
                    </h3>
                    <div class="input-group">
                        <label>Threshold:</label><input type="number" id="heart-threshold-{{ loop.index }}" value="{{ config.threshold }}" min="0">
                    </div>
                    <div class="input-group">
                        <label>Grab Channels (ID, ID):</label><input type="text" id="grab-channels-{{ loop.index }}" value="{{ ','.join(config.grab_channels) }}">
                    </div>
                    <div class="input-group">
                        <label>KTB Channel (ID):</label><input type="text" id="ktb-channel-{{ loop.index }}" value="{{ config.ktb_channel }}">
                    </div>
                    <button type="button" data-node="{{ loop.index }}" class="btn harvest-toggle-btn">{{ 'DISABLE' if config.enabled else 'ENABLE' }} GRAB</button>
                </div>
                {% endfor %}
            </div>
            
            <div class="panel">
                 <h2><i class="fas fa-skull"></i> Auto Resurrection</h2>
                <div class="input-group"><label>Interval (s)</label><input type="number" id="auto-reboot-delay" value="{{ auto_reboot_delay }}"></div>
                <button type="button" id="auto-reboot-toggle-btn" class="btn">{{ 'DISABLE' if auto_reboot_enabled else 'ENABLE' }} AUTO REBOOT</button>
            </div>
            <div class="panel">
                <h2><i class="fas fa-paper-plane"></i> Auto Broadcast (All Bots)</h2>
                <div class="input-group"><label>Message</label><textarea id="spam-message" rows="2">{{ spam_message }}</textarea></div>
                <div class="input-group"><label>Delay (s)</label><input type="number" id="spam-delay" value="{{ spam_delay }}"></div>
                <div class="input-group">
                    <label>Spam Channels (ID, ID):</label><input type="text" id="global-spam-channels" value="{{ ','.join(global_spam_channels) }}">
                </div>
                <button type="button" id="spam-toggle-btn" class="btn">{{ 'DISABLE' if spam_enabled else 'ENABLE' }} SPAM</button>
            </div>
            
            <div class="panel">
                <h2><i class="fas fa-plus-circle"></i> Add New Server Config</h2>
                <p class="info-text">Use this to add new grab channels for existing main bots or new global spam channels without restarting the app. Changes require bot reboot.</p>
                <button type="button" id="open-add-server-modal" class="btn">Add/Update Server Config</button>
            </div>
        </div>
    </div>

    <div id="addServerModal" class="modal">
        <div class="modal-content">
            <span class="close-button">&times;</span>
            <h2><i class="fas fa-server"></i> Configure Server Channels</h2>
            <p class="info-text">Leave fields blank if you don't want to change them. Entering new values will update existing settings. Bots will be rebooted.</p>
            <div class="form-row">
                <label for="mainBotSelect">Select Main Bot for Grab Config:</label>
                <select id="mainBotSelect">
                    <option value="">-- Select Bot --</option>
                    <option value="main_1">ALPHA Node</option>
                    <option value="main_2">BETA Node</option>
                    <option value="main_3">GAMMA Node</option>
                </select>
            </div>
            <div class="form-row">
                <label for="modalGrabChannels">New Grab Channels (comma-separated IDs):</label>
                <input type="text" id="modalGrabChannels" placeholder="e.g., 12345,67890">
            </div>
            <div class="form-row">
                <label for="modalKtbChannel">New KTB Channel (single ID):</label>
                <input type="text" id="modalKtbChannel" placeholder="e.g., 98765">
            </div>
            <hr style="border-color: var(--border-color); margin: 20px 0;">
            <div class="form-row">
                <label for="modalGlobalSpamChannels">Update Global Spam Channels (comma-separated IDs):</label>
                <input type="text" id="modalGlobalSpamChannels" placeholder="e.g., 111222,333444">
            </div>
            <button type="button" id="submitAddServerConfig" class="btn btn-add-server">Save Configuration & Reboot Bots</button>
        </div>
    </div>


<script>
    document.addEventListener('DOMContentLoaded', function () {
        const msgStatusContainer = document.getElementById('msg-status-container');
        const msgStatusText = document.getElementById('msg-status-text');
        
        // Modal elements
        const addServerModal = document.getElementById('addServerModal');
        const openAddServerModalBtn = document.getElementById('open-add-server-modal');
        const closeButton = addServerModal.querySelector('.close-button');
        const mainBotSelect = document.getElementById('mainBotSelect');
        const modalGrabChannels = document.getElementById('modalGrabChannels');
        const modalKtbChannel = document.getElementById('modalKtbChannel');
        const modalGlobalSpamChannels = document.getElementById('modalGlobalSpamChannels');
        const submitAddServerConfigBtn = document.getElementById('submitAddServerConfig');

        function showStatusMessage(message, isError = false) {
            if (!message) return;
            msgStatusText.textContent = message;
            msgStatusContainer.style.display = 'block';
            msgStatusContainer.style.color = isError ? 'red' : 'var(--necro-green)';
            setTimeout(() => { msgStatusContainer.style.display = 'none'; }, 3000);
        }
        
        async function postData(url = '', data = {}, showMsg = true) {
            try {
                const response = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await response.json();
                if (showMsg) showStatusMessage(result.message, result.status === 'error');
                setTimeout(fetchStatus, 500); // Fetch status after any action
                return result;
            } catch (error) {
                console.error('Error:', error);
                if (showMsg) showStatusMessage('Server communication error.', true);
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

                // Update spam message and delay from current status
                updateElement('spam-message', { value: data.spam_message });
                updateElement('spam-delay', { value: data.spam_delay });
                updateElement('global-spam-channels', { value: data.global_spam_channels.join(',') });
                updateElement('auto-reboot-delay', { value: data.auto_reboot_delay });


                const serverUptimeSeconds = (Date.now() / 1000) - data.server_start_time;
                updateElement('uptime-timer', { textContent: formatTime(serverUptimeSeconds) });
                
                // Update Harvest status for main bots dynamically
                for (let i = 0; i < data.main_bot_keys.length; i++) {
                    const key = data.main_bot_keys[i];
                    const config = data.auto_grab_configs[key];
                    if (config) {
                        updateElement(`harvest-status-${i+1}`, { textContent: config.enabled ? 'ON' : 'OFF', className: `status-badge ${config.enabled ? 'active' : 'inactive'}` });
                        document.querySelector(`.harvest-toggle-btn[data-node="${i+1}"]`).textContent = `${config.enabled ? 'DISABLE' : 'ENABLE'} GRAB`;
                        updateElement(`heart-threshold-${i+1}`, { value: config.threshold });
                        updateElement(`grab-channels-${i+1}`, { value: config.grab_channels.join(',') });
                        updateElement(`ktb-channel-${i+1}`, { value: config.ktb_channel });
                    }
                }

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
        setInterval(fetchStatus, 1000); // Fetch status every second

        // --- Event Listeners ---
        // Harvest Toggle for Main Bots
        document.querySelectorAll('.harvest-toggle-btn').forEach(button => {
            button.addEventListener('click', () => {
                const node = button.dataset.node; // 1, 2, or 3
                const threshold = document.getElementById(`heart-threshold-${node}`).value;
                const grabChannels = document.getElementById(`grab-channels-${node}`).value;
                const ktbChannel = document.getElementById(`ktb-channel-${node}`).value;
                
                postData('/api/harvest_toggle', { 
                    node: parseInt(node), 
                    threshold: threshold,
                    grab_channels: grabChannels,
                    ktb_channel: ktbChannel
                });
            });
        });
        
        document.getElementById('auto-reboot-toggle-btn').addEventListener('click', () => postData('/api/reboot_toggle_auto', { delay: document.getElementById('auto-reboot-delay').value }));
        
        document.getElementById('spam-toggle-btn').addEventListener('click', () => postData('/api/broadcast_toggle', {
            type: 'spam',
            message: document.getElementById('spam-message').value,
            delay: document.getElementById('spam-delay').value,
            global_spam_channels: document.getElementById('global-spam-channels').value
        }));
        
        document.getElementById('bot-status-list').addEventListener('click', e => {
            if(e.target.matches('button[data-target]')) {
                postData('/api/toggle_bot_state', { target: e.target.dataset.target });
            }
        });

        // --- Modal Event Listeners ---
        openAddServerModalBtn.addEventListener('click', () => {
            addServerModal.style.display = 'flex';
            // Pre-fill current global spam channels
            modalGlobalSpamChannels.value = document.getElementById('global-spam-channels').value;
            // Clear main bot specific fields initially
            mainBotSelect.value = "";
            modalGrabChannels.value = "";
            modalKtbChannel.value = "";
        });

        closeButton.addEventListener('click', () => {
            addServerModal.style.display = 'none';
        });

        window.addEventListener('click', (event) => {
            if (event.target == addServerModal) {
                addServerModal.style.display = 'none';
            }
        });
        
        // Populate main bot grab channels/ktb when selected in modal
        mainBotSelect.addEventListener('change', async () => {
            const selectedBot = mainBotSelect.value;
            if (selectedBot) {
                const response = await fetch('/status'); // Get current data
                const data = await response.json();
                const config = data.auto_grab_configs[selectedBot];
                if (config) {
                    modalGrabChannels.value = config.grab_channels.join(',');
                    modalKtbChannel.value = config.ktb_channel;
                }
            } else {
                modalGrabChannels.value = "";
                modalKtbChannel.value = "";
            }
        });

        submitAddServerConfigBtn.addEventListener('click', () => {
            const selectedBot = mainBotSelect.value;
            const grabChannels = modalGrabChannels.value;
            const ktbChannel = modalKtbChannel.value;
            const globalSpamChannels = modalGlobalSpamChannels.value;

            postData('/api/add_server_config', {
                main_bot_id: selectedBot,
                grab_channels: grabChannels,
                ktb_channel: ktbChannel,
                global_spam_channels: globalSpamChannels
            }).then(() => {
                addServerModal.style.display = 'none'; // Close modal after submission
            });
        });
    });
</script>
</body>
</html>
"""

# --- FLASK ROUTES ---
@app.route("/")
def index():
    # bot_names_map for display in template
    bot_names_map = {
        "main_1": "ALPHA",
        "main_2": "BETA",
        "main_3": "GAMMA"
    }
    # Pass main_bot_keys to loop in JS
    main_bot_keys = ["main_1", "main_2", "main_3"]

    return render_template_string(HTML_TEMPLATE, 
        auto_grab_configs=auto_grab_configs, # Pass the entire dict
        main_bot_keys=main_bot_keys, # To iterate in JS
        bot_names_map=bot_names_map, # For dynamic loop in template
        spam_message=spam_message, 
        spam_delay=spam_delay, 
        global_spam_channels=global_spam_channels,
        auto_reboot_delay=auto_reboot_delay, 
        auto_reboot_enabled=auto_reboot_enabled, # Pass enabled state for initial button text
        spam_enabled=spam_enabled # Pass enabled state for initial button text
    )

@app.route("/api/harvest_toggle", methods=['POST'])
def api_harvest_toggle():
    global auto_grab_configs
    data = request.get_json()
    node_idx = data.get('node') # 1, 2, or 3
    bot_key = f"main_{node_idx}"
    
    if bot_key not in auto_grab_configs:
        return jsonify({'status': 'error', 'message': f"Cấu hình cho {bot_key} không tồn tại."})

    auto_grab_configs[bot_key]["enabled"] = not auto_grab_configs[bot_key]["enabled"]
    auto_grab_configs[bot_key]["threshold"] = int(data.get('threshold', 50))
    
    # Update grab channels and KTB channel from the form
    grab_channels_str = data.get('grab_channels', '').strip()
    auto_grab_configs[bot_key]["grab_channels"] = [cid.strip() for cid in grab_channels_str.split(',') if cid.strip()]
    auto_grab_configs[bot_key]["ktb_channel"] = data.get('ktb_channel', '').strip()

    msg = f"Auto Grab cho {bot_key.upper()} đã được {'BẬT' if auto_grab_configs[bot_key]['enabled'] else 'TẮT'}."
    
    save_settings() # Lưu cấu hình sau khi thay đổi
    # Tái khởi động bot tương ứng để áp dụng thay đổi về kênh
    reboot_bot(bot_key) 
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
        msg = "Auto Reboot đã được BẬT."
    else:
        if auto_reboot_stop_event: auto_reboot_stop_event.set()
        auto_reboot_thread = None
        msg = "Auto Reboot đã được TẮT."
    
    save_settings() # Lưu cấu hình
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/broadcast_toggle", methods=['POST'])
def api_broadcast_toggle():
    global spam_enabled, spam_message, spam_delay, spam_thread, last_spam_time, global_spam_channels
    data = request.get_json()
    msg = ""
    
    spam_message = data.get("message", "").strip()
    spam_delay = int(data.get("delay", 10))
    
    # Update global spam channels from the form
    global_spam_channels_str = data.get("global_spam_channels", "").strip()
    global_spam_channels = [cid.strip() for cid in global_spam_channels_str.split(',') if cid.strip()]

    if not spam_enabled and spam_message and global_spam_channels:
        spam_enabled = True
        last_spam_time = time.time()
        msg = "Spam đã được BẬT."
        if spam_thread is None or not spam_thread.is_alive():
            spam_thread = threading.Thread(target=spam_loop, daemon=True)
            spam_thread.start()
        
        # Reboot all active bots to update their spam_channels_list
        with bots_lock:
            if main_bot and bot_active_states.get('main_1', False): reboot_bot('main_1')
            if main_bot_2 and bot_active_states.get('main_2', False): reboot_bot('main_2')
            if main_bot_3 and bot_active_states.get('main_3', False): reboot_bot('main_3')
            for i, bot_instance in enumerate(bots):
                if bot_instance and bot_active_states.get(f'sub_{i}', False):
                    reboot_bot(f'sub_{i}')
                    
    else: 
        spam_enabled = False
        msg = "Spam đã được TẮT."
    
    save_settings() # Lưu cấu hình
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/toggle_bot_state", methods=['POST'])
def api_toggle_bot_state():
    data = request.get_json()
    target = data.get('target')
    msg = ""
    if target in bot_active_states:
        bot_active_states[target] = not bot_active_states[target]
        state_text = "AWAKENED" if bot_active_states[target] else "DORMANT"
        msg = f"Target {target.upper()} đã được đặt thành {state_text}."
        save_settings() # Lưu trạng thái sau khi thay đổi
        if bot_active_states[target]: # If turning ON, try to reboot it
            reboot_bot(target)
        else: # If turning OFF, try to close its connection
            with bots_lock:
                # Cập nhật để đóng các bot cụ thể
                if target == 'main_1' and main_bot: 
                    main_bot.gateway.close()
                    # main_bot = None # Không set về None để tránh lỗi tham chiếu nếu có request khác đến bot này trước khi nó được khởi tạo lại
                    print(f"Đóng kết nối {target}")
                elif target == 'main_2' and main_bot_2: 
                    main_bot_2.gateway.close()
                    # main_bot_2 = None
                    print(f"Đóng kết nối {target}")
                elif target == 'main_3' and main_bot_3: 
                    main_bot_3.gateway.close()
                    # main_bot_3 = None
                    print(f"Đóng kết nối {target}")
                elif target.startswith('sub_'):
                    idx = int(target.split('_')[1])
                    if idx < len(bots) and bots[idx]: 
                        bots[idx].gateway.close()
                        # bots[idx] = None
                        print(f"Đóng kết nối {target}")
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/add_server_config", methods=['POST'])
def api_add_server_config():
    global auto_grab_configs, global_spam_channels
    data = request.get_json()
    
    main_bot_id = data.get('main_bot_id')
    grab_channels_str = data.get('grab_channels', '').strip()
    ktb_channel = data.get('ktb_channel', '').strip()
    global_spam_channels_str = data.get('global_spam_channels', '').strip()

    messages = []

    # Cập nhật cấu hình grab cho bot chính nếu được chọn
    if main_bot_id and main_bot_id in auto_grab_configs:
        # Cập nhật danh sách kênh grab
        if grab_channels_str:
            auto_grab_configs[main_bot_id]["grab_channels"] = [cid.strip() for cid in grab_channels_str.split(',') if cid.strip()]
            messages.append(f"Cập nhật Grab Channels cho {main_bot_id.upper()}.")
        # Cập nhật kênh KTB
        if ktb_channel:
            auto_grab_configs[main_bot_id]["ktb_channel"] = ktb_channel
            messages.append(f"Cập nhật KTB Channel cho {main_bot_id.upper()}.")
        
        # Reboot bot chính liên quan để áp dụng thay đổi
        reboot_bot(main_bot_id)
    elif main_bot_id and main_bot_id not in auto_grab_configs:
        messages.append(f"Cấu hình cho bot chính '{main_bot_id}' không tồn tại. Vui lòng kiểm tra lại ID bot.")


    # Cập nhật danh sách kênh spam toàn cục
    if global_spam_channels_str:
        global_spam_channels = [cid.strip() for cid in global_spam_channels_str.split(',') if cid.strip()]
        messages.append("Cập nhật Global Spam Channels.")
        
        # Reboot tất cả các bot đang hoạt động để chúng tải lại danh sách kênh spam mới
        with bots_lock:
            if main_bot and bot_active_states.get('main_1', False): reboot_bot('main_1')
            if main_bot_2 and bot_active_states.get('main_2', False): reboot_bot('main_2')
            if main_bot_3 and bot_active_states.get('main_3', False): reboot_bot('main_3')
            for i, bot_instance in enumerate(bots):
                if bot_instance and bot_active_states.get(f'sub_{i}', False):
                    reboot_bot(f'sub_{i}')
    
    save_settings() # Lưu cấu hình sau khi thêm/cập nhật
    
    if not messages:
        messages.append("Không có thông tin nào được cập nhật.")

    return jsonify({'status': 'success', 'message': " ".join(messages)})


# Endpoint để client có thể yêu cầu lưu cài đặt ngay lập tức (vẫn giữ nếu muốn save thủ công)
@app.route("/api/save_settings", methods=['POST'])
def api_save_settings():
    save_settings()
    return jsonify({'status': 'success', 'message': 'Cài đặt đã được lưu.'})


@app.route("/status")
def status():
    now = time.time()
    reboot_countdown = (last_reboot_cycle_time + auto_reboot_delay - now) if auto_reboot_enabled else 0
    spam_countdown = (last_spam_time + spam_delay - now) if spam_enabled else 0

    bot_statuses = {
        "main_bots": [],
        "sub_accounts": []
    }
    
    # Ensure bot_active_states is initialized for main bots before checking
    # This might happen if the config file was empty or main_tokens were added later
    for bot_key in ["main_1", "main_2", "main_3"]:
        if bot_key not in bot_active_states:
            bot_active_states[bot_key] = True # Default to active if not in saved state
    
    with bots_lock:
        bot_statuses["main_bots"].append({"name": "ALPHA", "status": main_bot is not None, "reboot_id": "main_1", "is_active": bot_active_states.get('main_1', False), "type": "main"})
        bot_statuses["main_bots"].append({"name": "BETA", "status": main_bot_2 is not None, "reboot_id": "main_2", "is_active": bot_active_states.get('main_2', False), "type": "main"})
        bot_statuses["main_bots"].append({"name": "GAMMA", "status": main_bot_3 is not None, "reboot_id": "main_3", "is_active": bot_active_states.get('main_3', False), "type": "main"})
        
        bot_statuses["sub_accounts"] = [
            {"name": acc_names[i] if i < len(acc_names) else f"Sub {i+1}", "status": bot is not None, "reboot_id": f"sub_{i}", "is_active": bot_active_states.get(f'sub_{i}', False), "type": "sub"}
            for i, bot in enumerate(bots)
        ]
    
    return jsonify({
        'reboot_enabled': auto_reboot_enabled, 'reboot_countdown': reboot_countdown, 'auto_reboot_delay': auto_reboot_delay,
        'spam_enabled': spam_enabled, 'spam_countdown': spam_countdown, 'spam_message': spam_message, 'spam_delay': spam_delay,
        'global_spam_channels': global_spam_channels, # Pass global spam channels
        'bot_statuses': bot_statuses,
        'server_start_time': server_start_time,
        'auto_grab_configs': auto_grab_configs, # Pass the entire dict for dynamic rendering
        'main_bot_keys': ["main_1", "main_2", "main_3"] # To iterate in JS
    })

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    load_settings() # TẢI CÀI ĐẶT KHI KHỞI ĐỘNG
    
    print("Đang khởi tạo các bot...", flush=True)
    with bots_lock:
        if main_token: 
            main_bot = create_bot(main_token, "main_1")
            if 'main_1' not in bot_active_states:
                bot_active_states['main_1'] = True
                
        if main_token_2: 
            main_bot_2 = create_bot(main_token_2, "main_2")
            if 'main_2' not in bot_active_states:
                bot_active_states['main_2'] = True
                
        if main_token_3: 
            main_bot_3 = create_bot(main_token_3, "main_3")
            if 'main_3' not in bot_active_states:
                bot_active_states['main_3'] = True
                
        for i, token in enumerate(tokens):
            if token.strip():
                bots.append(create_bot(token.strip(), f"sub_{i}"))
                if f'sub_{i}' not in bot_active_states:
                    bot_active_states[f'sub_{i}'] = True

    # Initial save of configs including default active states if loaded_settings was empty
    save_settings() 

    print("Đang khởi tạo các luồng nền...", flush=True)
    threading.Thread(target=periodic_save_loop, daemon=True).start() # BẮT ĐẦU LUỒNG LƯU ĐỊNH KỲ
    
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
