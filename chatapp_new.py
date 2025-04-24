# app.py (Flask后端)
from flask import Flask, jsonify, request, send_from_directory
from openai import OpenAI
import subprocess
import os
import csv
import time
import uuid
from datetime import datetime
import hashlib # 用于密码哈希
import logging
import json # <-- 导入 json 模块

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


app = Flask(__name__, static_folder='static')
current_session = str(uuid.uuid4()) ## 全局会话 ID，现在主要由前端在加载历史时设置
BASE_DIR = os.path.dirname(__file__)
HISTORY_PATH = os.path.join(BASE_DIR, "chat_history.csv") ## 聊天历史
USERS_PATH = os.path.join(BASE_DIR, "users.csv") # 新增：用户存储文件
CONFIG_PATH = os.path.join(BASE_DIR, "config.json") # <-- 新增：配置文件路径

# 全局变量存储当前登录用户 (替代依赖 localStorage)
current_logged_in_user = None # <-- 新增：全局变量

# --- 新增：配置文件读写函数 ---

def load_config():
    """从 config.json 加载配置"""
    global current_logged_in_user
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config_data = json.load(f)
                current_logged_in_user = config_data.get("logged_in_user") # 读取已登录用户
                logging.info(f"从配置文件加载登录用户: {current_logged_in_user}")
                return config_data
        else:
            logging.info(f"配置文件 {CONFIG_PATH} 不存在，将创建。")
            # 文件不存在，返回默认空配置，并初始化 current_logged_in_user 为 None
            current_logged_in_user = None
            return {"logged_in_user": None}
    except (json.JSONDecodeError, IOError) as e:
        logging.error(f"读取配置文件 {CONFIG_PATH} 时出错: {e}。将使用默认配置。")
        # 文件损坏或读取错误，同样返回默认
        current_logged_in_user = None
        return {"logged_in_user": None}

