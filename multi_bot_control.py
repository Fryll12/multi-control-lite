import discum
import time
import threading
import json
import random
import requests
import os
import sys
import re
from collections import deque
from flask import Flask, jsonify, render_template_string, request
from dotenv import load_dotenv

# ===================================================================
# CẤU HÌNH VÀ BIẾN TOÀN CỤC
# ===================================================================

# --- Tải và lấy cấu hình từ biến môi trường ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
KD_CHANNEL_ID = os.getenv("KD_CHANNEL_ID")
KVI_CHANNEL_ID = os.getenv("KVI_CHANNEL_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
JSONBIN_API_KEY = os.getenv("JSONBIN_API_KEY")
JSONBIN_BIN_ID = os.getenv("JSONBIN_BIN_ID")
KARUTA_ID = "646937666251915264"

# --- Kiểm tra biến môi trường ---
if not TOKEN:
    print("LỖI: Vui lòng cung cấp DISCORD_TOKEN trong biến môi trường.", flush=True)
    sys.exit(1)
if not CHANNEL_ID:
    print("LỖI: Vui lòng cung cấp CHANNEL_ID trong biến môi trường.", flush=True)
    sys.exit(1)
if not KD_CHANNEL_ID:
    print("CẢNH BÁO: KD_CHANNEL_ID chưa được cấu hình. Tính năng Auto KD sẽ không khả dụng.", flush=True)
if not KVI_CHANNEL_ID:
    print("CẢNH BÁO: KVI_CHANNEL_ID chưa được cấu hình. Tính năng Auto KVI sẽ không khả dụng.", flush=True)
if not GEMINI_API_KEY:
    print("CẢNH BÁO: GEMINI_API_KEY chưa được cấu hình. Tính năng Auto KVI sẽ không khả dụng.", flush=True)


# --- Các biến trạng thái và điều khiển ---
lock = threading.RLock()

# Các biến trạng thái chạy (sẽ được load từ JSON)
is_event_bot_running = False
is_autoclick_running = False
is_auto_kd_running = False
is_auto_kvi_running = False
is_box_collector_running = False 

# Các biến cài đặt (sẽ được load từ JSON)
is_hourly_loop_enabled = False
loop_delay_seconds = 3600
spam_panels = []
panel_id_counter = 0
next_kvi_allowed_time = 0 

# === THAY ĐỔI LỚN: Bot và Thread toàn cục ===
bot = None # Bot discum duy nhất
main_gateway_thread = None 
spam_thread = None
hourly_loop_thread = None
autoclick_bot_thread = None

# Các biến runtime khác (trước đây là 'nonlocal' trong các hàm thread)
event_active_message_id = None
event_action_queue = deque()
autoclick_target_message_data = None
autoclick_clicks_done = 0

kvi_last_action_time = 0
kvi_last_api_call_time = 0
kvi_last_kvi_send_time = 0
kvi_last_session_end_time = 0
KVI_COOLDOWN_SECONDS = 3
KVI_TIMEOUT_SECONDS = 3605
# ============================================

# ===================================================================
# HÀM LƯU/TẢI CÀI ĐẶT JSON
# ===================================================================

def save_settings():
    """Lưu tất cả cài đặt và trạng thái lên JSONBin.io"""
    with lock:
        if not JSONBIN_API_KEY or not JSONBIN_BIN_ID:
            print("[SETTINGS] WARN: Thiếu API Key hoặc Bin ID, không thể lưu cài đặt.", flush=True)
            return False

        settings_to_save = {
            'is_event_bot_running': is_event_bot_running,
            'is_auto_kd_running': is_auto_kd_running,
            'is_auto_kvi_running': is_auto_kvi_running,
            'is_autoclick_running': is_autoclick_running,
            'is_box_collector_running': is_box_collector_running,
            'is_hourly_loop_enabled': is_hourly_loop_enabled,
            'loop_delay_seconds': loop_delay_seconds,
            'spam_panels': spam_panels,
            'panel_id_counter': panel_id_counter,
            'autoclick_button_index': autoclick_button_index,
            'autoclick_count': autoclick_count,
            'autoclick_clicks_done': autoclick_clicks_done,
            'next_kvi_allowed_time': next_kvi_allowed_time
        }
        
        headers = {
            'Content-Type': 'application/json',
            'X-Master-Key': JSONBIN_API_KEY
        }
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
        
        try:
            req = requests.put(url, json=settings_to_save, headers=headers, timeout=15)
            if req.status_code == 200:
                print("[SETTINGS] INFO: Đã lưu cài đặt lên JSONBin.io thành công.", flush=True)
                return True
            else:
                print(f"[SETTINGS] LỖI: Lỗi khi lưu cài đặt: {req.status_code} - {req.text}", flush=True)
                return False
        except Exception as e:
            print(f"[SETTINGS] LỖI NGOẠI LỆ: Exception khi lưu cài đặt: {e}", flush=True)
            return False

def load_settings():
    """Tải cài đặt từ JSONBin.io khi khởi động"""
    global is_event_bot_running, is_auto_kd_running, is_autoclick_running, is_auto_kvi_running, is_box_collector_running
    global is_hourly_loop_enabled, loop_delay_seconds, spam_panels, panel_id_counter
    global autoclick_button_index, autoclick_count, autoclick_clicks_done
    global next_kvi_allowed_time
    
    with lock:
        if not JSONBIN_API_KEY or not JSONBIN_BIN_ID:
            print("[SETTINGS] INFO: Thiếu API Key hoặc Bin ID, sử dụng cài đặt mặc định.", flush=True)
            return False

        headers = {'X-Master-Key': JSONBIN_API_KEY, 'X-Bin-Meta': 'false'}
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"

        try:
            req = requests.get(url, headers=headers, timeout=15)
            if req.status_code == 200:
                settings = req.json()
                if settings and isinstance(settings, dict):
                    is_event_bot_running = settings.get('is_event_bot_running', False)
                    is_auto_kd_running = settings.get('is_auto_kd_running', False)
                    is_auto_kvi_running = settings.get('is_auto_kvi_running', False)
                    is_autoclick_running = settings.get('is_autoclick_running', False)
                    is_box_collector_running = settings.get('is_box_collector_running', False) 
                    is_hourly_loop_enabled = settings.get('is_hourly_loop_enabled', False)
                    loop_delay_seconds = settings.get('loop_delay_seconds', 3600)
                    spam_panels = settings.get('spam_panels', [])
                    panel_id_counter = settings.get('panel_id_counter', 0)
                    autoclick_button_index = settings.get('autoclick_button_index', 0)
                    autoclick_count = settings.get('autoclick_count', 0)
                    autoclick_clicks_done = settings.get('autoclick_clicks_done', 0)
                    next_kvi_allowed_time = settings.get('next_kvi_allowed_time', 0)
                    
                    if spam_panels:
                        max_id = max(p.get('id', -1) for p in spam_panels)
                        panel_id_counter = max(panel_id_counter, max_id + 1)

                    print("[SETTINGS] INFO: Đã tải cài đặt từ JSONBin.io thành công.", flush=True)
                    print(f"[SETTINGS] INFO: Event Bot: {is_event_bot_running}, Auto KD: {is_auto_kd_running}, Auto KVI: {is_auto_kvi_running}, Auto Click: {is_autoclick_running}, Box Collector: {is_box_collector_running}", flush=True)
                    return True
                else:
                    print("[SETTINGS] INFO: Bin rỗng hoặc không hợp lệ, bắt đầu với cài đặt mặc định.", flush=True)
                    return False
            else:
                print(f"[SETTINGS] LỖI: Lỗi khi tải cài đặt: {req.status_code} - {req.text}.", flush=True)
                return False
        except Exception as e:
            print(f"[SETTINGS] LỖI NGOẠI LỆ: Exception khi tải cài đặt: {e}.", flush=True)
            return False

# ===================================================================
# CÁC HÀM LOGIC CỐT LÕI
# ===================================================================

# <<< THAY ĐỔI: Hàm click giờ sẽ dùng bot toàn cục >>>
def click_button_by_index(message_data, index, source=""):
    global bot # Sử dụng bot toàn cục
    try:
        if not bot or not bot.gateway.session_id:
            print(f"[{source}] LỖI: Bot chưa kết nối hoặc không có session_id.", flush=True)
            return False
        application_id = message_data.get("application_id", KARUTA_ID)
        rows = [comp['components'] for comp in message_data.get('components', []) if 'components' in comp]
        all_buttons = [button for row in rows for button in row]
        if index >= len(all_buttons):
            print(f"[{source}] LỖI: Không tìm thấy button ở vị trí {index}", flush=True)
            return False
        button_to_click = all_buttons[index]
        custom_id = button_to_click.get("custom_id")
        if not custom_id: return False
        headers = {"Authorization": TOKEN}
        max_retries = 10
        for attempt in range(max_retries):
            session_id = bot.gateway.session_id # Luôn lấy session_id MỚI NHẤT từ bot toàn cục
            payload = { "type": 3, "guild_id": message_data.get("guild_id"), "channel_id": message_data.get("channel_id"), "message_id": message_data.get("id"), "application_id": application_id, "session_id": session_id, "data": {"component_type": 2, "custom_id": custom_id} }
            emoji_name = button_to_click.get('emoji', {}).get('name', 'Không có')
            label_name = button_to_click.get('label', 'Không có')
            print(f"[{source}] INFO (Lần {attempt + 1}/{max_retries}): Chuẩn bị click button {index} (Label: {label_name}, Emoji: {emoji_name})", flush=True)
            try:
                r = requests.post("https://discord.com/api/v9/interactions", headers=headers, json=payload, timeout=10)
                if 200 <= r.status_code < 300:
                    print(f"[{source}] INFO: Click thành công!", flush=True)
                    time.sleep(random.uniform(2.5, 3.5))
                    return True
                elif r.status_code == 429:
                    retry_after = r.json().get("retry_after", 1.5)
                    print(f"[{source}] WARN: Bị rate limit! Thử lại sau {retry_after:.2f}s...", flush=True)
                    time.sleep(retry_after)
                else:
                    # Lỗi 50035 (Component Validation Failed) thường xảy ra ở đây do session_id cũ
                    print(f"[{source}] LỖI: Click thất bại! (Status: {r.status_code}, Response: {r.text})", flush=True)
                    time.sleep(2)
            except requests.exceptions.RequestException as e:
                print(f"[{source}] LỖI KẾT NỐI: {e}. Thử lại sau 3s...", flush=True)
                time.sleep(3)
        print(f"[{source}] LỖI: Đã thử click {max_retries} lần không thành công.", flush=True)
        return False
    except Exception as e:
        print(f"[{source}] LỖI NGOẠI LỆ trong hàm click: {e}", flush=True)
        return False

# <<< THAY ĐỔI: Các hàm logic của KVI được đưa ra ngoài >>>
def kvi_answer_question_with_gemini(message_data, question, options):
    global kvi_last_api_call_time, bot
    print(f"[AUTO KVI] GEMINI: Nhận được câu hỏi: '{question}'", flush=True)
    
    try:
        embeds = message_data.get("embeds", [])
        embed = embeds[0] if embeds else {}
        desc = embed.get("description", "")
        
        character_name = "Unknown"
        embed_title = embed.get("title", "")
        if "Character:" in desc:
            char_match = re.search(r'Character:\s*([^(]+)', desc)
            if char_match:
                character_name = char_match.group(1).strip()
        elif embed_title:
            character_name = embed_title.replace("Visit Character", "").strip()
        
        prompt = f"""You are playing Karuta's KVI (Visit Character) system. You are interacting with the character: {character_name}. Your goal is to choose the BEST response to build affection and have a positive interaction with {character_name}.
IMPORTANT RULES:
1. Choose responses that show interest, care, or positive engagement with {character_name}.
2. Consider the character's personality if you know it.
3. Avoid negative, dismissive, or rude responses.
4. Pick answers that would naturally continue the conversation.
5. Prefer romantic or friendly options over neutral ones.
6. Choose responses that would make {character_name} happy or interested.
Question from {character_name}: "{question}"
Available response options:
{chr(10).join([f"{i+1}. {opt}" for i, opt in enumerate(options)])}
Respond with ONLY the number (1, 2, 3, etc.) of the BEST option to increase affection with {character_name}."""

        payload = { "contents": [{"parts": [{"text": prompt}]}] }
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        
        response = requests.post(api_url, headers={'Content-Type': 'application/json'}, json=payload, timeout=15)
        response.raise_for_status()
        
        result = response.json()
        api_text = result['candidates'][0]['content']['parts'][0]['text'].strip()
        
        match = re.search(r'(\d+)', api_text)
        if match:
            selected_option = int(match.group(1))
            if 1 <= selected_option <= len(options):
                print(f"[AUTO KVI] GEMINI: Chọn đáp án {selected_option}: '{options[selected_option-1]}'", flush=True)
                time.sleep(random.uniform(1.5, 2.5))
                if click_button_by_index(message_data, selected_option - 1, "AUTO KVI"):
                    with lock: kvi_last_api_call_time = time.time()
            else:
                print(f"[AUTO KVI] LỖI: Gemini chọn số không hợp lệ: {selected_option}. Chọn đáp án đầu tiên.", flush=True)
                if click_button_by_index(message_data, 0, "AUTO KVI"):
                     with lock: kvi_last_api_call_time = time.time()
        else:
            print(f"[AUTO KVI] LỖI: Không tìm thấy số trong phản hồi: '{api_text}'. Chọn đáp án đầu tiên.", flush=True)
            if click_button_by_index(message_data, 0, "AUTO KVI"):
                 with lock: kvi_last_api_call_time = time.time()

    except requests.exceptions.RequestException as e:
        print(f"[AUTO KVI] LỖI API: {e}. Chọn đáp án đầu tiên.", flush=True)
        if click_button_by_index(message_data, 0, "AUTO KVI"):
             with lock: kvi_last_api_call_time = time.time()
    except Exception as e:
        print(f"[AUTO KVI] LỖI NGOẠI LỆ: {e}. Chọn đáp án đầu tiên.", flush=True)
        if click_button_by_index(message_data, 0, "AUTO KVI"):
             with lock: kvi_last_api_call_time = time.time()

def kvi_smart_button_click(message_data):
    global kvi_last_api_call_time
    components = message_data.get("components", [])
    all_buttons = [button for row in components for button in row.get("components", [])]
    
    if all_buttons:
        target_index = 0
        button_label = all_buttons[target_index].get("label", "Không rõ")
        print(f"[AUTO KVI] INFO: Nhấn vào nút ở vị trí đầu tiên (Index 0, Label: {button_label}).", flush=True)
        time.sleep(random.uniform(1.0, 2.0))
        if click_button_by_index(message_data, target_index, "AUTO KVI"):
            with lock: kvi_last_api_call_time = time.time()
    else:
        print("[AUTO KVI] WARN: Không tìm thấy nút nào để bấm.", flush=True)

def periodic_kvi_sender():
    global kvi_last_action_time, kvi_last_kvi_send_time, next_kvi_allowed_time, bot, is_auto_kvi_running
    
    # Chờ bot sẵn sàng
    while not (bot and bot.gateway.session_id):
        print("[AUTO KVI] Chờ gateway chính sẵn sàng...", flush=True)
        time.sleep(5)
        with lock:
            if not is_auto_kvi_running:
                print("[AUTO KVI] Bị tắt trước khi gateway sẵn sàng.", flush=True)
                return

    time.sleep(10) # Chờ 10s sau khi gateway sẵn sàng

    with lock:
        if time.time() < next_kvi_allowed_time:
            wait_time = next_kvi_allowed_time - time.time()
            print(f"[AUTO KVI] INFO: Đang trong thời gian chờ. Sẽ không gửi kvi khởi tạo. Chờ thêm {wait_time:.0f} giây.", flush=True)
        else:
            try:
                bot.sendMessage(KVI_CHANNEL_ID, "kvi")
                kvi_last_kvi_send_time = time.time()
                kvi_last_action_time = time.time()
                print("[AUTO KVI] INFO: Gửi lệnh kvi khởi tạo", flush=True)
            except Exception as e:
                print(f"[AUTO KVI] LỖI: Không thể gửi kvi khởi tạo: {e}", flush=True)
    
    while True:
        with lock:
            if not is_auto_kvi_running: 
                print("[AUTO KVI] Luồng periodic_kvi_sender đã dừng.", flush=True)
                break
        
        current_time = time.time()
        if current_time - kvi_last_action_time > KVI_TIMEOUT_SECONDS:
            if current_time - kvi_last_kvi_send_time > 300:
                try:
                    print("[AUTO KVI] INFO: Timeout - gửi kvi để khởi động lại", flush=True)
                    bot.sendMessage(KVI_CHANNEL_ID, "kvi")
                    with lock: # Cập nhật thời gian trong lock
                        kvi_last_action_time = current_time
                        kvi_last_kvi_send_time = current_time
                except Exception as e:
                    print(f"[AUTO KVI] LỖI: Không thể gửi kvi timeout: {e}", flush=True)
        time.sleep(60)

# <<< THAY ĐỔI: Hàm này không tạo bot, chỉ chạy logic loop >>>
def run_autoclick_bot_thread():
    global is_autoclick_running, autoclick_clicks_done, autoclick_target_message_data, bot
    
    print("[AUTO CLICK] Luồng auto click đã khởi động.", flush=True)
    while not (bot and bot.gateway.session_id):
        print("[AUTO CLICK] Chờ gateway chính sẵn sàng...", flush=True)
        time.sleep(2)
        with lock:
            if not is_autoclick_running:
                print("[AUTO CLICK] Bị tắt trước khi gateway sẵn sàng.", flush=True)
                return

    try:
        while True:
            with lock:
                if not is_autoclick_running: break
                if autoclick_count > 0 and autoclick_clicks_done >= autoclick_count:
                    print("[AUTO CLICK] INFO: Đã hoàn thành.", flush=True)
                    break
                target_data = autoclick_target_message_data
            
            if target_data:
                if click_button_by_index(target_data, autoclick_button_index, "AUTO CLICK"):
                    with lock: 
                        autoclick_clicks_done += 1
                        save_settings()
                else:
                    print("[AUTO CLICK] LỖI NGHIÊM TRỌNG: Không thể click. Dừng.", flush=True)
                    break
            else:
                print("[AUTO CLICK] WARN: Chưa có tin nhắn event.", flush=True)
                time.sleep(5)
    except Exception as e:
        print(f"[AUTO CLICK] LỖI: Exception trong loop: {e}", flush=True)
    finally:
        with lock:
            is_autoclick_running = False
            # autoclick_bot_instance = None # Không còn instance riêng
            save_settings()
        print("[AUTO CLICK] Luồng auto click đã dừng.", flush=True)

# <<< THAY ĐỔI: Hàm này không tạo bot, chỉ chạy logic loop >>>
def run_hourly_loop_thread():
    global is_hourly_loop_enabled, loop_delay_seconds, bot, is_event_bot_running
    print("[HOURLY LOOP] Luồng vòng lặp đã khởi động.", flush=True)
    
    while not (bot and bot.gateway.session_id):
        print("[HOURLY LOOP] Chờ gateway chính sẵn sàng...", flush=True)
        time.sleep(2)
        with lock:
            if not is_hourly_loop_enabled:
                print("[HOURLY LOOP] Bị tắt trước khi gateway sẵn sàng.", flush=True)
                return
    
    try:
        while True:
            start_wait = time.time()
            while time.time() - start_wait < loop_delay_seconds:
                 with lock:
                    if not is_hourly_loop_enabled:
                        break 
                 time.sleep(1)

            with lock:
                if not is_hourly_loop_enabled:
                    break 
                
                if is_event_bot_running and bot and bot.gateway.session_id:
                    print(f"\n[HOURLY LOOP] Hết {loop_delay_seconds} giây. Gửi 'kevent'...", flush=True)
                    bot.sendMessage(CHANNEL_ID, "kevent")
                elif not is_event_bot_running:
                     print(f"\n[HOURLY LOOP] Đã hết giờ nhưng Event Bot không chạy. Tự tắt vòng lặp.", flush=True)
                     is_hourly_loop_enabled = False
                     break 
    except Exception as e:
        print(f"[HOURLY LOOP] LỖI: Exception trong loop: {e}", flush=True)
    finally:
        with lock:
            save_settings()
        print("[HOURLY LOOP] Luồng vòng lặp đã dừng.", flush=True)

def get_new_random_delay(panel):
    """Calculates the next spam delay based on the panel's selected mode."""
    mode = panel.get('delay_mode', 'minutes') 

    if mode == 'seconds':
        min_seconds = panel.get('delay_min_seconds', 240)
        max_seconds = panel.get('delay_max_seconds', 300)
        if min_seconds > max_seconds:
            min_seconds, max_seconds = max_seconds, min_seconds
        return random.uniform(min_seconds, max_seconds)
    else: 
        min_minutes = panel.get('delay_min_minutes', 4)
        max_minutes = panel.get('delay_max_minutes', 5)
        if min_minutes > max_minutes:
            min_minutes, max_minutes = max_minutes, min_minutes
        
        chosen_minutes = random.randint(min_minutes, max_minutes)
        humanizer_seconds = random.randint(1, 15)
        return (chosen_minutes * 60) + humanizer_seconds

# <<< THAY ĐỔI: Hàm này không tạo bot, chỉ chạy logic loop >>>
def spam_loop():
    global bot
    print("[SPAM BOT] Luồng spam đã khởi động.", flush=True)
    while not (bot and bot.gateway.session_id):
        print("[SPAM BOT] Đang chờ gateway chính sẵn sàng...", flush=True)
        time.sleep(2)
    
    print("[SPAM BOT] Gateway sẵn sàng. Bắt đầu vòng lặp spam.", flush=True)

    while True:
        try:
            with lock:
                panels_to_process = list(spam_panels)
            
            panels_ready_to_fire = []
            for panel in panels_to_process:
                if panel.get('is_active') and panel.get('channel_id') and panel.get('message') and time.time() >= panel.get('next_spam_time', 0):
                   panels_ready_to_fire.append(panel)
            
            if not panels_ready_to_fire:
                time.sleep(1)
                continue

            for panel in panels_ready_to_fire:
                    try:
                        bot.sendMessage(str(panel['channel_id']), str(panel['message']))
                        print(f"[SPAM BOT] Gửi tin nhắn tới kênh {panel['channel_id']}", flush=True)
                        
                        with lock:
                            for p in spam_panels:
                                if p['id'] == panel['id']:
                                    next_delay = get_new_random_delay(p)
                                    p['next_spam_time'] = time.time() + next_delay
                                    print(f"[SPAM BOT] Panel {p['id']} (Mode: {p.get('delay_mode', 'minutes')}) hẹn giờ tiếp theo sau {next_delay:.2f} giây.", flush=True)
                                    break
                            save_settings()
                            
                    except Exception as e:
                        print(f"[SPAM BOT] LỖI: Không thể gửi tin nhắn. {e}", flush=True)
                        with lock:
                            for p in spam_panels: 
                                if p['id'] == panel['id']:
                                    p['next_spam_time'] = time.time() + 60 
                                    break
            time.sleep(0.5) 
        except Exception as e:
            print(f"LỖI NGOẠI LỆ trong vòng lặp spam: {e}", flush=True)
            time.sleep(5)

# ===================================================================
# <<< MỚI: HÀM GATEWAY CHÍNH >>>
# ===================================================================
def run_main_gateway_thread():
    global bot, event_active_message_id, event_action_queue
    global autoclick_target_message_data
    global kvi_last_action_time, kvi_last_api_call_time, kvi_last_session_end_time, next_kvi_allowed_time
    
    bot = discum.Client(token=TOKEN, log=False)
    
    box_collector_last_message_id = None

    # --- Handler cho Event Bot (Chế độ 2) ---
    def handle_event_bot_message(m):
        global event_active_message_id, event_action_queue
        
        def perform_final_confirmation(message_data):
            print("[EVENT BOT] ACTION: Chờ 2s cho nút cuối...", flush=True)
            time.sleep(2)
            click_button_by_index(message_data, 2, "EVENT BOT")
            print("[EVENT BOT] INFO: Hoàn thành lượt.", flush=True)

        with lock:
            if "Takumi's Solisfair Stand" in m.get("embeds", [{}])[0].get("title", ""):
                # Chỉ cập nhật nếu là tin nhắn mới (không phải update)
                if 'message_id' not in m: # Heuristic for new message
                    event_active_message_id = m.get("id")
                    event_action_queue.clear()
                    print(f"\n[EVENT BOT] INFO: Phát hiện game mới. ID: {event_active_message_id}", flush=True)
            if m.get("id") != event_active_message_id: 
                return
        
        embed_desc = m.get("embeds", [{}])[0].get("description", "")
        all_buttons_flat = [b for row in m.get('components', []) for b in row.get('components', []) if row.get('type') == 1]
        is_movement_phase = any(b.get('emoji', {}).get('name') == '▶️' for b in all_buttons_flat)
        is_final_confirm_phase = any(b.get('emoji', {}).get('name') == '❌' for b in all_buttons_flat)
        found_good_move = "If placed here, you will receive the following fruit:" in embed_desc
        has_received_fruit = "You received the following fruit:" in embed_desc
        
        if is_final_confirm_phase:
            with lock: event_action_queue.clear() 
            threading.Thread(target=perform_final_confirmation, args=(m,)).start()
        elif has_received_fruit:
            threading.Thread(target=click_button_by_index, args=(m, 0, "EVENT BOT")).start()
        elif is_movement_phase:
            with lock:
                if found_good_move:
                    print("[EVENT BOT] INFO: NGẮT QUÃNG - Phát hiện nước đi tốt.", flush=True)
                    event_action_queue.clear()
                    event_action_queue.append(0)
                elif not event_action_queue:
                    print("[EVENT BOT] INFO: Tạo chuỗi hành động...", flush=True)
                    action_queue.extend([1, 1, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 1, 1, 1, 1, 2, 2, 3, 3])
                    action_queue.extend([random.choice([1,2,3,4]) for _ in range(random.randint(4, 12))])
                    action_queue.append(0)
                if event_action_queue:
                    next_action_index = event_action_queue.popleft()
                    threading.Thread(target=click_button_by_index, args=(m, next_action_index, "EVENT BOT")).start()

    # --- Handler cho Auto Click (Chế độ 3) ---
    def handle_autoclick_message(m):
        global autoclick_target_message_data
        if "Takumi's Solisfair Stand" in m.get("embeds", [{}])[0].get("title", ""):
             with lock: autoclick_target_message_data = m
             print(f"[AUTO CLICK] INFO: Đã cập nhật tin nhắn game. ID: {m.get('id')}", flush=True)

    # --- Handler cho Box Collector (Chế độ 1) ---
    def handle_box_collector_message(m):
        nonlocal box_collector_last_message_id
        if "Takumi's Solisfair Stand" in m.get("embeds", [{}])[0].get("title", ""):
            if m.get("id") == box_collector_last_message_id: return
            box_collector_last_message_id = m.get("id")
            
            print("[BOX COLLECTOR] INFO: Phát hiện tin nhắn event. Click nút 0...", flush=True)
            
            def action_thread():
                if click_button_by_index(m, 0, "BOX COLLECTOR"):
                    time.sleep(random.uniform(2.5, 3.5)) 
                    with lock:
                        if not is_box_collector_running: return 
                    try:
                        print("[BOX COLLECTOR] INFO: Gửi 'kevent' tiếp theo...", flush=True)
                        bot.sendMessage(CHANNEL_ID, "kevent")
                    except Exception as e:
                        print(f"[BOX COLLECTOR] LỖI: Không thể gửi 'kevent': {e}", flush=True)
                else:
                    print("[BOX COLLECTOR] LỖI: Không thể click nút 0. Dừng...", flush=True)
                    with lock:
                        is_box_collector_running = False 
                        save_settings()
            threading.Thread(target=action_thread, daemon=True).start()

    # --- Handler cho Auto KD ---
    def handle_auto_kd_message(m):
        message_content = m.get("content", "").lower()
        embed_description = ""
        embeds = m.get("embeds", [])
        if embeds: embed_description = embeds[0].get("description", "").lower()
        if ("blessing has activated!" in message_content or "blessing has activated!" in embed_description):
            print("[AUTO KD] INFO: Phát hiện blessing activated!", flush=True)
            delay = random.uniform(1.5, 3.0)
            time.sleep(delay)
            try:
                bot.sendMessage(KD_CHANNEL_ID, "kd")
                print(f"[AUTO KD] SUCCESS: Đã gửi kd.", flush=True)
            except Exception as e:
                print(f"[AUTO KD] LỖI: Không thể gửi kd. {e}", flush=True)

    # --- Handler cho Auto KVI ---
    def handle_auto_kvi_message(m):
        global kvi_last_action_time, kvi_last_api_call_time, kvi_last_session_end_time, next_kvi_allowed_time

        current_time = time.time()
        with lock: kvi_last_action_time = current_time

        if current_time - kvi_last_api_call_time < KVI_COOLDOWN_SECONDS:
            return

        components = m.get("components", [])
        action_row = components[0] if components and components[0].get("type") == 1 else {}
        all_buttons = action_row.get("components", [])

        if all_buttons and all_buttons[0].get("disabled", False):
            if time.time() - kvi_last_session_end_time > 60:
                with lock: kvi_last_session_end_time = time.time()
                with lock:
                    next_kvi_allowed_time = time.time() + 1800 
                    print(f"[AUTO KVI] INFO: Nút 'Talk' đã bị vô hiệu hóa. Phiên KVI kết thúc.", flush=True)
                    print(f"[AUTO KVI] INFO: KVI tiếp theo được phép sau {time.strftime('%H:%M:%S', time.localtime(next_kvi_allowed_time))}", flush=True)
                    save_settings()
            return 

        embeds = m.get("embeds", [])
        if not embeds: return
        embed = embeds[0]
        desc = embed.get("description", "")
        
        if '1️⃣' in desc:
            print("[AUTO KVI] INFO: Phát hiện câu hỏi có emoji 1️⃣. Dùng AI...", flush=True)
            question_patterns = [r'["“](.+?)["”]', r'"([^"]+)"']
            question_found = False
            for pattern in question_patterns:
                question_match = re.search(pattern, desc, re.DOTALL)
                if question_match:
                    question = question_match.group(1).strip()
                    options = []
                    lines = desc.split('\n')
                    for line in lines:
                        match = re.search(r'^\s*(?:\d{1,2}[\.\)]|:keycap_(\d{1,2}):|(\d{1,2})️⃣)\s*(.+)', line)
                        if match:
                            option_text = match.groups()[-1].strip()
                            if option_text:
                                options.append(option_text)
                    
                    if question and len(options) >= 2:
                        question_found = True
                        threading.Thread(target=kvi_answer_question_with_gemini, args=(m, question, options), daemon=True).start()
                        break
            
            if not question_found:
                 print("[AUTO KVI] WARN: Có emoji 1️⃣ nhưng không thể phân tích câu hỏi. Chuyển sang hành động mặc định.", flush=True)
                 threading.Thread(target=kvi_smart_button_click, args=(m,), daemon=True).start()
        else:
            print("[AUTO KVI] INFO: Không có câu hỏi. Thực hiện hành động mặc định (bấm nút đầu tiên).", flush=True)
            threading.Thread(target=kvi_smart_button_click, args=(m,), daemon=True).start()


    # --- MASTER ON_MESSAGE ---
    @bot.gateway.command
    def on_message(resp):
        nonlocal box_collector_last_message_id
        
        if not (resp.event.message or resp.event.message_updated): return
        m = resp.parsed.auto()
        if not m.get("author", {}).get("id") == KARUTA_ID: return

        channel_id = m.get("channel_id")

        with lock:
            # Kênh Event Chính
            if channel_id == CHANNEL_ID:
                if is_event_bot_running:
                    handle_event_bot_message(m)
                elif is_autoclick_running:
                    handle_autoclick_message(m)
                elif is_box_collector_running:
                    handle_box_collector_message(m)
            
            # Kênh Auto KD
            elif channel_id == KD_CHANNEL_ID and is_auto_kd_running:
                handle_auto_kd_message(m)
            
            # Kênh Auto KVI
            elif channel_id == KVI_CHANNEL_ID and is_auto_kvi_running:
                handle_auto_kvi_message(m)

    # --- MASTER ON_READY ---
    @bot.gateway.command
    def on_ready(resp):
        if resp.event.ready_supplemental: # Dùng ready_supplemental tốt hơn
            print("[GATEWAY] Gateway chính đã sẵn sàng.", flush=True)
            with lock:
                if is_event_bot_running:
                    print("[GATEWAY] Gửi 'kevent' cho Event Bot.", flush=True)
                    bot.sendMessage(CHANNEL_ID, "kevent")
                if is_box_collector_running:
                    print("[GATEWAY] Gửi 'kevent' cho Box Collector.", flush=True)
                    bot.sendMessage(CHANNEL_ID, "kevent")
                if is_auto_kvi_running:
                    print(f"[GATEWAY] Khởi động KVI loop. Theo dõi kênh {KVI_CHANNEL_ID}...", flush=True)
                    threading.Thread(target=periodic_kvi_sender, daemon=True).start()
        
        if resp.event.ready:
             print(f"[GATEWAY] Đang theo dõi kênh KD {KD_CHANNEL_ID} (nếu bật).", flush=True)


    print("[GATEWAY] Khởi động luồng gateway chính...", flush=True)
    try:
        bot.gateway.run(auto_reconnect=True)
    except Exception as e:
        print(f"[GATEWAY] LỖI: Gateway bị lỗi: {e}", flush=True)
    finally:
        print("[GATEWAY] Luồng gateway chính đã dừng.", flush=True)


# ===================================================================
# HÀM KHỞI ĐỘNG LẠI BOT THEO TRẠNG THÁI ĐÃ LƯU
# ===================================================================
# <<< THAY ĐỔI: Chỉ khởi động lại các thread lặp độc lập >>>
def restore_bot_states():
    """Khởi động lại các thread logic theo trạng thái đã lưu"""
    global autoclick_bot_thread, hourly_loop_thread
    
    # Event, KD, KVI, Box Collector đều dựa trên on_message/on_ready
    # on_ready sẽ tự xử lý việc gửi tin nhắn ban đầu cho KVI, Event, Box
    
    if is_autoclick_running:
        print("[RESTORE] Khôi phục Auto Click...", flush=True)
        autoclick_bot_thread = threading.Thread(target=run_autoclick_bot_thread, daemon=True)
        autoclick_bot_thread.start()
    
    if is_hourly_loop_enabled:
        print("[RESTORE] Khôi phục Hourly Loop...", flush=True)
        hourly_loop_thread = threading.Thread(target=run_hourly_loop_thread, daemon=True)
        hourly_loop_thread.start()

# ===================================================================
# WEB SERVER (FLASK)
# ===================================================================
app = Flask(__name__)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8"> <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bot Control Panel</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #121212; color: #e0e0e0; display: flex; flex-direction: column; align-items: center; gap: 20px; padding: 20px;}
        .container { display: flex; flex-wrap: wrap; justify-content: center; gap: 20px; width: 100%; max-width: 1300px; }
        .panel { text-align: center; background-color: #1e1e1e; padding: 20px; border-radius: 10px; box-shadow: 0 0 20px rgba(0,0,0,0.5); width: 100%; max-width: 400px; display: flex; flex-direction: column; gap: 15px; border: 2px solid #1e1e1e; transition: border-color 0.3s;}
        .panel.active-mode { border-color: #03dac6; }
        .panel.active-mode-alt { border-color: #f7b731; } /* <<< TÍNH NĂNG MỚI: Màu mới cho box */
        h1, h2 { color: #bb86fc; margin-top: 0; } .status { font-size: 1.1em; }
        .status-on { color: #03dac6; } .status-on-alt { color: #f7b731; } .status-off { color: #cf6679; }
        button { background-color: #bb86fc; color: #121212; border: none; padding: 12px 24px; font-size: 1em; border-radius: 5px; cursor: pointer; transition: all 0.3s; font-weight: bold; }
        button:hover:not(:disabled) { background-color: #a050f0; transform: translateY(-2px); }
        button:disabled { background-color: #444; color: #888; cursor: not-allowed; }
        .input-group { display: flex; flex-direction: column; gap: 5px; } .input-group label { text-align: left; font-size: 0.9em; color: #aaa; }
        .input-group-row { display: flex; } .input-group-row label { white-space: nowrap; padding: 10px; background-color: #333; border-radius: 5px 0 0 5px; }
        .input-group-row input { width:100%; border: 1px solid #333; background-color: #222; color: #eee; padding: 10px; border-radius: 0 5px 5px 0; }
        .spam-controls { display: flex; flex-direction: column; gap: 20px; width: 100%; max-width: 840px; background-color: #1e1e1e; padding: 20px; border-radius: 10px; }
        #panel-container { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; width: 100%; }
        .spam-panel { background-color: #2a2a2a; padding: 20px; border-radius: 10px; display: flex; flex-direction: column; gap: 15px; border-left: 5px solid #333; }
        .spam-panel.active { border-left-color: #03dac6; }
        .spam-panel input, .spam-panel textarea { width: 100%; box-sizing: border-box; border: 1px solid #444; background-color: #333; color: #eee; padding: 10px; border-radius: 5px; font-size: 1em; }
        .spam-panel textarea { resize: vertical; min-height: 80px; }
        .spam-panel-controls { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
        .delete-btn { background-color: #cf6679 !important; }
        .add-panel-btn { width: 100%; padding: 15px; font-size: 1.2em; background-color: rgba(3, 218, 198, 0.2); border: 2px dashed #03dac6; color: #03dac6; cursor: pointer; border-radius: 10px;}
        .timer { font-size: 0.9em; color: #888; text-align: right; }
        .save-status { position: fixed; top: 10px; right: 10px; padding: 10px; border-radius: 5px; z-index: 1000; display: none; }
        .save-success { background-color: #03dac6; color: #121212; }
        .save-error { background-color: #cf6679; color: #fff; }
        .channel-display {font-size:0.8em; color:#666; margin:10px 0;}
        .delay-range-group { display: flex; align-items: center; gap: 5px; }
        .delay-range-group input { text-align: center; }
        .delay-range-group span { color: #888; }
        .mode-selector { display: flex; gap: 10px; background-color: #333; padding: 5px; border-radius: 5px; }
        .mode-selector label { cursor: pointer; padding: 5px 10px; border-radius: 5px; transition: background-color 0.3s; user-select: none;}
        .mode-selector input { display: none; }
        .mode-selector input:checked + label { background-color: #bb86fc; color: #121212; }
        .delay-inputs { display: none; }
        .delay-inputs.visible { display: flex; flex-direction: column; gap: 5px; }
    </style>
</head>
<body>
    <div id="saveStatus" class="save-status"></div>
    <h1>Karuta Bot Control</h1>
    <p>Chọn một chế độ để chạy. Các chế độ Event, AutoClick và Nhận Box không thể chạy cùng lúc.</p>
    <div class="container">
        <!-- <<< TÍNH NĂNG MỚI: Thêm Panel Nhận Box >>> -->
        <div class="panel" id="box-collector-panel"><h2>Chế độ 1: Auto Nhận Box</h2><p style="font-size:0.9em; color:#aaa;">Tự động lặp lại: [gửi 'kevent' -> click nút 0].</p><div id="box-collector-status" class="status">Trạng thái: ĐÃ DỪNG</div><button id="toggleBoxCollectorBtn">Bật Auto Nhận Box</button></div>
        
        <div class="panel" id="event-bot-panel"><h2>Chế độ 2: Auto Play Event</h2><p style="font-size:0.9em; color:#aaa;">Tự động chơi event với logic phức tạp (di chuyển, tìm quả, xác nhận).</p><div id="event-bot-status" class="status">Trạng thái: ĐÃ DỪNG</div><button id="toggleEventBotBtn">Bật Auto Play</button></div>
        
        <div class="panel" id="autoclick-panel"><h2>Chế độ 3: Auto Click</h2><p style="font-size:0.9em; color:#aaa;">Chỉ click liên tục vào một nút. Bạn phải tự gõ 'kevent' để bot nhận diện.</p><div id="autoclick-status" class="status">Trạng thái: ĐÃ DỪNG</div><div class="input-group"><label for="autoclick-button-index">Button Index</label><input type="number" id="autoclick-button-index" value="0" min="0"></div><div class="input-group"><label for="autoclick-count">Số lần click (0 = ∞)</label><input type="number" id="autoclick-count" value="10" min="0"></div><button id="toggleAutoclickBtn">Bật Auto Click</button></div>

        <div class="panel" id="auto-kd-panel"><h2>Auto KD</h2><p style="font-size:0.9em; color:#aaa;">Tự động gửi 'kd' khi phát hiện "blessing has activated!" trong kênh KD.</p><div id="auto-kd-status" class="status">Trạng thái: ĐÃ DỪNG</div><div class="channel-display">KD Channel: <span id="kd-channel-display"></span></div><button id="toggleAutoKdBtn">Bật Auto KD</button></div>
        
        <div class="panel" id="auto-kvi-panel"><h2>Auto KVI (dùng Gemini AI)</h2><p style="font-size:0.9em; color:#aaa;">Tự động tương tác KVI. Dùng AI để chọn câu trả lời tốt nhất.</p><div id="auto-kvi-status" class="status">Trạng thái: ĐÃ DỪNG</div><div class="channel-display">KVI Channel: <span id="kvi-channel-display"></span></div><button id="toggleAutoKviBtn">Bật Auto KVI</button></div>
        
        <div class="panel"><h2>Tiện ích: Vòng lặp Event</h2><p style="font-size:0.9em; color:#aaa;">Tự động gửi 'kevent' theo chu kỳ. Chỉ hoạt động khi "Chế độ 2" (Auto Play) đang chạy.</p><div id="loop-status" class="status">Trạng thái: ĐÃ DỪNG</div><div class="input-group-row"><label for="delay-input">Delay (giây)</label><input type="number" id="delay-input" value="3600"></div><button id="toggleLoopBtn">Bật Vòng lặp</button></div>
    </div>
    <div class="spam-controls">
        <h2>Tiện ích: Spam Tin Nhắn</h2>
        <div id="panel-container"></div>
        <button class="add-panel-btn" onclick="addPanel()">+ Thêm Bảng Spam</button>
    </div>
    <script>
        function showSaveStatus(message, isSuccess) {
            const status = document.getElementById('saveStatus');
            status.textContent = message;
            status.className = 'save-status ' + (isSuccess ? 'save-success' : 'save-error');
            status.style.display = 'block';
            setTimeout(() => status.style.display = 'none', 3000);
        }
        
        async function apiCall(endpoint, method = 'POST', body = null) {
            const options = { method, headers: {'Content-Type': 'application/json'} };
            if (body) options.body = JSON.stringify(body);
            try {
                const response = await fetch(endpoint, options);
                if (!response.ok) {
                    const errorResult = await response.json();
                    showSaveStatus(`Lỗi: ${errorResult.message || 'Unknown error'}`, false);
                    return { error: errorResult.message || 'API call failed' };
                }
                const result = await response.json();
                if (result.save_status !== undefined) {
                    showSaveStatus(result.save_status ? 'Đã lưu thành công' : 'Lỗi khi lưu', result.save_status);
                }
                return result;
            } catch (error) { 
                console.error('API call failed:', error); 
                showSaveStatus('Lỗi kết nối', false);
                return { error: 'API call failed' }; 
            }
        }
        
        async function fetchStatus() {
            const data = await apiCall('/api/status', 'GET');
            if (data.error) { document.getElementById('event-bot-status').textContent = 'Lỗi kết nối server.'; return; }
            
            const updateStatus = (elemId, text, className, btnId, btnText, panelId, active) => {
                document.getElementById(elemId).textContent = text;
                document.getElementById(elemId).className = className;
                if(btnId) document.getElementById(btnId).textContent = btnText;
                if(panelId) document.getElementById(panelId).classList.toggle('active-mode', active);
            };
            
            // <<< TÍNH NĂNG MỚI: Cập nhật UI cho Box Collector >>>
            const isEventChannelBotRunning = data.is_event_bot_running || data.is_autoclick_running || data.is_box_collector_running;
            
            updateStatus('box-collector-status', data.is_box_collector_running ? 'Trạng thái: ĐANG CHẠY' : 'Trạng thái: ĐÃ DỪNG', data.is_box_collector_running ? 'status status-on-alt' : 'status status-off', 'toggleBoxCollectorBtn', data.is_box_collector_running ? 'Dừng Nhận Box' : 'Bật Auto Nhận Box', 'box-collector-panel', data.is_box_collector_running);
            document.getElementById('box-collector-panel').classList.toggle('active-mode-alt', data.is_box_collector_running); // Dùng màu viền khác
            document.getElementById('toggleBoxCollectorBtn').disabled = data.is_event_bot_running || data.is_autoclick_running;

            // Cập nhật các bot khác
            updateStatus('event-bot-status', data.is_event_bot_running ? 'Trạng thái: ĐANG CHẠY' : 'Trạng thái: ĐÃ DỪNG', data.is_event_bot_running ? 'status status-on' : 'status status-off', 'toggleEventBotBtn', data.is_event_bot_running ? 'Dừng Auto Play' : 'Bật Auto Play', 'event-bot-panel', data.is_event_bot_running);
            document.getElementById('toggleEventBotBtn').disabled = data.is_autoclick_running || data.is_box_collector_running;
            
            const countText = data.autoclick_count > 0 ? `${data.autoclick_clicks_done}/${data.autoclick_count}` : `${data.autoclick_clicks_done}/∞`;
            updateStatus('autoclick-status', data.is_autoclick_running ? `Trạng thái: ĐANG CHẠY (${countText})` : 'Trạng thái: ĐÃ DỪNG', data.is_autoclick_running ? 'status status-on' : 'status status-off', 'toggleAutoclickBtn', data.is_autoclick_running ? 'Dừng Auto Click' : 'Bật Auto Click', 'autoclick-panel', data.is_autoclick_running);
            document.getElementById('autoclick-button-index').disabled = data.is_autoclick_running; document.getElementById('autoclick-count').disabled = data.is_autoclick_running; 
            document.getElementById('toggleAutoclickBtn').disabled = data.is_event_bot_running || data.is_box_collector_running;
            
            // Auto KD và KVI (không thay đổi)
            updateStatus('auto-kd-status', data.is_auto_kd_running ? 'Trạng thái: ĐANG CHẠY' : 'Trạng thái: ĐÃ DỪNG', data.is_auto_kd_running ? 'status status-on' : 'status status-off', 'toggleAutoKdBtn', data.is_auto_kd_running ? 'Dừng Auto KD' : 'Bật Auto KD', 'auto-kd-panel', data.is_auto_kd_running);
            document.getElementById('kd-channel-display').textContent = data.kd_channel_id;
            updateStatus('auto-kvi-status', data.is_auto_kvi_running ? 'Trạng thái: ĐANG CHẠY' : 'Trạng thái: ĐÃ DỪNG', data.is_auto_kvi_running ? 'status status-on' : 'status status-off', 'toggleAutoKviBtn', data.is_auto_kvi_running ? 'Dừng Auto KVI' : 'Bật Auto KVI', 'auto-kvi-panel', data.is_auto_kvi_running);
            document.getElementById('kvi-channel-display').textContent = data.kvi_channel_id;
            
            // Loop (không thay đổi)
            updateStatus('loop-status', data.is_hourly_loop_enabled ? 'Trạng thái: ĐANG CHẠY' : 'Trạng thái: ĐÃ DỪNG', data.is_hourly_loop_enabled ? 'status status-on' : 'status status-off', 'toggleLoopBtn', data.is_hourly_loop_enabled ? 'TẮT VÒNG LẶP' : 'BẬT VÒNG LẶP');
            document.getElementById('toggleLoopBtn').disabled = !data.is_event_bot_running && !data.is_hourly_loop_enabled; document.getElementById('delay-input').value = data.loop_delay_seconds;
        }
        
        // <<< TÍNH NĂNG MỚI: Thêm sự kiện click cho nút mới >>>
        document.getElementById('toggleBoxCollectorBtn').addEventListener('click', () => apiCall('/api/toggle_box_collector').then(fetchStatus));
        
        document.getElementById('toggleEventBotBtn').addEventListener('click', () => apiCall('/api/toggle_event_bot').then(fetchStatus));
        document.getElementById('toggleAutoclickBtn').addEventListener('click', () => apiCall('/api/toggle_autoclick', 'POST', { button_index: parseInt(document.getElementById('autoclick-button-index').value, 10), count: parseInt(document.getElementById('autoclick-count').value, 10) }).then(fetchStatus));
        document.getElementById('toggleAutoKdBtn').addEventListener('click', () => apiCall('/api/toggle_auto_kd').then(fetchStatus));
        document.getElementById('toggleAutoKviBtn').addEventListener('click', () => apiCall('/api/toggle_auto_kvi').then(fetchStatus));
        document.getElementById('toggleLoopBtn').addEventListener('click', () => apiCall('/api/toggle_hourly_loop', 'POST', { enabled: !document.getElementById('loop-status').textContent.includes('ĐANG CHẠY'), delay: parseInt(document.getElementById('delay-input').value, 10) }).then(fetchStatus));
        
        function createPanelElement(panel) {
            const div = document.createElement('div');
            div.className = `spam-panel ${panel.is_active ? 'active' : ''}`; 
            div.dataset.id = panel.id;
            const isMinutesMode = panel.delay_mode !== 'seconds';
            let countdown = (panel.is_active && panel.next_spam_time) ? Math.max(0, Math.ceil(panel.next_spam_time - (Date.now() / 1000))) : 0;
            // <<< FIX LỖI SPAM: Hiển thị 0s nếu countdown < 0 >>>
            countdown = countdown > 0 ? countdown + 's' : '0s';

            div.innerHTML = `
                <div class="input-group"><label>Nội dung spam</label><textarea class="message-input">${panel.message}</textarea></div>
                <div class="input-group"><label>ID Kênh</label><input type="text" class="channel-input" value="${panel.channel_id}"></div>
                
                <div class="input-group">
                    <label>Chế độ Delay</label>
                    <div class="mode-selector">
                        <input type="radio" id="mode-seconds-${panel.id}" name="mode-${panel.id}" value="seconds" ${!isMinutesMode ? 'checked' : ''}><label for="mode-seconds-${panel.id}">Theo Giây</label>
                        <input type="radio" id="mode-minutes-${panel.id}" name="mode-${panel.id}" value="minutes" ${isMinutesMode ? 'checked' : ''}><label for="mode-minutes-${panel.id}">Theo Phút</label>
                    </div>
                </div>

                <div class="delay-inputs delay-inputs-seconds ${!isMinutesMode ? 'visible' : ''}">
                    <label>Delay ngẫu nhiên (giây)</label>
                    <div class="delay-range-group">
                        <input type="number" class="delay-input-min-seconds" value="${panel.delay_min_seconds || 240}"><span>-</span><input type="number" class="delay-input-max-seconds" value="${panel.delay_max_seconds || 300}">
                    </div>
                </div>
                <div class="delay-inputs delay-inputs-minutes ${isMinutesMode ? 'visible' : ''}">
                    <label>Delay ngẫu nhiên (phút)</label>
                    <div class="delay-range-group">
                         <input type="number" class="delay-input-min-minutes" value="${panel.delay_min_minutes || 4}"><span>-</span><input type="number" class="delay-input-max-minutes" value="${panel.delay_max_minutes || 5}">
                    </div>
                </div>

                <div class="spam-panel-controls">
                    <button class="toggle-btn">${panel.is_active ? 'DỪNG' : 'CHẠY'}</button>
                    <button class="delete-btn">XÓA</button>
                </div>
                <div class="timer">Tiếp theo trong: ${panel.is_active ? countdown : '...'}</div>
            `;
            
            const getPanelData = () => {
                let min_s = parseInt(div.querySelector('.delay-input-min-seconds').value, 10) || 240; let max_s = parseInt(div.querySelector('.delay-input-max-seconds').value, 10) || 300;
                if (min_s > max_s) [min_s, max_s] = [max_s, min_s];
                let min_m = parseInt(div.querySelector('.delay-input-min-minutes').value, 10) || 4; let max_m = parseInt(div.querySelector('.delay-input-max-minutes').value, 10) || 5;
                if (min_m > max_m) [min_m, max_m] = [max_m, min_m];
                return { 
                    ...panel, 
                    message: div.querySelector('.message-input').value, channel_id: div.querySelector('.channel-input').value, 
                    delay_mode: div.querySelector('input[name="mode-' + panel.id + '"]:checked').value,
                    delay_min_seconds: min_s, delay_max_seconds: max_s,
                    delay_min_minutes: min_m, delay_max_minutes: max_m
                }
            };
            
            div.querySelector('.toggle-btn').addEventListener('click', () => apiCall('/api/panel/update', 'POST', { ...getPanelData(), is_active: !panel.is_active }).then(fetchPanels));
            div.querySelector('.delete-btn').addEventListener('click', () => { if (confirm('Bạn có chắc muốn xóa bảng spam này?')) apiCall('/api/panel/delete', 'POST', { id: panel.id }).then(fetchPanels); });
            
            ['message-input', 'channel-input', 'delay-input-min-seconds', 'delay-input-max-seconds', 'delay-input-min-minutes', 'delay-input-max-minutes'].forEach(cls => {
                div.querySelector('.' + cls).addEventListener('change', () => apiCall('/api/panel/update', 'POST', getPanelData()));
            });

            div.querySelectorAll('input[name="mode-' + panel.id + '"]').forEach(radio => {
                radio.addEventListener('change', (e) => {
                    div.querySelector('.delay-inputs-seconds').classList.toggle('visible', e.target.value === 'seconds');
                    div.querySelector('.delay-inputs-minutes').classList.toggle('visible', e.target.value === 'minutes');
                    apiCall('/api/panel/update', 'POST', getPanelData());
                });
            });
            
            return div;
        }
        
        async function fetchPanels() {
            if (document.activeElement && ['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;
            const data = await apiCall('/api/panels', 'GET');
            const container = document.getElementById('panel-container'); 
            
            // Giữ lại trạng thái cuộn và focus
            const focusedElement = document.activeElement;
            const focusedId = focusedElement ? focusedElement.closest('.spam-panel')?.dataset.id : null;
            const focusedClass = focusedElement ? focusedElement.className : null;
            
            container.innerHTML = '';
            if (data.panels) data.panels.forEach(panel => container.appendChild(createPanelElement(panel)));

            // Khôi phục focus
            if(focusedId && focusedClass) {
                const newPanel = container.querySelector(`[data-id="${focusedId}"]`);
                if(newPanel) {
                    const newElement = newPanel.querySelector('.' + focusedClass.split(' ')[0]); // Lấy class đầu tiên
                    if(newElement) newElement.focus();
                }
            }
        }
        
        async function addPanel() { await apiCall('/api/panel/add'); fetchPanels(); }
        
        document.addEventListener('DOMContentLoaded', () => {
            fetchStatus(); fetchPanels();
            setInterval(fetchStatus, 5000); 
            setInterval(fetchPanels, 1000); // Update timer mỗi giây
        });
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/status", methods=['GET'])
def status():
    with lock:
        return jsonify({
            "is_event_bot_running": is_event_bot_running,
            "is_hourly_loop_enabled": is_hourly_loop_enabled,
            "loop_delay_seconds": loop_delay_seconds,
            "is_autoclick_running": is_autoclick_running,
            "autoclick_button_index": autoclick_button_index,
            "autoclick_count": autoclick_count,
            "autoclick_clicks_done": autoclick_clicks_done,
            "is_auto_kd_running": is_auto_kd_running,
            "kd_channel_id": KD_CHANNEL_ID or "Chưa cấu hình",
            "is_auto_kvi_running": is_auto_kvi_running,
            "kvi_channel_id": KVI_CHANNEL_ID or "Chưa cấu hình",
            "is_box_collector_running": is_box_collector_running 
        })

# <<< THAY ĐỔI: Các hàm Toggle giờ chỉ thay đổi cờ trạng thái >>>
# Gateway sẽ tự phát hiện và gửi tin nhắn (ví dụ kevent)
@app.route("/api/toggle_event_bot", methods=['POST'])
def toggle_event_bot():
    global is_event_bot_running, is_autoclick_running, is_box_collector_running, bot
    with lock:
        if is_autoclick_running or is_box_collector_running:
            return jsonify({"status": "error", "message": "Bot khác (Auto Click hoặc Nhận Box) đang chạy. Tắt nó trước."}), 400
        
        if is_event_bot_running:
            is_event_bot_running = False
            print("[CONTROL] Nhận lệnh DỪNG Bot Event.", flush=True)
        else:
            is_event_bot_running = True
            print("[CONTROL] Nhận lệnh BẬT Bot Event.", flush=True)
            if bot and bot.gateway.session_id: # Nếu bot đang chạy
                print("[CONTROL] Gửi 'kevent' ban đầu.", flush=True)
                bot.sendMessage(CHANNEL_ID, "kevent")
        
        save_result = save_settings()
    return jsonify({"status": "ok", "save_status": save_result})

@app.route("/api/toggle_autoclick", methods=['POST'])
def toggle_autoclick():
    global autoclick_bot_thread, is_autoclick_running, is_event_bot_running, is_box_collector_running
    global autoclick_button_index, autoclick_count, autoclick_clicks_done, autoclick_target_message_data
    data = request.get_json()
    with lock:
        if is_event_bot_running or is_box_collector_running:
            return jsonify({"status": "error", "message": "Bot khác (Event Bot hoặc Nhận Box) đang chạy. Tắt nó trước."}), 400
            
        if is_autoclick_running:
            is_autoclick_running = False
            print("[CONTROL] Nhận lệnh DỪNG Auto Click.", flush=True)
            # Thread autoclick sẽ tự dừng khi thấy cờ False
        else:
            is_autoclick_running = True
            autoclick_button_index = int(data.get('button_index', 0))
            autoclick_count = int(data.get('count', 1))
            autoclick_clicks_done = 0
            autoclick_target_message_data = None
            print(f"[CONTROL] Nhận lệnh BẬT Auto Click: {autoclick_count or 'vô hạn'} lần vào button {autoclick_button_index}.", flush=True)
            # Khởi động thread lặp
            autoclick_bot_thread = threading.Thread(target=run_autoclick_bot_thread, daemon=True)
            autoclick_bot_thread.start()
        
        save_result = save_settings()
    return jsonify({"status": "ok", "save_status": save_result})

@app.route("/api/toggle_box_collector", methods=['POST'])
def toggle_box_collector():
    global is_box_collector_running, is_event_bot_running, is_autoclick_running, bot
    with lock:
        if is_event_bot_running or is_autoclick_running:
            return jsonify({"status": "error", "message": "Bot khác (Event Bot hoặc Auto Click) đang chạy. Tắt nó trước."}), 400
            
        if is_box_collector_running:
            is_box_collector_running = False
            print("[CONTROL] Nhận lệnh DỪNG Auto Nhận Box.", flush=True)
        else:
            is_box_collector_running = True
            print(f"[CONTROL] Nhận lệnh BẬT Auto Nhận Box.", flush=True)
            if bot and bot.gateway.session_id:
                print("[CONTROL] Gửi 'kevent' ban đầu.", flush=True)
                bot.sendMessage(CHANNEL_ID, "kevent")
        
        save_result = save_settings()
    return jsonify({"status": "ok", "save_status": save_result})


@app.route("/api/toggle_auto_kd", methods=['POST'])
def toggle_auto_kd():
    global is_auto_kd_running
    with lock:
        if not KD_CHANNEL_ID:
            return jsonify({"status": "error", "message": "Chưa cấu hình KD_CHANNEL_ID."}), 400
        
        if is_auto_kd_running:
            is_auto_kd_running = False
            print("[CONTROL] Nhận lệnh DỪNG Auto KD.", flush=True)
        else:
            is_auto_kd_running = True
            print("[CONTROL] Nhận lệnh BẬT Auto KD.", flush=True)
        
        save_result = save_settings()
    return jsonify({"status": "ok", "save_status": save_result})

@app.route("/api/toggle_auto_kvi", methods=['POST'])
def toggle_auto_kvi():
    global is_auto_kvi_running, kvi_last_action_time
    with lock:
        if not KVI_CHANNEL_ID or not GEMINI_API_KEY:
            return jsonify({"status": "error", "message": "Chưa cấu hình KVI_CHANNEL_ID hoặc GEMINI_API_KEY."}), 400
        
        if is_auto_kvi_running:
            is_auto_kvi_running = False
            print("[CONTROL] Nhận lệnh DỪNG Auto KVI.", flush=True)
            # Thread periodic_kvi_sender sẽ tự dừng
        else:
            is_auto_kvi_running = True
            kvi_last_action_time = time.time() # Reset KVI timer
            print("[CONTROL] Nhận lệnh BẬT Auto KVI.", flush=True)
            # Khởi động KVI loop
            threading.Thread(target=periodic_kvi_sender, daemon=True).start()
        
        save_result = save_settings()
    return jsonify({"status": "ok", "save_status": save_result})

@app.route("/api/toggle_hourly_loop", methods=['POST'])
def toggle_hourly_loop():
    global hourly_loop_thread, is_hourly_loop_enabled, loop_delay_seconds
    data = request.get_json()
    with lock:
        is_hourly_loop_enabled = data.get('enabled')
        loop_delay_seconds = int(data.get('delay', 3600))
        if loop_delay_seconds < 60: 
            loop_delay_seconds = 60
            
        if is_hourly_loop_enabled:
            if hourly_loop_thread is None or not hourly_loop_thread.is_alive():
                hourly_loop_thread = threading.Thread(target=run_hourly_loop_thread, daemon=True)
                hourly_loop_thread.start()
            print(f"[CONTROL] Vòng lặp ĐÃ BẬT với delay {loop_delay_seconds} giây.", flush=True)
        else:
            print("[CONTROL] Vòng lặp ĐÃ TẮT.", flush=True)
        
        save_result = save_settings()
    return jsonify({"status": "ok", "save_status": save_result})

# ===================================================================
# API CHO SPAM PANEL
# ===================================================================
@app.route("/api/panels", methods=['GET'])
def get_panels():
    with lock:
        return jsonify({"panels": spam_panels})

@app.route("/api/panel/add", methods=['POST'])
def add_panel():
    global panel_id_counter
    with lock:
        new_panel = { 
            "id": panel_id_counter, 
            "message": "", 
            "channel_id": "", 
            "delay_mode": "minutes",
            "delay_min_minutes": 4, 
            "delay_max_minutes": 5,
            "delay_min_seconds": 240,
            "delay_max_seconds": 300,
            "is_active": False, 
            "next_spam_time": 0 
        }
        spam_panels.append(new_panel)
        panel_id_counter += 1
        save_result = save_settings()
    return jsonify({"status": "ok", "new_panel": new_panel, "save_status": save_result})

@app.route("/api/panel/update", methods=['POST'])
def update_panel():
    data = request.get_json()
    with lock:
        for panel in spam_panels:
            if panel['id'] == data['id']:
                is_activating = data.get('is_active') and not panel.get('is_active')
                
                if is_activating:
                    data['next_spam_time'] = time.time() 
                    print(f"[SPAM CONTROL] Panel {panel['id']} đã kích hoạt, gửi ngay lập tức.", flush=True)
                
                panel.update(data)
                break
        save_result = save_settings()
    return jsonify({"status": "ok", "save_status": save_result})

@app.route("/api/panel/delete", methods=['POST'])
def delete_panel():
    data = request.get_json()
    with lock:
        spam_panels[:] = [p for p in spam_panels if p['id'] != data['id']]
        save_result = save_settings()
    return jsonify({"status": "ok", "save_status": save_result})

# ===================================================================
# KHỞI CHẠY WEB SERVER
# ===================================================================
if __name__ == "__main__":
    load_settings()
    
    # Khởi động gateway chính TRƯỚC TIÊN
    print("[MAIN] Khởi động Gateway chính...", flush=True)
    main_gateway_thread = threading.Thread(target=run_main_gateway_thread, daemon=True)
    main_gateway_thread.start()

    # Bây giờ mới khởi động các thread logic (như spam, autoclick)
    restore_bot_states() 

    spam_thread = threading.Thread(target=spam_loop, daemon=True)
    spam_thread.start()
    
    port = int(os.environ.get("PORT", 10000))
    print(f"[SERVER] Khởi động Web Server tại http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False)

