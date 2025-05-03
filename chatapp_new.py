# app.py (Flask后端)
from flask import Flask, jsonify, request, send_from_directory
from openai import OpenAI
import subprocess
import os
import csv
import uuid
from datetime import datetime
import logging
import json # <-- 导入 json 模块
import shutil # <-- 新增：导入 shutil 用于文件操作

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


app = Flask(__name__, static_folder='static')
current_session = str(uuid.uuid4()) ## 全局会话 ID，现在主要由前端在加载历史时设置
BASE_DIR = os.path.dirname(__file__)
SETTING_DIR = os.path.join(BASE_DIR, "setting")

HISTORY_PATH = os.path.join(BASE_DIR, "chat_history.csv") ## 聊天历史
USERS_PATH = os.path.join(BASE_DIR, "users.csv") # 新增：用户存储文件
CONFIG_PATH = os.path.join(BASE_DIR, "Uconfig.json") # <-- 新增：用户界面配置路径

# --- 新增：API 相关路径 ---
API_FOLDER_PATH = os.path.join(BASE_DIR, "simple-one-api") # API程序和其配置所在目录
# simple-one-api 读取的动态配置文件 (确保 simple-one-api.exe 读取的是这个文件)
CONFIG_ACTIVE_PATH = os.path.join(API_FOLDER_PATH, "config.json")
# 默认配置模板路径 
CONFIG_TEMPLATE_PATH = os.path.join(BASE_DIR, "config_template.json")
# 用户密钥存储文件
USER_KEYS_PATH = os.path.join(BASE_DIR, "user_api_keys.json")
# 模型元数据路径
MCONFIG_PATH = os.path.join(BASE_DIR, "Mconfig.json")

# --- 全局变量 ---
api_process = None # 存储 API 进程
current_logged_in_user = None # 当前登录用户
config = {} # 用户界面配置 (Uconfig.json)

# --- 新增：用户密钥管理函数 ---

def load_user_keys():
    """加载所有用户的密钥"""
    if not os.path.exists(USER_KEYS_PATH):
        logging.info(f"用户密钥文件 {USER_KEYS_PATH} 不存在，将创建空文件。")
        save_user_keys({}) # 创建一个空文件
        return {} # 文件不存在返回空字典
    try:
        with open(USER_KEYS_PATH, 'r', encoding='utf-8') as f:
            # 处理空文件的情况
            content = f.read()
            if not content:
                return {}
            return json.loads(content)
    except (json.JSONDecodeError, IOError) as e:
        logging.error(f"读取用户密钥文件 {USER_KEYS_PATH} 时出错: {e}. 返回空数据。")
        return {}

def save_user_keys(user_keys_data):
    """保存所有用户的密钥"""
    try:
        with open(USER_KEYS_PATH, 'w', encoding='utf-8') as f:
            json.dump(user_keys_data, f, indent=4, ensure_ascii=False)
        logging.info(f"用户密钥已保存到 {USER_KEYS_PATH}")
    except IOError as e:
        logging.error(f"保存用户密钥文件 {USER_KEYS_PATH} 时出错: {e}")

