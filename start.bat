    @echo off
    echo Checking for Python virtual environment (venv)...

    REM 检查venv目录是否存在
    if not exist venv (
        echo Creating virtual environment in 'venv' folder...
        python -m venv venv
        if %errorlevel% neq 0 (
            echo Failed to create virtual environment. Please ensure Python is installed and added to PATH.
            pause
            exit /b 1
        )
    )

    echo Activating virtual environment...
    call venv\Scripts\activate.bat

    echo Installing required packages from requirements.txt...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo Failed to install packages. Please check your internet connection and requirements.txt.
        pause
        exit /b 1
    )

    echo Starting the FPChatbox application...
    python chatapp_new.py

    echo Application closed. Deactivating virtual environment (optional)...
    REM deactivate automatically happens when script exits

    pause