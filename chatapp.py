from tkinter import * # 和import tk的区别是，这样不用在后续申明tkinter
from tkinter import messagebox
from zhipuai import ZhipuAI
import time
import csv
import os
import requests
import json

# 创建全局变量，用于申明不同的ai
current_api = "zhipuai"

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


# 窗口函数，点击设置出现窗口
def show_setting_windows():
    setting_windows = Toplevel(root) #新建
    setting_windows.title("设置")
    setting_windows.geometry("200x200")
    
    setting_list = Listbox(setting_windows,height = 10,selectmode=SINGLE)
    setting_list.insert(1, "切换质谱AI")
    setting_list.insert(2,"切换阿里云AI")
    setting_list.insert(3, "其他设置")
    setting_list.pack( padx=3, pady=3)
    
    
# 设置选项函数
    def setting_select(event): #event用于传进上面的函数
        global current_api
        selection_index = setting_list.curselection() # 返回选项索引
        if selection_index:
            option = setting_list.get(selection_index)
            print(f"Selected option: {option}")
            if option == "切换质谱API":
                current_api = "zhipuai"
                messagebox.showinfo("提示", "API切换成功！当前使用质谱ai")  # 弹出提示框
            elif option == "切换阿里云AI":
                current_api = "aliyunai"
                messagebox.showinfo("提示", "API切换成功！当前使用阿里云")
    ########未完成

    setting_list.bind("<<ListboxSelect>>", setting_select) # 被选择时

### 创建窗口
root = Tk() # root意思是主窗口，可以改变
root.geometry("1000x600") # 创建窗口
root.title("FLYINGPIGAI")
# root.iconbitmap 改变标题的icon

### 创建头顶文本框
lab = Label(root,text = "FLYINGPIG-AI", font=("华文中宋",25)) # root主窗口，relief窗口形态
lab.pack() # 将lable放置在窗口上


# basicframe新建一个顶部框架
basicframe = Frame(root,)
basicframe.pack(side = TOP,fill = X)

# 设置按钮
settingbutton = Button(basicframe,text="设置",relief = "groove", font=("黑体",15,"bold"),command=show_setting_windows)
settingbutton.pack(side = LEFT,padx=5,pady = 5)



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

# 创建历史和新建对话框功能
expandframe = Frame(root)
expandframe.pack(side = LEFT)

historybotton = Button(expandframe,text="查看历史",width= 15,command=display_history)
historybotton.pack(side=LEFT,padx = 5,pady = 5)
createbotton = Button(expandframe,text="新建对话",width= 15,command=create_new_chat)
createbotton.pack(side=RIGHT,padx = 5,pady = 5)


mainloop() # 循环重复窗口