def merge_config_with_user_keys(username):
    """将用户密钥合并到模板配置中，并写入活动的 config.json"""
    try:
        # 1. 读取模板配置
        if not os.path.exists(CONFIG_TEMPLATE_PATH):
             logging.error(f"配置模板 {CONFIG_TEMPLATE_PATH} 未找到！无法加载配置。")
             # 尝试从当前的活动配置创建模板？或者报错？这里选择报错
             return False
        with open(CONFIG_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
            active_config = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logging.error(f"无法读取配置模板 {CONFIG_TEMPLATE_PATH}: {e}。无法为用户 {username} 加载配置。")
        return False # 返回失败

    # 2. 读取用户密钥
    all_user_keys = load_user_keys()
    user_specific_keys = all_user_keys.get(username, {}) # 获取当前用户的密钥字典

    # 3. 合并密钥 (只合并用户已定义的key)
    if user_specific_keys and 'services' in active_config:
        logging.info(f"为用户 {username} 合并已保存的密钥...")
        for service_type, service_list in active_config.get('services', {}).items():
            for i, service_instance in enumerate(service_list):
                models_in_instance = service_instance.get("models", [])
                # 检查此服务实例中的任何模型是否在用户的密钥中有定义
                for model_name in models_in_instance:
                    if model_name in user_specific_keys:
                        user_key = user_specific_keys[model_name]
                        if user_key: # 只合并非空的 key
                             if "credentials" not in active_config['services'][service_type][i]:
                                 active_config['services'][service_type][i]["credentials"] = {}
                             active_config['services'][service_type][i]["credentials"]["api_key"] = user_key
                             logging.debug(f"  - 模型 {model_name} (服务 {service_type}) 使用用户保存的密钥。")
                             # 假设一个服务实例共享一个key，找到一个匹配就更新并跳出内层 model 循环
                             break

    # 4. 写入活动的 config.json
    try:
        with open(CONFIG_ACTIVE_PATH, 'w', encoding='utf-8') as f:
            json.dump(active_config, f, indent=2, ensure_ascii=False) # Use indent=2 like original config
        logging.info(f"已为用户 {username} 更新活动的配置文件 {CONFIG_ACTIVE_PATH}")
        return True # 返回成功
    except IOError as e:
        logging.error(f"写入活动配置文件 {CONFIG_ACTIVE_PATH} 时出错: {e}")
        return False # 返回失败

def apply_default_config():
    """将模板配置写回活动的 config.json"""
    if not os.path.exists(CONFIG_TEMPLATE_PATH):
         logging.error(f"配置模板 {CONFIG_TEMPLATE_PATH} 未找到！无法恢复默认配置。")
         return False
    try:
        # 直接复制模板文件到活动配置文件路径
        shutil.copy2(CONFIG_TEMPLATE_PATH, CONFIG_ACTIVE_PATH)
        logging.info(f"已将默认配置模板 {CONFIG_TEMPLATE_PATH} 应用到活动配置 {CONFIG_ACTIVE_PATH}")
        return True
    except Exception as e:
        logging.error(f"应用默认配置时出错 (从 {CONFIG_TEMPLATE_PATH} 到 {CONFIG_ACTIVE_PATH}): {e}")
        return False


# --- 配置文件读写函数 (Uconfig.json) ---

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

    # 新增：确保必要的配置文件存在
    if not os.path.exists(CONFIG_PATH):
         logging.info(f"用户界面配置文件 {CONFIG_PATH} 不存在，将创建。")
         save_config({"logged_in_user": None}) # 创建包含默认值的配置

    if not os.path.exists(USER_KEYS_PATH):
         logging.info(f"用户密钥文件 {USER_KEYS_PATH} 不存在，将创建。")
         save_user_keys({}) # 创建空的密钥文件

    # 确保活动配置文件存在，如果不存在则从模板复制
    if not os.path.exists(CONFIG_ACTIVE_PATH):
         logging.warning(f"活动配置文件 {CONFIG_ACTIVE_PATH} 不存在。")
         if apply_default_config():
             logging.info(f"已从模板创建活动配置文件 {CONFIG_ACTIVE_PATH}。")
         else:
             logging.error(f"无法创建活动配置文件 {CONFIG_ACTIVE_PATH}！API 服务可能无法启动。")

initialize_files() # 程序启动时检查并初始化文件

# 全局状态
current_api = "zhipuai" # 默认 API 标识符 (需要与 MODEL_MAPPING 的 key 对应)
temperature = 1.0
BASE_URL = "http://localhost:9090/v1"
#用于前端的映射
MODEL_MAPPING = {
    "zhipuai": "glm-4-flash",         # 智谱AI
    "aliyunai": "Qwen/Qwen2.5-7B-Instruct", # 阿里通义千问
    "deepseek": "deepseek-chat",     # Deepseek
    # "test_api": "test" # 如果有 test 模型，也需要映射
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

# --- 新增：辅助函数，用于从模板配置中查找默认 Key ---
def get_default_key_from_template(model_name, template_data):
    """
    在加载的模板配置数据中查找指定模型的默认 API Key。
    返回非空 Key 字符串或 None。
    """
    if not template_data or 'services' not in template_data:
        return None
    for service_type, service_list in template_data.get('services', {}).items():
        for service_instance in service_list:
            # 检查当前服务实例配置是否包含目标模型
            if model_name in service_instance.get("models", []):
                # 找到了包含该模型的服务配置块
                key = service_instance.get("credentials", {}).get("api_key")
                # 只有当 key 存在且不为空字符串时，才认为模板有有效 Key
                if key:
                    return key # 返回找到的非空 Key
                else:
                    # 找到了配置块，但 key 为空或不存在
                    return None
    # 遍历完所有服务配置块，都没找到该模型
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
    global current_logged_in_user, config # 引入 config
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

        # --- 更新并保存 Uconfig.json ---
        current_logged_in_user = username
        config["logged_in_user"] = username
        save_config(config) # 保存到 Uconfig.json

        # --- 应用用户特定的 API Key 配置并重启服务 ---
        logging.info(f"正在为用户 {username} 应用 API Key 配置...")
        if merge_config_with_user_keys(username):
            restart_api_server() # 成功合并配置后重启服务
        else:
            logging.error(f"未能为用户 {username} 正确加载 API Key 配置！服务可能使用旧配置或默认配置。")
            # 可以考虑是否返回错误给前端
            # return jsonify({'success': False, 'error': '加载用户API配置时出错'}), 500

        return jsonify({'success': True, 'username': username})
    else:
        logging.warning(f"用户登录失败（密码错误）: {username}")
        return jsonify({'success': False, 'error': '密码错误'}), 401

# 登出
@app.route('/api/logout', methods=['POST'])
def handle_logout():
    global current_logged_in_user, config # 引入 config
    logged_out_user = current_logged_in_user
    logging.info(f"用户 {logged_out_user} 请求退出登录")

    # --- 清除 Uconfig.json 中的登录状态 ---
    current_logged_in_user = None
    config["logged_in_user"] = None
    save_config(config) # 保存到 Uconfig.json

    # --- 恢复默认 API 配置并重启服务 ---
    logging.info("正在恢复默认 API Key 配置...")
    if apply_default_config():
        restart_api_server() # 成功恢复默认配置后重启服务
    else:
        logging.error("未能恢复默认 API 配置！服务可能仍在运行用户配置。")

    return jsonify({'success': True})

# --- 检查认证状态 API 端点 ---
@app.route('/api/check_auth', methods=['GET'])
def check_auth():
    """检查当前后端记录的登录状态"""
    if current_logged_in_user:
        logging.debug(f"检查认证状态：用户 '{current_logged_in_user}' 已登录")
        return jsonify({'isLoggedIn': True, 'username': current_logged_in_user})
    else:
        logging.debug("检查认证状态：无用户登录")
        return jsonify({'isLoggedIn': False})

# 回答函数 (不变)
def ai_call(text):
    client = OpenAI(base_url=BASE_URL, api_key="sk-123456") # key "sk-123456" 可能是 simple-one-api 需要的固定值，或者会被忽略
    model_name = MODEL_MAPPING.get(current_api) # 从当前 API 标识符获取模型名称

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

'''
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
'''

# 温度设置类似，也应该是登录后操作  b
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
    model_name = MODEL_MAPPING.get(current_api) # 从当前 API 标识符获取模型名称

    if not model_name:
         logging.error(f"无法找到 API 标识符 '{current_api}' 对应的模型名称！请检查 MODEL_MAPPING。")
         # 可以抛出异常或返回错误信息
         raise ValueError(f"Invalid API identifier: {current_api}")
         # return "Error: Backend model mapping configuration issue."

    logging.info(f"使用模型 '{model_name}' (API标识: {current_api}, 温度: {temperature}) 进行调用")
    
  
    response = client.chat.completions.create(
        model=model_name, # 使用映射得到的模型名称
        messages=[{"role": "user", "content": text}],
        # temperature=temperature
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
    global api_process # 确保修改全局变量

    # 先尝试终止现有进程（如果存在且仍在运行）
    if api_process and api_process.poll() is None: # poll() 返回 None 表示进程仍在运行
        logging.warning("start_api_server 被调用，但似乎已有进程在运行。将尝试终止现有进程。")
        try:
            api_process.terminate()
            api_process.wait(timeout=5)
        except Exception as e:
            logging.warning(f"尝试终止现有进程时出错: {e}")
            try:
                 api_process.kill() # 强制结束
                 api_process.wait(timeout=2)
            except: pass # 忽略错误
        api_process = None

    exe_path = os.path.join(API_FOLDER_PATH, "simple-one-api.exe")
    active_config_path = CONFIG_ACTIVE_PATH # 使用活动配置路径

    # 检查活动配置文件是否存在，如果不存在则尝试应用默认配置
    if not os.path.exists(active_config_path):
         logging.warning(f"活动配置文件 {active_config_path} 不存在。尝试应用默认配置。")
         if not apply_default_config():
             logging.error("无法应用默认配置。API 服务无法启动。")
             return # 无法启动

    if os.path.exists(exe_path):
        logging.info(f"尝试在目录 {API_FOLDER_PATH} 启动 simple-one-api.exe (读取 {active_config_path})")
        try:
            # 使用 cwd 指定工作目录，creationflags 避免 Windows 弹窗
            process = subprocess.Popen([exe_path], cwd=API_FOLDER_PATH, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            logging.info(f"simple-one-api 进程已启动 (PID: {process.pid})")
            api_process = process # <-- 将新进程赋给全局变量
        except Exception as e:
            logging.error(f"启动 simple-one-api.exe 失败: {e}")
            api_process = None
    else:
        logging.warning(f"simple-one-api.exe 未找到于: {exe_path}")
        api_process = None

def restart_api_server():
    """停止并重新启动 simple-one-api 服务"""
    global api_process
    if api_process:
        logging.info(f"尝试终止现有的 simple-one-api 进程 (PID: {api_process.pid})")
        try:
            # 检查进程是否还在运行
            if api_process.poll() is None:
                 api_process.terminate() # 尝试友好终止
                 api_process.wait(timeout=5) # 等待最多5秒
                 logging.info("simple-one-api 进程已终止。")
            else:
                 logging.info("simple-one-api 进程已经结束，无需终止。")
        except subprocess.TimeoutExpired:
            logging.warning("simple-one-api 进程未在超时内终止，强制结束...")
            if api_process.poll() is None: # 再次检查是否需要kill
                api_process.kill() # 强制终止
                try:
                    api_process.wait(timeout=2) # 等待强制结束后确认
                except: pass # 忽略等待错误
            logging.info("simple-one-api 进程已被强制结束。")
        except Exception as e:
            logging.warning(f"终止 simple-one-api 时发生错误: {e}")
        finally:
             api_process = None # 清除旧的进程对象引用

    logging.info("正在重新启动 simple-one-api 服务...")
    start_api_server() # 启动新的实例

# 获取模型列表 (修改 require_key 逻辑)
@app.route('/api/get_models', methods=['GET'])
def get_models():
    username = request.args.get('user')
    if not username or username != current_logged_in_user:
        return jsonify({"error": "用户未登录或认证失败"}), 401

    models_structure = []
    try:
        # 1. 读取 Mconfig.json 获取公司和模型名称
        if not os.path.exists(MCONFIG_PATH):
            logging.error(f"模型元数据文件 {MCONFIG_PATH} 未找到！")
            return jsonify({"error": "服务器模型配置缺失"}), 500
        with open(MCONFIG_PATH, 'r', encoding='utf-8') as f:
            mconfig = json.load(f)

        # 2. 读取用户密钥数据
        all_user_keys = load_user_keys()
        user_specific_keys = all_user_keys.get(username, {}) # 获取当前用户的密钥
         # +++ 新增：读取 config_template.json 的内容 +++
        config_template_data = None
        if not os.path.exists(CONFIG_TEMPLATE_PATH):
             logging.warning(f"配置模板文件 {CONFIG_TEMPLATE_PATH} 未找到！无法检查默认 Key。")
             # 即使模板不存在，也应该继续执行，只是无法判断模板是否有 Key
        else:
             try:
                 with open(CONFIG_TEMPLATE_PATH, 'r', encoding='utf-8') as f_template:
                     config_template_data = json.load(f_template)
             except (json.JSONDecodeError, IOError) as e:
                 logging.error(f"读取配置模板 {CONFIG_TEMPLATE_PATH} 失败: {e}。无法检查默认 Key。")
                 # 出错时也继续，当作模板没有 Key 处理

        # 3. 构建返回给前端的数据结构
        for company_name, company_data in mconfig.items():
            company_models = []
            model_names_in_company = company_data.get("models", [])

            for model_name in model_names_in_company:
                # **修改判断逻辑:** requires_key is True if user hasn't provided a non-empty key for this model
                user_has_key = model_name in user_specific_keys and user_specific_keys[model_name]
    
                # b. ++ 新增：检查 config_template.json 中是否有非空默认 Key ++
                template_default_key = get_default_key_from_template(model_name, config_template_data)
                template_has_key = bool(template_default_key) # 如果找到了非空 Key，则为 True

                # c. ++ 修改：重新计算 requires_key ++
                # 只有当用户没存 Key 且模板也没预设 Key 时，才为 True
                requires_key_now = (not user_has_key) and (not template_has_key)
                # --- 判断逻辑修改结束 ---

                # 记录日志，方便调试
                logging.debug(f"模型: {model_name}, 用户有Key: {user_has_key}, 模板有Key: {template_has_key}, 最终需要Key: {requires_key_now}")
                company_models.append({
                    "name": model_name,
                    "requires_key": requires_key_now # 告诉前端这个模型当前是否需要用户输入 key
                })

            if company_models:
                models_structure.append({
                    "company": company_name,
                    "models": company_models
                })

        return jsonify(models_structure)

    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.error(f"读取模型或用户密钥配置文件失败: {e}")
        return jsonify({"error": "读取配置时出错"}), 500
    except Exception as e:
         logging.exception(f"构建模型列表时发生未知错误: {e}") # Use exception for stacktrace
         return jsonify({"error": "处理模型列表时出错"}), 500

# 保存 API Key (更新 user_keys 和活动 config)
@app.route('/api/save_api_key', methods=['POST'])
def save_api_key():
    data = request.json
    username = data.get('username')
    model_name = data.get('model_name')
    api_key = data.get('api_key') # 注意：前端传过来时可能是空字符串

    if not username or username != current_logged_in_user:
        return jsonify({"success": False, "error": "用户未登录或认证失败"}), 401
    if not model_name: # API Key 可以是空字符串，表示清除
        return jsonify({"success": False, "error": "缺少模型名称"}), 400
    # 不再检查 api_key 是否为空，允许用户保存空 key 以清除

    logging.info(f"用户 {username} 正在为模型 {model_name} 保存 API Key (长度: {len(api_key)})...")

    try:
        # 1. 更新 user_api_keys.json
        all_user_keys = load_user_keys()
        if username not in all_user_keys:
            all_user_keys[username] = {}
        all_user_keys[username][model_name] = api_key # 保存 key (可能是空字符串)
        save_user_keys(all_user_keys)
        logging.info(f"用户 {username} 的模型 {model_name} 的密钥已更新到 {USER_KEYS_PATH}。")

        # 2. 更新当前活动的 config.json
        # 不需要从模板重新合并，直接修改当前活动的即可
        try:
            with open(CONFIG_ACTIVE_PATH, 'r', encoding='utf-8') as f:
                current_active_config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, IOError) as e:
             logging.error(f"读取活动配置文件 {CONFIG_ACTIVE_PATH} 以更新密钥时失败: {e}")
             # 理论上活动配置文件应该存在，如果不存在则服务有问题
             return jsonify({"success": False, "error": "无法读取活动配置以应用新密钥"}), 500

        # 查找并更新活动配置中的密钥
        found_and_updated = False
        key_to_set = api_key if api_key else "xxx" # 如果用户保存空key，在config.json中写回占位符 "xxx"
        if 'services' in current_active_config:
            for service_type, service_list in current_active_config['services'].items():
                for i, service_instance in enumerate(service_list): # Need index to modify in place
                    if model_name in service_instance.get("models", []):
                        if "credentials" not in current_active_config['services'][service_type][i]:
                            current_active_config['services'][service_type][i]["credentials"] = {}
                        current_active_config['services'][service_type][i]["credentials"]["api_key"] = key_to_set
                        found_and_updated = True
                        logging.debug(f"在活动配置中更新了模型 {model_name} 的 Key。")
                        break # 假设一个服务实例共享一个 key
                if found_and_updated:
                    break

        if not found_and_updated:
            logging.error(f"尝试更新活动配置 {CONFIG_ACTIVE_PATH} 时未找到模型 {model_name}。配置可能已损坏或与 Mconfig 不一致。")
            return jsonify({"success": False, "error": f"配置错误：无法在活动配置中定位模型 '{model_name}'。"}), 500

        # 写回更新后的活动配置
        try:
            with open(CONFIG_ACTIVE_PATH, 'w', encoding='utf-8') as f:
                json.dump(current_active_config, f, indent=2, ensure_ascii=False)
            logging.info(f"活动配置文件 {CONFIG_ACTIVE_PATH} 已更新。")
        except IOError as e:
            logging.error(f"保存更新后的活动配置文件 {CONFIG_ACTIVE_PATH} 失败: {e}")
            return jsonify({"success": False, "error": "保存配置更新失败"}), 500

        # 3. 重启 API 服务
        logging.info("准备重启 simple-one-api 服务以应用更改...")
        restart_api_server()

        # 4. （可选）自动切换到该模型 
        if api_key: # 只有在提供了有效 key 时才自动切换
             global current_api
             found_api_identifier = None
             for api_id, mapped_model in MODEL_MAPPING.items():
                  if mapped_model == model_name:
                      found_api_identifier = api_id
                      break
             if found_api_identifier:
                  current_api = found_api_identifier
                  logging.info(f"API Key 保存成功，后端当前 API 自动切换为: {current_api} (模型: {model_name})")
             else:
                  logging.warning(f"保存 Key 后尝试自动切换，但未在 MODEL_MAPPING 中找到模型 {model_name} 对应的 API 标识符。")

        return jsonify({"success": True})

    except Exception as e:
        logging.exception(f"保存 API Key 时发生意外错误 (用户: {username}, 模型: {model_name}): {e}")
        return jsonify({"success": False, "error": "处理请求时发生内部服务器错误"}), 500

# 选择模型 (仅切换后端状态)
@app.route('/api/select_model', methods=['POST'])
def select_model():
    global current_api # 只需要修改 current_api
    data = request.json
    username = data.get('username')
    model_name = data.get('model_name')

    if not username or username != current_logged_in_user:
        return jsonify({"success": False, "error": "用户未登录或认证失败"}), 401
    if not model_name:
        return jsonify({"success": False, "error": "缺少模型名称"}), 400

    # 在 MODEL_MAPPING 中查找与 model_name 对应的 api 标识符
    found_api_identifier = None
    for api_identifier, mapped_model_name in MODEL_MAPPING.items():
        if mapped_model_name == model_name:
            found_api_identifier = api_identifier
            break

    if found_api_identifier:
        # 检查用户是否已为此模型提供 Key
        all_user_keys = load_user_keys()
        user_keys = all_user_keys.get(username, {})
        if model_name not in user_keys or not user_keys[model_name]:
             # 用户选择了模型，但尚未提供 key (理论上前端不应调用此接口，除非requires_key=false)
             logging.warning(f"用户 {username} 尝试选择模型 {model_name} 但尚未提供有效 Key。")
             # 允许切换，但前端应该阻止无 Key 调用
             # 或者返回错误？ return jsonify({"success": False, "error": f"模型 '{model_name}' 需要 API Key"}), 400
             # 决定允许切换，由发送消息时 ai_call 依赖的配置决定是否能成功
             pass # 允许切换，但后续调用可能失败

        current_api = found_api_identifier # 更新全局状态
        logging.info(f"用户 {username} 选择模型 {model_name}，后端 API 标识切换为: {current_api}")
        return jsonify({"success": True, "selected_api": current_api})
    else:
        logging.warning(f"用户 {username} 尝试选择未映射的模型: {model_name}")
        # 检查 Mconfig.json 是否包含该模型
        try:
            # 修正缩进
            with open(MCONFIG_PATH, 'r', encoding='utf-8') as f:
                mconfig = json.load(f)
            model_exists_in_mconfig = any(model_name in company_data.get("models", []) for company_data in mconfig.values())
            if model_exists_in_mconfig:
                # 模型在 Mconfig 中，但不在 MODEL_MAPPING 里，这是后端配置问题
                logging.error(f"模型 {model_name} 存在于 Mconfig.json 但未在 chatapp_new.py 的 MODEL_MAPPING 中定义！")
                return jsonify({"success": False, "error": f"服务器内部配置错误：模型 '{model_name}' 无法被后端处理。"}), 500
            else:
                # 模型根本没定义
                return jsonify({"success": False, "error": f"无效的模型名称: {model_name}"}), 400
        except Exception as e:
            # 修正缩进
            logging.error(f"检查模型映射时出错: {e}")
            return jsonify({"success": False, "error": "检查模型有效性时出错"}), 500




## 设置
@app.route('/api/setting')
def setting():
    topic = request.args.get('topic') # 从查询参数获取 topic
    request.args.get('topic')
    topic_to_file = {
            "userAgreement": "Userprivacy.txt",
            "userManual": "manual.txt"
        }
    filename = topic_to_file.get(topic)
    file_path = os.path.join(SETTING_DIR, filename)
    with open(file_path,'r',encoding = 'utf-8') as f:
        content = f.read()
        if not os.path.exists(file_path):
            logging.error(f"设置文件未找到: {file_path}")
            # 返回更具体的错误信息给前端
            return jsonify({"success": False, "error": f"请求的内容文件 '{filename}' 未找到"}), 404 # 返回 404 Not Found

    return jsonify({"success": True, "messages": content})

# 根路由 (不变)
@app.route('/')
def index():
    # 总是返回 chat.html，由前端 JS 决定显示登录还是主界面
    return send_from_directory('static', 'chat.html')

# 主程序入口 (修改 webview.start)
if __name__ == '__main__':
    import webview
    start_api_server() # <--- 在这里启动
    # 启动 Flask app (webview 会处理)
    logging.info("启动 Flask 应用和 webview 窗口...")
    window = webview.create_window('FLYINGPIG-AI', app, width=1000, height=700)

    webview.start(debug=False) # <-- 移除 storage_path

    # 清理 simple-one-api 进程 (当 webview 关闭时)
    if api_process and api_process.poll() is None: # 检查进程是否存在且在运行
        logging.info("Webview 关闭，正在尝试终止 simple-one-api 进程...")
        try:
            api_process.terminate()
            api_process.wait(timeout=5)
            logging.info("simple-one-api 进程已终止。")
        except subprocess.TimeoutExpired:
            if api_process.poll() is None: api_process.kill()
            logging.info("simple-one-api 进程已被强制结束。")
        except Exception as e:
             logging.warning(f"关闭时终止 simple-one-api 出错: {e}")