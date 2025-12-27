import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib import font_manager
import os
import platform
import requests  # 需要确保 requirements.txt 中有 requests

def get_chinese_font():
    """
    获取中文字体。
    逻辑：
    1. 检查当前目录下是否有 simhei.ttf
    2. 如果没有，尝试从网络下载 (确保云端可用)
    3. 如果下载失败，尝试查找系统常见字体路径
    """
    font_name = "simhei.ttf"
    # 获取当前文件所在目录，确保字体存在项目里
    current_dir = os.path.dirname(os.path.abspath(__file__))
    local_font_path = os.path.join(current_dir, font_name)

    # 1. 检查本地是否存在
    if os.path.exists(local_font_path):
        return font_manager.FontProperties(fname=local_font_path)

    # 2. 尝试下载 (使用 GitHub 镜像源或其他稳定源)
    print(f"未找到本地字体，正在尝试下载 {font_name} ...")
    url = "https://github.com/StellarCN/scp_zh/raw/master/fonts/SimHei.ttf"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            with open(local_font_path, "wb") as f:
                f.write(response.content)
            print("✅ 字体下载成功！")
            return font_manager.FontProperties(fname=local_font_path)
    except Exception as e:
        print(f"❌ 字体下载失败: {e}")

    # 3. 最后的兜底：尝试系统路径 (WSL, Mac, Linux apt)
    system_font_paths = [
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # Linux 常见开源字体
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/mnt/c/Windows/Fonts/simhei.ttf", # WSL
        "C:/Windows/Fonts/simhei.ttf",     # Windows
        "/System/Library/Fonts/PingFang.ttc" # Mac
    ]
    
    for path in system_font_paths:
        if os.path.exists(path):
            return font_manager.FontProperties(fname=path)
            
    print("⚠️ 警告：未找到任何中文字体，中文可能显示为乱码。")
    return None

def plot_heatmap(X_norm, regions, feature_names=None):
    """
    绘制特征矩阵热力图
    X_norm: 归一化后的矩阵
    regions: 地区列表 (纵轴)
    feature_names: 特征名列表 (横轴，可选)
    """
    my_font = get_chinese_font()
    
    # 地区名称简化字典
    rename_dict = {
        "广州--湛江市产业转移合作园（湛江奋勇高新区）-湛江奋勇高新区": "广州--湛江市产业转移合作园",
        "湛江-麻章-湛江经济技术开发区东海岛": "湛江-麻章-经开区东海岛"
    }
    regions_short = [rename_dict.get(r, r) for r in regions]
    
    # 动态调整图片高度
    # 至少 10，每个地区增加 0.4 高度
    h = max(10, len(regions) * 0.4)
    fig, ax = plt.subplots(figsize=(12, h))
    
    # 如果没有特征名，用数字代替
    xticklabels = feature_names if feature_names else [str(i) for i in range(X_norm.shape[1])]
    
    sns.heatmap(
        X_norm, 
        cmap='Reds', 
        yticklabels=regions_short,
        xticklabels=xticklabels,
        linewidths=0.05,
        ax=ax
    )
    
    # 设置字体
    if my_font:
        ax.set_xlabel('特征', fontproperties=my_font, fontsize=14)
        ax.set_ylabel('地区', fontproperties=my_font, fontsize=14)
        ax.set_title('多源数据融合特征热力图 (归一化后)', fontproperties=my_font, fontsize=16)
        
        # 调整轴标签字体
        # y轴 (地区名)
        plt.setp(ax.get_yticklabels(), fontproperties=my_font)
        # x轴 (特征名)
        plt.setp(ax.get_xticklabels(), fontproperties=my_font)
            
    plt.yticks(rotation=0)
    plt.xticks(rotation=90)
    plt.tight_layout()
    
    return fig