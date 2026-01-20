import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib import font_manager
import os
from matplotlib.patches import Patch
import numpy as np
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
    h = max(10, len(regions) * 0.3)
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

def plot_category_radar_chart(category_feature_attention_expert):
    """
    绘制类别特征注意力雷达图 (适配 Streamlit)
    Input: DataFrame (行=特征, 列=类别)
    """
    my_font = get_chinese_font()
    n_clusters = category_feature_attention_expert.shape[1]
    
    # 计算行列
    n_cols = 3
    n_rows = (n_clusters + n_cols - 1) // n_cols

    # 创建 Figure
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(18, 5*n_rows),
                             subplot_kw=dict(projection='polar'))
    
    title_font = my_font.copy()
    title_font.set_size(16)
    title_font.set_weight('bold')
    
    plt.suptitle('各类别主要关注特征雷达图', fontproperties=title_font, y=1.02)
    
    if n_rows == 1 and n_cols == 1: axes = np.array([[axes]])
    elif n_rows == 1: axes = axes.reshape(1, -1)
    elif n_cols == 1: axes = axes.reshape(-1, 1)

    colors = plt.cm.Set3(np.linspace(0, 1, n_clusters))

    for k in range(n_clusters):
        row = k // n_cols
        col = k % n_cols
        ax = axes[row, col]

        # 获取当前类别的前8个特征
        top_features = category_feature_attention_expert.iloc[:, k].sort_values(ascending=False).head(8)
        features = top_features.index.tolist()
        values = top_features.values.tolist()

        if not features: continue

        # 数据闭合
        angles = np.linspace(0, 2*np.pi, len(features), endpoint=False).tolist()
        values += values[:1]
        angles += angles[:1]

        ax.plot(angles, values, 'o-', linewidth=2, color=colors[k], label=f'类别 {k+1}')
        ax.fill(angles, values, alpha=0.25, color=colors[k])

        ax.set_xticks(angles[:-1])
        feature_labels = [f'{feat[:10]}..' if len(feat)>10 else feat for feat in features]
        ax.set_xticklabels(feature_labels, fontproperties=my_font, fontsize=9)

        if values:
            ax.set_ylim(0, max(values) * 1.2)
            ax.set_yticks(np.linspace(0, max(values), 4))
        
        ax.grid(True, alpha=0.3)
        ax.set_title(f'类别 {k+1} 特征画像', fontproperties=my_font, fontsize=12, pad=15)

    # 隐藏多余子图
    for k in range(n_clusters, n_rows * n_cols):
        row = k // n_cols
        col = k % n_cols
        axes[row, col].set_visible(False)

    plt.tight_layout()
    return fig  # 返回对象供 st.pyplot 使用