def save_config(config_data):
    """将配置数据保存到 config.json"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False) # indent=4 使文件更易读
        logging.info(f"配置已保存到 {CONFIG_PATH}")
    except IOError as e:
        logging.error(f"保存配置文件 {CONFIG_PATH} 时出错: {e}")

# --- 程序启动时加载配置 ---
config = load_config() # 加载初始配置并设置 current_logged_in_user


# 初始化用户文件和历史文件（如果不存在，则创建并添加表头）
def initialize_files():
    if not os.path.exists(USERS_PATH):
        try:
            with open(USERS_PATH, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["username", "password_hash"]) # 添加表头
            logging.info(f"用户文件已创建: {USERS_PATH}")
        except IOError as e:
            logging.error(f"无法创建用户文件 {USERS_PATH}: {e}")

    if not os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                # **修改：** 添加 username 列
                writer.writerow(["session_id", "username", "user_msg", "ai_msg", "timestamp"]) # 添加表头
            logging.info(f"聊天历史文件已创建: {HISTORY_PATH}")
        except IOError as e:
            logging.error(f"无法创建聊天历史文件 {HISTORY_PATH}: {e}")

initialize_files() # 程序启动时检查并初始化文件

# 全局状态
current_api = "zhipuai"
temperature = 1.0
BASE_URL = "http://localhost:9090/v1"
MODEL_MAPPING = {
    "zhipuai": "glm-4-flash",
    "aliyunai": "Qwen/Qwen2.5-7B-Instruct",
    "deepseek": "deepseek-chat"
}

# --- 新增：用户认证相关函数 ---

# 查找用户
def find_user(username):
    if not os.path.exists(USERS_PATH):
        return None
    try:
        with open(USERS_PATH, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader) # 跳过表头
            for row in reader:
                if len(row) >= 1 and row[0] == username:
                    return row # 返回整行 [username, password_hash]
    except StopIteration: # 文件为空（只有表头）
        return None
    except Exception as e:
        logging.error(f"读取用户文件时出错: {e}")
        return None
    return None

# 注册用户
def register_user(username, hashed_password):
    if find_user(username):
        return False, "用户名已被注册。"

    try:
        with open(USERS_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([username, hashed_password])
        logging.info(f"新用户注册成功: {username}")
        return True, "注册成功！"
    except IOError as e:
        logging.error(f"写入用户文件时出错: {e}")
        return False, "注册过程中发生服务器错误。"

# --- 新增：认证 API 端点 ---

@app.route('/api/register', methods=['POST'])
def handle_register():
    data = request.json
    username = data.get('username')
    hashed_password = data.get('password') # 前端已经哈希过了

    if not username or not hashed_password:
        return jsonify({'success': False, 'error': '缺少用户名或密码'}), 400

    # 基本的用户名和密码格式验证 (可选)
    if len(username) < 3:
         return jsonify({'success': False, 'error': '用户名至少需要3个字符'}), 400
    # 密码哈希的长度通常是固定的 (SHA256 是 64 个十六进制字符)
    if len(hashed_password) != 64:
         return jsonify({'success': False, 'error': '密码格式无效'}), 400


    success, message = register_user(username, hashed_password)
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': message}), 400 # 用户名已存在等是客户端错误

@app.route('/api/login', methods=['POST'])
def handle_login():
    global current_logged_in_user # 声明要修改全局变量
    data = request.json
    username = data.get('username')
    hashed_password_from_client = data.get('password') # 前端已经哈希过了

    if not username or not hashed_password_from_client:
        return jsonify({'success': False, 'error': '缺少用户名或密码'}), 400

    user_data = find_user(username)

    if not user_data:
        return jsonify({'success': False, 'error': '用户名不存在'}), 401 # 401 Unauthorized

    # 比较哈希值
    stored_hashed_password = user_data[1]
    if stored_hashed_password == hashed_password_from_client:
        logging.info(f"用户登录成功: {username}")
        # --- 修改：更新并保存配置 ---
        current_logged_in_user = username # 更新全局变量
        config["logged_in_user"] = username # 更新配置字典
        save_config(config) # 保存到文件
        # --------------------------
        return jsonify({'success': True, 'username': username}) # 可以返回用户名确认
    else:
        logging.warning(f"用户登录失败（密码错误）: {username}")
        return jsonify({'success': False, 'error': '密码错误'}), 401 # 401 Unauthorized

# --- 新增：退出登录 API 端点 ---
@app.route('/api/logout', methods=['POST'])
def handle_logout():
    global current_logged_in_user
    logged_out_user = current_logged_in_user # 获取当前登录用户，用于日志记录
    logging.info(f"用户 {logged_out_user} 请求退出登录")

    # --- 清除配置 ---
    current_logged_in_user = None # 清除全局变量
    config["logged_in_user"] = None # 更新配置字典
    save_config(config) # 保存到文件
    # ----------------

    return jsonify({'success': True})

# --- 新增：检查认证状态 API 端点 ---
@app.route('/api/check_auth', methods=['GET'])
def check_auth():
    """检查当前后端记录的登录状态"""
    if current_logged_in_user:
        logging.debug(f"检查认证状态：用户 '{current_logged_in_user}' 已登录")
        return jsonify({'isLoggedIn': True, 'username': current_logged_in_user})
    else:
        logging.debug("检查认证状态：无用户登录")
        return jsonify({'isLoggedIn': False})

# --- 修改现有 API 以关联用户 ---

# 利用flask的jsonify的框架，将后端处理转发到前端
@app.route('/api/send', methods=['POST'])
def handle_message():
    data = request.json
    user_input = data.get('message', '')
    username = data.get('username') # **新增：** 获取用户名

    if not username:
         logging.warning("收到发送消息请求，但缺少用户名")
         return jsonify({'success': False, 'error': '用户未登录或请求无效'}), 401

    logging.info(f"用户 {username} 发送消息: {user_input[:50]}...") # 日志记录

    try:
        response = ai_call(user_input)
        # **修改：** 传递用户名给 save_chat
        save_chat(username, user_input, response)
        return jsonify({'success': True, 'response': response})
    except Exception as e:
        logging.error(f"处理用户 {username} 消息时出错: {e}")
        return jsonify({'success': False, 'error': f'处理消息时出错: {e}'}), 500

@app.route('/api/switch', methods=['POST'])
def switch_api():
    # 此操作通常是全局的，但最好也确认用户已登录（虽然前端会检查）
    # data = request.json
    # username = data.get('username') # 如果需要记录谁切换的
    # if not username: return jsonify({'success': False, 'error': '需要登录'}), 401

    global current_api
    api = request.json.get('api')
    logging.info(f"API 切换请求: {api}")
    if api in MODEL_MAPPING:
        current_api = api
        logging.info(f"API 已切换为: {current_api}")
        return jsonify({'success': True})
    else:
        logging.warning(f"尝试切换到无效 API: {api}")
        return jsonify({'success': False, 'error': '无效的 API 名称'}), 400


# 温度设置类似，也应该是登录后操作
@app.route('/api/temperature', methods=['POST'])
def set_temperature():
    global temperature
    # 同样可以添加登录验证
    try:
        new_temp = float(request.json.get('temp', 1.0))
        if 0 <= new_temp <= 2:
            temperature = new_temp
            logging.info(f"温度已设置为: {temperature}")
            return jsonify({'success': True})
        logging.warning(f"尝试设置无效温度值: {new_temp}")
        return jsonify({'success': False, 'error': '温度值必须在 0 和 2 之间'}), 400
    except (ValueError, TypeError):
        logging.error(f"设置温度时收到无效值: {request.json.get('temp')}")
        return jsonify({'success': False, 'error': '无效的温度值'}), 400


@app.route('/api/new_chat',methods=['POST'])
def new_chat():
    # 此操作也应验证用户登录（前端已做）
    # data = request.json
    # username = data.get('username') # 如果需要记录
    # if not username: return jsonify({'success': False, 'error': '需要登录'}), 401

    global current_session
    old_session = current_session
    current_session = str(uuid.uuid4()) # 生成新的全局 session_id
    logging.info(f"创建新会话 ID: {current_session} (旧: {old_session})")
    # 注意：这个全局 current_session 可能在多用户场景下不是最佳实践
    # 但对于单用户本地运行或前端驱动会话切换的场景是可行的
    return jsonify({'success': True})

# 回答函数 (不变)
def ai_call(text):
    client = OpenAI(base_url=BASE_URL, api_key="sk-123456")
    response = client.chat.completions.create(
        model=MODEL_MAPPING[current_api],
        messages=[{"role": "user", "content": text}],
        temperature=temperature
    )
    return response.choices[0].message.content


## 保存历史文件 (**修改：** 添加 username 参数和列)
def save_chat(username, user_msg, ai_msg):
    global current_session # 需要访问全局会话ID
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # 使用 datetime 获取更精确的时间
    try:
        # 确保文件存在且有表头，如果需要的话（initialize_files 应该已处理）
        if not os.path.exists(HISTORY_PATH):
             initialize_files()

        with open(HISTORY_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([current_session, username, user_msg, ai_msg, timestamp])
        # logging.info(f"聊天记录已保存 (用户: {username}, 会话: {current_session})")
    except IOError as e:
        logging.error(f"保存聊天记录时出错 (用户: {username}, 会话: {current_session}): {e}")
    except Exception as e:
         logging.error(f"保存聊天时发生未知错误: {e}")


# 会话管理接口 (**修改：** 过滤用户)
@app.route('/api/sessions')
def get_sessions():
    username = request.args.get('user') # **新增：** 从查询参数获取用户名
    if not username:
        logging.warning("获取会话列表请求缺少用户名")
        return jsonify({"error": "需要提供用户名"}), 400

    logging.info(f"用户 {username} 请求会话列表")
    sessions = {}
    if os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                try:
                    header = next(reader) # 读取表头
                    # 验证表头是否符合预期
                    if header != ["session_id", "username", "user_msg", "ai_msg", "timestamp"]:
                         logging.error(f"历史文件表头不匹配: {header}")
                         return jsonify({"error": "历史文件格式错误"}), 500
                except StopIteration:
                    logging.info("历史文件为空")
                    return jsonify([]) # 空文件，返回空列表

                for row in reader:
                    # **修改：** 检查列数和用户名匹配
                    if len(row) == 5 and row[1] == username:
                        session_id = row[0]
                        user_msg = row[2] # 用户消息用于预览
                        timestamp_str = row[4]

                        current_session_data = sessions.get(session_id, {"last_time": "1970-01-01 00:00:00"})

                        try:
                            # 比较时间戳，保留最新的
                            row_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                            current_time = datetime.strptime(current_session_data["last_time"], "%Y-%m-%d %H:%M:%S")
                            if row_time >= current_time:
                                sessions[session_id] = {
                                    "last_time": timestamp_str,
                                    "preview": user_msg[:30] + "..." if len(user_msg) > 30 else user_msg
                                }
                        except ValueError:
                             logging.warning(f"会话 {session_id} (用户 {username}) 的时间戳格式无效: {timestamp_str}")
                             continue
                    elif len(row) != 5:
                        logging.warning(f"跳过格式不正确的行 (用户 {username}): {row}")

        except IOError as e:
            logging.error(f"读取历史记录时出错 (用户 {username}): {e}")
            return jsonify({"error": f"读取历史记录时出错: {e}"}), 500
        except Exception as e:
             logging.error(f"处理历史记录时发生未知错误 (用户 {username}): {e}")
             return jsonify({"error": f"处理历史记录时出错: {e}"}), 500


    session_items = list(sessions.items())
    # 按最后时间排序
    try:
        session_items.sort(key=lambda item: datetime.strptime(item[1]['last_time'], "%Y-%m-%d %H:%M:%S"), reverse=True)
    except ValueError as e:
        logging.error(f"排序会话时时间格式转换失败 (用户 {username}): {e}. 返回未排序列表。")

    logging.info(f"为用户 {username} 返回 {len(session_items)} 个会话")
    return jsonify(session_items)

# 加载特定会话内容 (**修改：** 增加用户验证)
@app.route('/api/load_session')
def load_session_content():
    global current_session # 声明我们要修改全局变量
    session_id = request.args.get('session')
    username = request.args.get('user') # **新增：** 获取用户名

    if not session_id or not username:
        logging.warning("加载会话请求缺少 session_id 或 username")
        return jsonify({"success": False, "error": "缺少 session ID 或用户名"}), 400

    logging.info(f"用户 {username} 请求加载会话: {session_id}")

    messages = []
    session_found_for_user = False # 标记是否找到了属于该用户的此会话记录
    if os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                try:
                    next(reader) # 跳过表头
                except StopIteration:
                    pass # 文件为空

                for row in reader:
                    # **修改：** 检查列数、session_id 和 username 匹配
                    if len(row) == 5 and row[0] == session_id:
                         if row[1] == username:
                             session_found_for_user = True
                             messages.append({"sender": "user", "text": row[2]})
                             messages.append({"sender": "ai", "text": row[3]})
                         else:
                             # 找到了 session 但不属于此用户，记录但不添加到 messages
                              logging.warning(f"用户 {username} 尝试加载不属于自己的会话 {session_id} (属于 {row[1]})")
                              # 可以选择立即返回错误，或继续检查完文件后判断

            if not session_found_for_user:
                 logging.warning(f"用户 {username} 尝试加载的会话 {session_id} 不存在或不属于该用户")
                 # 如果 session 存在但不属于该用户，或者根本找不到该 session，都返回错误
                 return jsonify({"success": False, "error": "无法加载该会话或会话不存在"}), 404 # 404 Not Found


            # 如果找到了属于该用户的会话记录
            current_session = session_id # 切换后端的当前会话 ID
            logging.info(f"用户 {username} 成功加载会话 {session_id}，后端会话已切换")
            return jsonify({"success": True, "messages": messages})

        except IOError as e:
            logging.error(f"加载会话 {session_id} (用户 {username}) 时读取文件出错: {e}")
            return jsonify({"success": False, "error": f"加载会话时出错: {e}"}), 500
        except Exception as e:
             logging.error(f"加载会话 {session_id} (用户 {username}) 时发生未知错误: {e}")
             return jsonify({"success": False, "error": f"加载会话时出错: {e}"}), 500
    else:
        # 历史文件不存在
        logging.warning(f"历史文件 {HISTORY_PATH} 不存在，无法加载会话 {session_id}")
        return jsonify({"success": False, "error": "历史记录文件不存在"}), 404

# 启动 simple-one-api (辅助函数，不变)
def start_api_server():
    current_dir = os.path.dirname(__file__)
    exe_folder = os.path.join(current_dir, "simple-one-api")
    exe_path = os.path.join(exe_folder, "simple-one-api.exe")

    if os.path.exists(exe_path):
        logging.info(f"尝试在目录 {exe_folder} 启动 simple-one-api.exe")
        try:
            # os.chdir(exe_folder) # 改变工作目录可能影响其他文件路径，改为指定 cwd
            process = subprocess.Popen([exe_path], cwd=exe_folder)
            logging.info(f"simple-one-api 进程已启动 (PID: {process.pid})")
            return process
        except Exception as e:
            logging.error(f"启动 simple-one-api.exe 失败: {e}")
            return None
    else:
        logging.warning(f"simple-one-api.exe 未找到于: {exe_path}")
        return None

api_process = start_api_server()


# 根路由 (不变)
@app.route('/')
def index():
    # 总是返回 chat.html，由前端 JS 决定显示登录还是主界面
    return send_from_directory('static', 'chat.html')

# 主程序入口 (修改 webview.start)
if __name__ == '__main__':
    import webview
    # 启动 Flask app (webview 会处理)
    logging.info("启动 Flask 应用和 webview 窗口...")
    window = webview.create_window('FLYINGPIG-AI', app, width=1000, height=700)

    webview.start(debug=True) # <-- 移除 storage_path

    # 清理 simple-one-api 进程 (当 webview 关闭时)
    if api_process:
        logging.info("正在尝试终止 simple-one-api 进程...")
        api_process.terminate()
        try:
            api_process.wait(timeout=5) # 等待进程结束
            logging.info("simple-one-api 进程已终止。")
        except subprocess.TimeoutExpired:
            logging.warning("终止 simple-one-api 进程超时，可能需要手动结束。")
            api_process.kill() # 强制结束