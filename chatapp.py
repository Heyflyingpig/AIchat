from tkinter import * # 和import tk的区别是，这样不用在后续申明tkinter
from tkinter import messagebox
from zhipuai import ZhipuAI
from openai import OpenAI
import time
import csv
import os
import requests
import json

# 创建全局变量，用于申明不同的ai，和初始温度
current_api = "zhipuai"
temperature = 1.0

### 定义主函数
def printget(event = None):
    user_input = search_message.get("1.0", END)
    if user_input:
        # 设置标签样式
        display_text.tag_config("right", justify='right',font = ("黑体", 15)) # 利用tag_config控件来进行右对齐
        display_text.tag_config("left", justify='left',font = ("黑体", 15))    # 左对齐left标签
        
        display_text.config(state=NORMAL)
        display_text.insert(END, f"You: {user_input}\n","right") # 将用户输入的代码显示在对话框内，end表示在末尾插入字符
        display_text.config(state=DISABLED)
        
        if current_api == "zhipuai":
            ai_response = zhipuai(user_input)
        elif current_api == "aliyunai":
            ai_response = aliyun(user_input)
            print(f"当前api是：{current_api}")
        elif current_api == "deepseek":
            ai_response = deepseek(user_input,temperature)
            print(f"当前api是：{current_api}")
        display_text.config(state=NORMAL)
        display_text.insert(END, f"AI: {ai_response}\n\n", "left")
        display_text.config(state=DISABLED)

        # 保存对话
        save_chat(user_input,ai_response)

         # 清空输入框
        search_message.delete("1.0", END) # 从索引0开始清除到end位置

### 调用质谱api
def zhipuai(text):
    credentials_file_path = 'zhipu_secret.txt'
    # 初始化字典来存储密钥
    credentials = {}
    # 读取文件并解析密钥
    with open(credentials_file_path, 'r') as file:
        for line in file:
            # 去除换行符和空格
            line = line.strip()
            # 检查是否为空行或注释行（以#开头）
            if not line or line.startswith('#'):
                continue
                # 分割键和值
            key, value = line.split('=', 1)
            # 存储到字典中
            credentials[key] = value
    client = ZhipuAI(api_key=credentials.get('zhipu_API')) 
    response = client.chat.completions.create(
                model="glm-4-flash",
                messages=[{"role": "user", "content": text}]
            )
    airesponse = response.choices[0].message.content
    return airesponse

### 调用阿里云api
def aliyun(text):
    credentials_file_path = 'aliyun_secret.txt'
    credentials = {}
    with open(credentials_file_path, 'r') as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, value = line.split('=', 1)
            credentials[key] = value

    API_KEY = credentials.get('ALIYUN_API_KEY')
    url = "https://api.siliconflow.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }   
    payload = {
                "messages": [{"role": "user", "content": text}],
                "model": "Qwen/Qwen2.5-7B-Instruct"
            }
    response = requests.request("POST", url, json=payload, headers=headers)   
    response_json = json.loads(response.text)  # 解析JSON响应
    answer = response_json['choices'][0]['message']['content']  # 获取content内容
    return answer
    
    ### 保存文件

## deepseek
def deepseek(text,tem): 
    credentials_file_path = 'deepseek_secret.txt'
    credentials = {}
    with open(credentials_file_path, 'r') as file:
        for line in file:
            line = line.strip()
            key, value = line.split('=', 1)
            credentials[key] = value

    API_KEY = credentials.get('DEEPSEEKAPI')
    client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com")

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": text},
        ],
        stream=False,
        temperature=tem
        
    )

    answer = response.choices[0].message.content
    return answer

### 转换api函数
def switch_api(api):
    global current_api
    current_api = api
    messagebox.showinfo("提示", f"API 切换成功！当前使用 {api}")

### 更改模型温度
def switch_tem():
    def set_temperature():
        global temperature
        try:
            new_temp = float(tembox.get())
            if 0 <= new_temp <= 2:
                temperature = new_temp
                messagebox.showinfo("提示", f"当前温度设置为 {temperature}")
                tembox.destroy()
            else:
                messagebox.showerror("错误", "请输入 0 - 2 之间的值！")
        except ValueError:
            messagebox.showerror("错误", "请输入数字！")
    
    # 创建新窗口
    temperature_window = Toplevel(root)
    temperature_window.title("更改模型温度")
    temperature_window.geometry("300x150")
    
    # 设置温度调节控件
    tem_var = StringVar()
    tem_label = Label(temperature_window, text="设置模型温度（0-2）：")
    tem_label.pack(pady=10)
    
    # 设置温度spinbox空间，调整温度
    tembox = Spinbox(temperature_window,from_=0,to=2,increment=0.1,textvariable=tem_var)
    tembox.pack(pady=10)
    tembox.delete(0, END) # 清除框内值
    tembox.insert(0, temperature) # 在框内插入当前温度
    
    confirm_button = Button(temperature_window, text="确认", command=set_temperature)
    confirm_button.pack(pady=10)
     
    

