import streamlit as st
import base64
import os

def get_base64_of_bin_file(bin_file):
    """读取图片文件并转换为 base64 字符串"""
    try:
        with open(bin_file, 'rb') as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except FileNotFoundError:
        return ""

def set_bg_hack(main_bg):
    """设置全屏背景图和登录框样式"""
    # 替换为你实际的背景图片路径，如果图片在同目录下直接写文件名
    # 这里为了演示，如果没有图片，我会用 CSS 渐变代替
    if os.path.exists(main_bg):
        bin_str = get_base64_of_bin_file(main_bg)
        bg_img_style = f"""
            background-image: url("data:image/png;base64,{bin_str}");
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
        """
    else:
        # 如果找不到图片，使用类似截图的绿色/蓝色渐变背景
        bg_img_style = """
            background: linear-gradient(135deg, #76b852 10%, #8DC26F 100%);
        """

    st.markdown(
        f"""
        <style>
        /* 1. 隐藏 Streamlit 默认的顶部 Header 和 底部 Footer */
        header {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        #MainMenu {{visibility: hidden;}}
        
        /* 2. 设置全屏背景 */
        .stApp {{
            {bg_img_style}
        }}

        /* 3. 登录卡片容器样式 */
        /* 通过 data-testid 定位主要的 block */
        [data-testid="stVerticalBlock"] > [style*="flex-direction: column;"] > [data-testid="stVerticalBlock"] {{
            background-color: rgba(255, 255, 255, 0.95);
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
            max-width: 500px;  /* 限制卡片宽度 */
            margin: auto;      /* 居中 */
        }}

        /* 4. 输入框样式微调 */
        .stTextInput > div > div > input {{
            border-radius: 5px;
            border: 1px solid #ddd;
            padding: 10px;
        }}

        /* 5. 登录按钮样式 (模仿截图中的青蓝色) */
        .stButton > button {{
            background-color: #00bfa5; /* 青绿色 */
            color: white;
            border: none;
            border-radius: 5px;
            padding: 10px 20px;
            width: 100%;
            font-size: 16px;
            font-weight: bold;
        }}
        .stButton > button:hover {{
            background-color: #008f7a;
            color: white;
            border: none;
        }}

        /* 6. 标题和Logo样式 */
        .login-title {{
            text-align: center;
            font-size: 24px;
            font-weight: bold;
            color: #333;
            margin-bottom: 5px;
            font-family: "Microsoft YaHei", sans-serif;
        }}
        .login-subtitle {{
            text-align: center;
            font-size: 12px;
            color: #999;
            margin-bottom: 30px;
            letter-spacing: 1px;
        }}
        .logo-img {{
            display: block;
            margin-left: auto;
            margin-right: auto;
            width: 80px;
            margin-bottom: 20px;
        }}
        
        /* 7. 验证码样式模拟 */
        .captcha-text {{
            font-family: 'Courier New', monospace;
            font-weight: bold;
            font-size: 20px;
            letter-spacing: 5px;
            color: #ff5722;
            padding-top: 10px;
        }}
        
        /* 8. 底部警告文字 */
        .footer-warning {{
            text-align: center;
            color: #d32f2f;
            font-size: 14px;
            margin-top: 20px;
            font-weight: bold;
            text-shadow: 1px 1px 2px white;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )