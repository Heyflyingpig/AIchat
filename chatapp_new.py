# app.py (Flask后端)
from flask import Flask, jsonify, request, send_from_directory
from openai import OpenAI
import subprocess
import os
import csv
import time



app = Flask(__name__, static_folder='static')

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

@app.route('/api/history')
def get_history():
    return jsonify(load_chat())

@app.route('/api/new_chat',methods=['POST'])
def new_chat(): 
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
    with open("chat_history.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([user_msg, ai_msg, timestamp])

## 加载历史函数
def load_chat():
    history = []
    if os.path.exists("chat_history.csv"):
        with open("chat_history.csv", "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            history = list(reader)
    return history

#是一个纯静态的前端文件（无动态模板渲染），适合直接通过 send_from_directory 返回。
@app.route('/')
def index():
    return send_from_directory('static', 'chat.html')

if __name__ == '__main__':
    import webview
    window = webview.create_window('FLYINGPIG-AI', app)
    webview.start()