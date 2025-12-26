import numpy as np
import pandas as pd

def _to_region2idx(mp):
    if not mp: return {}
    first_key = next(iter(mp))
    if isinstance(first_key, int): return {v: k for k, v in mp.items()}
    return mp

def unify_and_concatenate(matrices, maps, names=None):
    """多源异构数据融合"""
    if len(matrices) == 0: return [], np.array([]), []

    region2idx_list = [_to_region2idx(mp) for mp in maps]
    key_sets = [set(r2i.keys()) for r2i in region2idx_list]
    
    # 取交集
    common_regions_set = set.intersection(*key_sets)
    if not common_regions_set: return [], np.array([]), []

    # 排序
    first_r2i = region2idx_list[0]
    sorted_regions = sorted(list(common_regions_set), key=lambda r: first_r2i.get(r, 999999))

    # 拼接
    X_rows = []
    for r in sorted_regions:
        parts = []
        for mat, r2i in zip(matrices, region2idx_list):
            idx = r2i[r]
            parts.append(mat[idx])
        X_rows.append(np.concatenate(parts))
    
    X_final = np.vstack(X_rows)

    # 生成切片说明
    widths = [m.shape[1] for m in matrices]
    cum = np.cumsum([0] + widths)
    if names is None: names = [f"Block_{i}" for i in range(len(matrices))]
    slices = [{"name": names[i], "start": int(cum[i]), "end": int(cum[i+1])} for i in range(len(widths))]

    return sorted_regions, X_final, slices

def preprocess_X(X, eps=1e-8):
    """
    预处理函数：
    - 面积列：Min-Max归一化
    - 金额列：Min-Max归一化
    - 数量列：Min-Max归一化
    - 布尔列：缩放到 [0, 0.5]
    
    注意：这里的列索引是硬编码的，假设输入的 X 严格按照特定的特征顺序排列。
    如果特征顺序变化，索引需要相应调整。
    """
    # 确保输入是numpy数组
    if not isinstance(X, np.ndarray):
        X = np.array(X, dtype=np.float64)
    
    X_norm = np.zeros_like(X, dtype=np.float64)
    
    # === 列索引定义 (根据您的需求硬编码) ===
    # 假设 X 的总列数至少为 54 列
    # 1. 面积相关
    # 0-3 (自然资源), 4-23 (潜力), 23-27 (空间), 34,37... (子项目面积)
    area_potential_idx = list(range(4, 23))          # 4-22 (共19列)
    area_spatial_idx = list(range(23, 27))           # 23-26 (共4列)
    area_specific_idx = [34, 37, 40, 43, 46, 49, 52] # 子项目面积列
    
    area_idx = list(range(0, 3)) + area_potential_idx + area_spatial_idx + area_specific_idx
    
    # 2. 金额相关
    money_idx = [35, 38, 41, 44, 47, 50, 53]
    
    # 3. 数量相关
    count_idx = [33, 36, 39, 42, 45, 48, 51]
    
    # 4. 布尔/打分相关
    # 3 (林地占比?), 27 (打分), 28-32 (存在问题)
    # 修正：您原来的代码中 bool_idx = [3] + list(range(27, 31)) 可能有误
    # 根据您提供的 feature_groups，存在问题是 5 个 (28, 29, 30, 31, 32)
    # 规划打分是 27
    bool_idx = [3] + list(range(28, 33)) # 包含存在问题的5列
    score_idx = [27]
    
    # === 归一化处理 ===
    
    # 1. 面积、金额、数量 (Min-Max)
    for indices in [area_idx, money_idx, count_idx]:
        # 过滤掉越界的索引 (防止 X 列数不够)
        valid_idx = [i for i in indices if i < X.shape[1]]
        if not valid_idx: continue
        
        for col in valid_idx:
            vals = X[:, col]
            vmin, vmax = vals.min(), vals.max()
            if (vmax - vmin) > eps:
                X_norm[:, col] = (vals - vmin) / (vmax - vmin)
            else:
                X_norm[:, col] = 0.0
                
    # 2. 空间布局打分 (Min-Max, 0-5分)
    for col in score_idx:
        if col < X.shape[1]:
            vals = X[:, col]
            # 假设打分最高5分
            X_norm[:, col] = vals / 5.0
            
    # 3. 布尔列 (0/1 -> 0/0.5)
    for col in bool_idx:
        if col < X.shape[1]:
            vals = X[:, col]
            # 简单的二值化清洗
            vals = np.where(vals > 0, 1.0, 0.0)
            X_norm[:, col] = vals * 0.5
            
    return X_norm