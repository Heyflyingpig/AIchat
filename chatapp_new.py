# app.py (Flask后端)
from flask import Flask, jsonify, request, send_from_directory
from openai import OpenAI
import subprocess
import os
import csv
import time
import uuid
from datetime import datetime



app = Flask(__name__, static_folder='static')
current_session = str(uuid.uuid4()) ## 表示uid
HISTORY_PATH = os.path.join(os.path.dirname(__file__), "chat_history.csv") ##表示历史记录

# 全局状态  
current_api = "zhipuai"
temperature = 1.0
BASE_URL = "http://localhost:9090/v1"
MODEL_MAPPING = {
    "zhipuai": "glm-4-flash",
    "aliyunai": "Qwen/Qwen2.5-7B-Instruct",
    "deepseek": "deepseek-chat"
}

# 启动simple-one-api
def start_api_server():
    current_dir = os.path.dirname(__file__)
    exe_folder = os.path.join(current_dir, "simple-one-api")
    exe_path = os.path.join(exe_folder, "simple-one-api.exe")
    
    if os.path.exists(exe_path):
        os.chdir(exe_folder)
        return subprocess.Popen([exe_path])
    return None

api_process = start_api_server()

# API路由
# 利用flask的jsonify的框架，将后端处理转发到前端
@app.route('/api/send', methods=['POST'])
def handle_message():
    data = request.json
    user_input = data.get('message', '')
    
    try:
        response = ai_call(user_input)
        save_chat(user_input, response)
        return jsonify({'success': True, 'response': response})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/switch', methods=['POST'])
def switch_api():
    global current_api
    api = request.json.get('api')
    if api in MODEL_MAPPING:
        current_api = api
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Invalid API'})


@app.route('/api/temperature', methods=['POST'])
def set_temperature():
    global temperature
    try:
        new_temp = float(request.json.get('temp', 1.0))
        if 0 <= new_temp <= 2:
            temperature = new_temp
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Value out of range'})
    except:
        return jsonify({'success': False, 'error': 'Invalid value'})


@app.route('/api/new_chat',methods=['POST'])
def new_chat():
    global current_session
    current_session = str(uuid.uuid4())
    return jsonify({'success': True})

# 回答函数
def ai_call(text):
    client = OpenAI(base_url=BASE_URL, api_key="sk-123456")
    response = client.chat.completions.create(
        model=MODEL_MAPPING[current_api],
        messages=[{"role": "user", "content": text}],
        temperature=temperature
    )
    return response.choices[0].message.content


## 保存历史文件
def save_chat(user_msg, ai_msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(HISTORY_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([current_session, user_msg, ai_msg, timestamp])

## 加载历史函数
def load_chat():
    history = []
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            history = list(reader)
    return history

# 新增会话管理接口
@app.route('/api/sessions')
def get_sessions():
    sessions = {}
    if os.path.exists(HISTORY_PATH):
        try: # 添加 try...except 块处理可能的读取错误
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                for row in reader:
                    # 添加基本的行数据校验，防止空行或格式错误导致索引错误
                    if len(row) >= 4:
                        session_id = row[0]
                        user_msg = row[1]
                        timestamp_str = row[3]

                        # 使用 get 方法这里是获取了当前遍历的行的id
                        current_session_data = sessions.get(session_id, {"last_time": "1970-01-01 00:00:00"}) # 使用一个很早的默认时间

                        # 只有当新读取到的行的 时间戳 > 当前记录的时间戳 时才更新
                        # 逻辑是当我们当前的首先进入当前的行，然后比较时间，只保留最新的时间
                        try:
                            row_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                            current_time = datetime.strptime(current_session_data["last_time"], "%Y-%m-%d %H:%M:%S")
                            if row_time >= current_time: # 更新为等于也可以，确保取到最后一次交互
                                sessions[session_id] = {
                                    "last_time": timestamp_str, # 存储原始字符串格式
                                    "preview": user_msg[:30] + "..." if len(user_msg) > 30 else user_msg
                                }
                        except ValueError:
                             # 如果时间戳格式错误，可以选择跳过或记录错误
                             print(f"警告：会话 {session_id} 的时间戳格式无效: {timestamp_str}")
                             continue # 跳过此行
                    else:
                        print(f"警告：跳过格式不正确的行: {row}")

        except Exception as e:
            print(f"错误：读取历史记录时出错: {e}")
            return jsonify({"error": f"读取历史记录时出错: {e}"}), 500 # 返回服务器错误


    # 将字典转换为包含 [session_id, session_data] 的列表
    session_items = list(sessions.items())

    #    key=lambda item: item[1]['last_time'] 指定按每个元素的第二个部分（即 session_data 字典）中的 'last_time' 字段排序
    try:
        session_items.sort(key=lambda item: datetime.strptime(item[1]['last_time'], "%Y-%m-%d %H:%M:%S"), reverse=True)
    except ValueError as e:
        print(f"错误：排序时时间格式转换失败: {e}. 可能存在无效的时间戳。将返回未排序或部分排序的数据。")
    return jsonify(session_items)


#是一个纯静态的前端文件（无动态模板渲染），适合直接通过 send_from_directory 返回。
@app.route('/')
def index():
    return send_from_directory('static', 'chat.html')

if __name__ == '__main__':
    import webview
    window = webview.create_window('FLYINGPIG-AI', app)
    webview.start(debug = True)