### 保存文件
def save_chat(message,response):
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S") # 保存时间
    with open("chat_history.csv", mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file) # 写入文件
        writer.writerow(["User", message, timestamp])
        writer.writerow(["AI", response, timestamp])

# 加载文件
def load_chat():
    history = []
    if os.path.exists("chat_history.csv"):
        with open("chat_history.csv", mode="r", encoding="utf-8") as file:
            reader = csv.reader(file) # 读取文件
            history = list(reader)
    return history

# 窗口历史函数
def display_history():
    history = load_chat()
    display_text.config(state=NORMAL) # 打开编辑状态
    display_text.delete(1.0,END) # 清除所有内容
    for i in range(0, len(history), 2):  
        user_msg = history[i]  
        ai_msg = history[i+1]  
        
        display_text.insert(END, f"{user_msg[2]}\n{user_msg[0]}: {user_msg[1]}\n", "right")  
        display_text.insert(END, f"{ai_msg[2]}\n{ai_msg[0]}: {ai_msg[1]}\n\n", "left")  
    display_text.config(state=DISABLED)  # 将文本部件的编辑状态设置为只读（禁用状态）

# 新建新对话
def create_new_chat():
    display_text.config(state=NORMAL)
    display_text.delete(1.0, END)
    display_text.config(state=DISABLED)

### 创建窗口
root = Tk() # root意思是主窗口，可以改变
root.geometry("1000x600") # 创建窗口
root.title("FLYINGPIGAI")
# root.iconbitmap 改变标题的icon

## 创建菜单栏
menubar = Menu(root)
root.config(menu=menubar)

## 创建设置菜单
setting_menu = Menu(menubar, tearoff=0)  ## tearoff用于是否可将该选项独立出来
menubar.add_cascade(label="设置", menu=setting_menu)

# 创建切换 AI 子菜单
api_submenu = Menu(setting_menu, tearoff=0)
api_submenu.add_command(label="切换为质谱 AI", command=lambda: switch_api("zhipuai"))
api_submenu.add_command(label="切换为阿里云 AI", command=lambda: switch_api("aliyunai"))
api_submenu.add_command(label="切换为 Deepseek", command=lambda: switch_api("deepseek"))

# 添加切换 AI 菜单项（父菜单）
setting_menu.add_cascade(label="切换 API", menu=api_submenu )
setting_menu.add_cascade(label="更改模型温度",command=switch_tem )

## 创建功能菜单
function_menu = Menu(menubar, tearoff=0)
menubar.add_cascade(label="功能", menu=function_menu)
function_menu.add_command(label="查看历史", command=display_history)
function_menu.add_command(label="新建对话", command=create_new_chat)

### 创建头顶文本框
lab = Label(root,text = "FLYINGPIG-AI", font=("华文中宋",25)) # root主窗口，relief窗口形态
lab.pack() # 将lable放置在窗口上


# basicframe新建一个顶部框架
basicframe = Frame(root,)
basicframe.pack(side = TOP,fill = X)


### 创建对话显示框
display_frame = Frame(root)
display_frame.pack(fill=BOTH, expand=True) # 自适应窗口
display_text = Text(display_frame, wrap=WORD, state=DISABLED) #换行按照完整的单词进行换行，禁止用户编辑对话框内容
display_text.pack(side=LEFT, fill=BOTH, expand=True)
scrollbar = Scrollbar(display_frame, command=display_text.yview) # 创建一个滚动条
scrollbar.pack(side=RIGHT, fill=Y) # 垂直方向填充对话框
display_text.config(yscrollcommand=scrollbar.set)

### 创建框架,用于整理发送框，发送键
search_model = Frame(root)
search_model.pack(side=BOTTOM,fill = X,)        

### 创建一个文本框
search_message = Text(search_model, height = 5)
search_message.pack(side=LEFT, fill=X, expand = True,padx=5, pady=5)


### 创建发送按钮
searchbutton = Button(search_model,text="发送",activeforeground="white", activebackground="blue",command=printget)
searchbutton.pack(side=RIGHT, padx=10, pady=5) #设置与父控件的间距

# 绑定回车键事件
search_message.bind('<Return>', printget) 


mainloop() # 循环重复窗口