# === 2. 修改后的条形图函数 ===
def plot_horizontal_bars_from_df(df_result, my_font=None):
    """
    直接从 DataFrame 绘制 (不再需要读取 Excel)
    df_result: 必须包含 'Top1_Cluster', 'Top1_Prob' 等列
    """
    if my_font is None:
        my_font = get_chinese_font()

    # 构造绘图数据字典
    data_dict = {}
    # 假设索引是地区名
    for region_name, row in df_result.iterrows():
        # 兼容处理：如果是 Excel 读取的可能是字符串，如果是 DataFrame 直接是数值
        # 这里假设已经是数值
        data_dict[region_name] = [
            (row['Top1_Cluster'], row['Top1_Prob']),
            (row['Top2_Cluster'], row['Top2_Prob']),
            (row['Top3_Cluster'], row['Top3_Prob'])
        ]

    num_regions = len(data_dict)
    # 动态调整高度
    fig_height = max(6, num_regions * 0.6)
    fig, ax = plt.subplots(figsize=(12, fig_height))

    all_categories = sorted(set([c for v in data_dict.values() for c, p in v]))
    
    # 颜色映射
    base_colors = plt.cm.tab20.colors # 使用 matplotlib 内置色板
    category_colors = {cls: base_colors[i % len(base_colors)] for i, cls in enumerate(all_categories)}

    bar_height = 0.25
    region_space = 1.0
    
    regions = list(data_dict.keys())
    # 倒序遍历，让第一个地区显示在最上面
    for i, region in enumerate(reversed(regions)):
        values = data_dict[region]
        y_pos = i * region_space
        
        for rank, (cls, prob) in enumerate(values):
            color = category_colors.get(cls, '#7f7f7f')
            alpha = 1.0 - (rank * 0.3) # 排名越靠后越透明
            
            ax.barh(y_pos + (2-rank)*bar_height, prob, height=bar_height, 
                    color=color, alpha=alpha, edgecolor='white')
            
            # 显示数值
            ax.text(prob + 0.01, y_pos + (2-rank)*bar_height, f"{prob:.1%}", 
                    va='center', fontsize=8, fontproperties=my_font)

    # 设置 Y 轴标签
    ax.set_yticks([i * region_space + bar_height for i in range(num_regions)])
    ax.set_yticklabels(reversed(regions), fontproperties=my_font)
    
    ax.set_xlabel('属于该类别的概率', fontproperties=my_font)
    ax.set_title('各地区 Top3 聚类匹配度', fontproperties=my_font, fontsize=14)
    ax.grid(axis='x', linestyle='--', alpha=0.3)
    
    # 图例
    legend_elements = [Patch(facecolor=category_colors[c], label=f'类别 {c}') for c in all_categories]
    ax.legend(handles=legend_elements, loc='upper center', bbox_to_anchor=(0.5, -0.05), 
              ncol=min(5, len(all_categories)), prop=my_font)

    plt.tight_layout()
    return fig


def plot_clusters(X_pca, labels, region_names, my_font=None):
    """
    绘制 PCA 聚类散点图
    ----------
    X_pca: 降维后的 2D 坐标 (n_samples, 2)
    labels: 聚类标签 (n_samples,)
    region_names: 地区名称列表 (n_samples,)
    my_font: 字体属性 (可选)
    """
    # 1. 获取字体
    if my_font is None:
        # 假设 get_chinese_font 已经在上下文定义过
        my_font = get_chinese_font()

    # 2. 创建画布
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # 3. 获取唯一的聚类标签
    unique_labels = np.unique(labels)
    
    # 4. 生成颜色映射
    colors = plt.cm.tab10(np.linspace(0, 1, len(unique_labels)))
    
    # 5. 循环绘制每一类
    for i, label in enumerate(unique_labels):
        # 筛选出属于当前类别的点
        mask = (labels == label)
        
        # 绘制散点
        ax.scatter(
            X_pca[mask, 0], 
            X_pca[mask, 1], 
            c=[colors[i]], 
            label=f'类别 {label+1}', 
            s=100, 
            alpha=0.7, 
            edgecolors='w'
        )
        
        # (可选) 给每个点标上地区名字
        # 为了防止文字太密集，可以只标一部分，或者把字体设小一点
        for x, y, name in zip(X_pca[mask, 0], X_pca[mask, 1], region_names[mask]):
            ax.text(
                x, y+0.02, 
                name, 
                fontsize=8, 
                ha='center', 
                va='bottom', 
                fontproperties=my_font,
                alpha=0.8
            )

    # 6. 设置图表装饰
    ax.set_title('项目地区聚类分布 (PCA降维)', fontproperties=my_font, fontsize=16)
    ax.set_xlabel('Principal Component 1', fontsize=10)
    ax.set_ylabel('Principal Component 2', fontsize=10)
    ax.grid(True, linestyle='--', alpha=0.3)
    
    # 7. 添加图例
    ax.legend(title="聚类类别", prop=my_font, title_fontproperties=my_font)
    
    plt.tight_layout()
    return fig