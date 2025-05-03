# 技术说明：前后端 API Key 处理逻辑

本文档详细说明了 Chatapp 应用中处理模型 API Key 的前后端交互流程。

## 核心目标

允许用户安全地提供、保存和使用需要 API Key 的 AI 模型。

## 关键组件与文件

**后端 (`chatapp_new.py` 及相关)**

*   **`Mconfig.json`**: 模型元数据。定义了服务提供商及其提供的模型名称列表（模型目录）。
    *   作用：让后端知道哪些模型是理论上存在的。
*   **`user_api_keys.json`**: 用户密钥存储（JSON）。存储每个用户为特定模型提供的 API Key。
    *   结构: `{ "username": { "model_name1": "key1", ... }, ... }`
    *   作用：持久化存储用户输入的密钥。
*   **`config_template.json`**: `simple-one-api` 的配置模板。包含基础结构和可能的默认值/占位符。
    *   作用：作为生成活动配置的基础。
*   **`simple-one-api/config.json`**: 活动配置文件。这是 `simple-one-api.exe` 运行时**实际读取**的配置文件，包含调用模型所需的认证信息（API Key）。
    *   作用：为底层 API 服务提供认证凭据。
    *   **动态生成**: 其内容基于 `config_template.json` 和当前登录用户的 `user_api_keys.json` 中的数据合并而成。
*   **`Uconfig.json`**: 存储 UI 状态，主要是当前登录的用户名 (`logged_in_user`)。
*   **`chatapp_new.py`**: Flask 应用逻辑。
    *   `current_api` (全局变量): 存储当前选定的 API *标识符* (如 "zhipuai")，用于 `ai_call` 决定调用哪个模型。
    *   `MODEL_MAPPING` (全局字典): 将 API 标识符映射到具体的模型名称 (如 "zhipuai" -> "glm-4-flash")，供 `ai_call` 使用。
    *   `api_process` (全局变量): 运行中的 `simple-one-api.exe` 进程句柄。
    *   相关 API 端点: `/api/login`, `/api/logout`, `/api/get_models`, `/api/save_api_key`, `/api/select_model`, `/api/send`。
    *   辅助函数: `load/save_user_keys`, `merge_config_with_user_keys`, `apply_default_config`, `start/restart_api_server`, `ai_call`。

**前端 (`chat.html`)**

*   **`#modelSelector`**: 模型选择下拉菜单。
    *   `<option>` 元素存储 `value` (模型名称) 和 `dataset.requiresKey` (布尔值，表示当前用户是否需要为此模型输入 Key)。
*   **`#apiKeyModal`**: API Key 输入弹窗。
*   **JavaScript 函数**: `loadModels`, `showApiKeyModal`, `submitApiKey`, `selectModelFrontend`, `sendMessage` 等。

## 核心流程

### 1. 获取模型列表 (Login/Page Load)

1.  **FE**: 登录成功后调用 `loadModels()`，向 `/api/get_models?user=<username>` 发送请求。
2.  **BE (`/api/get_models`)**:
    *   读取 `Mconfig.json` (所有模型) 和 `user_api_keys.json` (当前用户 Key)。
    *   对每个模型，检查用户是否已提供 Key，设置 `requires_key` 标志。
    *   返回包含模型列表（含 `requires_key`）的 JSON。
3.  **FE (`loadModels()` 回调)**:
    *   解析 JSON，填充 `#modelSelector`。
    *   为每个 `<option>` 设置 `value` 和 `dataset.requiresKey`。

### 2. 用户选择模型

1.  **FE**: 用户在 `#modelSelector` 选择模型，触发 `change` 事件。
2.  **FE**: 检查选中 `<option>` 的 `dataset.requiresKey`。
    *   **If `true`**: 调用 `showApiKeyModal(modelName)` 显示弹窗。
    *   **If `false`**: 调用 `selectModelFrontend(modelName)`。
3.  **FE (`selectModelFrontend`)**: 向 `/api/select_model` 发送 POST 请求 (username, model_name)。
4.  **BE (`/api/select_model`)**:
    *   根据 `model_name` 查找 `MODEL_MAPPING` 中的 API 标识符。
    *   **更新全局变量 `current_api`**。
    *   *不修改文件，不重启服务*。
    *   返回成功。

### 3. 用户提交 API Key

1.  **FE**: 用户在 `#apiKeyModal` 输入 Key，点击确定，触发 `submitApiKey()`。
2.  **FE (`submitApiKey`)**:
    *   显示加载指示器。
    *   向 `/api/save_api_key` 发送 POST 请求 (username, model_name, api_key)。
    *   隐藏弹窗。
3.  **BE (`/api/save_api_key`)**:
    *   **更新 `user_api_keys.json`**: 保存用户的 Key。
    *   **更新 `simple-one-api/config.json`**: 读取活动配置，找到对应模型，修改 `api_key`，写回文件。
    *   **调用 `restart_api_server()`**: 终止旧进程，启动新进程以加载新配置。
    *   **(可选) 更新全局变量 `current_api`**: 如果 Key 有效，可自动切换到该模型。
    *   返回成功。
4.  **FE (`submitApiKey()` 回调)**:
    *   隐藏加载指示器。
    *   显示成功消息。
    *   **更新 `#modelSelector` 中对应 `<option>` 的 `dataset.requiresKey = false`**。

### 4. 发送消息 (使用 Key)

1.  **FE (`sendMessage`)**: 向 `/api/send` 发送 POST 请求 (message, username)。
2.  **BE (`/api/send`)**: 调用 `ai_call(message)`。
3.  **BE (`ai_call`)**:
    *   获取全局 `current_api` 标识符。
    *   用 `MODEL_MAPPING` 获取模型名称。
    *   向 `http://localhost:9090/v1` (simple-one-api) 发送请求。
4.  **simple-one-api**:
    *   接收请求。
    *   **读取自身的 `config.json`**，找到对应模型的 Key。
    *   使用该 Key 调用外部 AI 服务。
    *   返回结果。
5.  **BE/FE**: 响应传回前端显示。

### 5. 用户登出

1.  **FE (`handleLogout`)**: 向 `/api/logout` 发送 POST 请求。
2.  **BE (`/api/logout`)**:
    *   清除登录状态 (`current_logged_in_user`, `Uconfig.json`)。
    *   **调用 `apply_default_config()`**: 用模板覆盖 `simple-one-api/config.json`。
    *   **调用 `restart_api_server()`**: 应用默认配置。
    *   返回成功。
3.  **FE**: 清理 UI，显示登录页。

## 总结

系统通过分离模型定义 (`Mconfig`), 用户密钥存储 (`user_api_keys`), 和运行时配置 (`simple-one-api/config.json`) 来管理 API Key。后端通过全局变量 (`current_api`) 控制当前对话使用的模型，并通过动态生成配置文件和重启 `simple-one-api` 服务来应用用户提供的密钥。前端负责根据后端提供的状态 (`requires_key`) 决定是否提示用户输入，并在用户提交后更新自身状态。