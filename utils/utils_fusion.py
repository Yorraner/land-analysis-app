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

def preprocess_X(X, eps=1e-8, use_log=True):
    """
    预处理函数：
    1. (可选) 对数值列执行 Log1p 变换，拉近长尾分布
    2. 执行 Min-Max 归一化
    """
    # 确保输入是numpy数组
    if not isinstance(X, np.ndarray):
        X = np.array(X, dtype=np.float64)
    
    X_proc = X.copy().astype(np.float64)
    X_norm = np.zeros_like(X_proc, dtype=np.float64)
    
    # === 列索引定义 (硬编码，需与数据列顺序一致) ===
    # 1. 面积相关
    area_potential_idx = list(range(4, 23))          # 4-22
    area_spatial_idx = list(range(23, 27))           # 23-26
    area_specific_idx = [34, 37, 40, 43, 46, 49, 52] # 子项目面积
    
    area_idx = list(range(0, 3)) + area_potential_idx + area_spatial_idx + area_specific_idx
    # 2. 金额相关
    money_idx = [35, 38, 41, 44, 47, 50, 53] 
    # 3. 数量相关
    count_idx = [33, 36, 39, 42, 45, 48, 51]
    # 4. 布尔/打分相关 (不进行 Log 变换)
    # 27=规划打分, 3=林地(占比), 28-32=存在问题
    # [3] 林地占比不进行归一化 
    bool_idx =  list(range(28, 33)) 
    score_idx = [27]
    forest_ratio_idx = [3]
    # === 1. Log1p 变换 (关键步骤) ===
    if use_log:
        # 汇总所有需要 Log 的列 (面积、金额、数量)
        numeric_indices = []
        for idx_list in [area_idx, money_idx, count_idx]:
            # 过滤越界索引
            valid = [i for i in idx_list if i < X.shape[1]]
            numeric_indices.extend(valid)
        if numeric_indices:
            # np.log1p(x) = log(x + 1)，可以处理 0 值，且平滑长尾
            # np.maximum(..., 0) 确保没有负数输入
            X_proc[:, numeric_indices] = np.log1p(np.maximum(X_proc[:, numeric_indices], 0))

    # === 2. Min-Max 归一化 ===
    # A. 数值列 (已经 Log 过)
    for indices in [area_idx, money_idx, count_idx]:
        valid_idx = [i for i in indices if i < X.shape[1]]
        if not valid_idx: continue
        for col in valid_idx:
            vals = X_proc[:, col]
            vmin, vmax = vals.min(), vals.max()
            if (vmax - vmin) > eps:
                X_norm[:, col] = (vals - vmin) / (vmax - vmin)*0.99999 + 0.00001
            else:
                X_norm[:, col] = 0.0 # 如果所有值都一样，归一化为0
                
    # B. 空间布局打分 (0-5分) -> 归一化到 0-1
    for col in score_idx:
        if col < X.shape[1]:
            # 打分通常不 Log，直接除以最大值
            vals = X[:, col]
            X_norm[:, col] = vals / 5.0
            
    # C. 布尔列 (0/1) -> 映射为 0.0 / 0.5
    for col in bool_idx:
        if col < X.shape[1]:
            vals = X[:, col]
            # 强制二值化
            vals = np.where(vals > 0, 1.0, 0.0)
            X_norm[:, col] = vals * 0.5
    # D. 林地占比列 (0-1) -> 直接使用
    for col in forest_ratio_idx:
        if col < X.shape[1]:
            vals = X[:, col]
            X_norm[:, col] = vals
    
    return X_norm