import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib import font_manager
import os
import platform

def get_chinese_font():
    """尝试获取系统中可用的中文字体"""
    system = platform.system()
    # 常见的字体路径列表
    font_paths = [
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", # Linux常用
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/mnt/c/Windows/Fonts/simhei.ttf", # WSL
        "C:/Windows/Fonts/simhei.ttf",     # Windows
        "/System/Library/Fonts/PingFang.ttc" # Mac
    ]
    
    for path in font_paths:
        if os.path.exists(path):
            try:
                return font_manager.FontProperties(fname=path)
            except:
                continue
    return None

def plot_heatmap(X_norm, regions, feature_names=None):
    """
    绘制特征矩阵热力图
    X_norm: 归一化后的矩阵
    regions: 地区列表 (纵轴)
    feature_names: 特征名列表 (横轴，可选)
    """
    my_font = get_chinese_font()
    
    # 地区名称简化字典 (根据您的需求)
    rename_dict = {
        "广州--湛江市产业转移合作园（湛江奋勇高新区）-湛江奋勇高新区": "广州--湛江市产业转移合作园",
        "湛江-麻章-湛江经济技术开发区东海岛": "湛江-麻章-经开区东海岛"
    }
    regions_short = [rename_dict.get(r, r) for r in regions]
    
    # 动态调整图片高度
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
        # y轴
        for label in ax.get_yticklabels():
            label.set_fontproperties(my_font)
        # x轴 (如果有中文)
        for label in ax.get_xticklabels():
            label.set_fontproperties(my_font)
            
    plt.yticks(rotation=0)
    plt.xticks(rotation=90)
    plt.tight_layout()
    
    return fig