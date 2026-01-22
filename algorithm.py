import numpy as np
import pandas as pd
from os.path import join as opj
from sklearn.cluster import KMeans


def build_weight_vector(weight_settings, feature_columns):
    """
    构建特征权重向量
    ----------
    weight_settings: dict, 用户在 UI 上设置的权重字典 (key=中文业务名, value=float)
    feature_columns: list/Index, 特征矩阵的列名列表 (如 ['landuse:农用地', 'potential:潜力', ...])
    
    Return:
    np.array shape=(n_features,)
    """
    # 1. 定义映射关系：UI上的中文 Key -> 数据文件的前缀 (Suffix)
    # 必须与 TASK_DICT 和 Step 4 生成的前缀保持一致
    prefix_map = {
        "landuse": "自然资源禀赋",
        "potential": "潜力项数据",
        "spatial": "空间布局",
        "issue": "存在问题",
        "project": "子项目数据"
    }
    
    weights = []
    
    # 2. 遍历每一个特征列，根据其名字分配权重
    for col in feature_columns:
        w = 1.0 # 默认权重
        
        # 解析列名，格式通常为 "prefix:feature_name"
        if ":" in col:
            prefix, real_name = col.split(":", 1)
        else:
            prefix = "default"
            real_name = col
            
        # A. 匹配大类权重
        if prefix in prefix_map:
            ui_key = prefix_map[prefix]
            # 获取用户设置的值，如果没有设置则默认为 1.0
            w = weight_settings.get(ui_key, 1.0)
            
        # B. 处理特殊细分项权重 (如：自然资源中的“林地”或“布尔”项)
        # 这里逻辑是：如果列名包含特定关键词，使用特殊权重覆盖或叠加
        if prefix == "landuse":
            if "林地" in real_name or "布尔" in real_name:
                # 如果 UI 里设置了 "自然资源-布尔项"，则使用该权重
                if "自然资源-布尔项" in weight_settings:
                    w = weight_settings["自然资源-布尔项"]

        weights.append(w)
        
    return np.array(weights)

def entropy_weight_method(X):
    """
    输入：DataFrame，行=样本（地区），列=指标
    输出：各指标权重
    """
    # 1. 标准化到 [0,1]
    # scaler = MinMaxScaler()
    # X = scaler.fit_transform(data.values)
    X = np.where(X == 0, 1e-12, X)  # 防止 log(0)

    # 2. 计算比重 pij
    P = X / X.sum(axis=0)

    # 3. 计算熵值
    n = X.shape[0]
    k = 1.0 / np.log(n)
    E = -k * (P * np.log(P)).sum(axis=0)

    # 4. 计算权重
    d = 1 - E
    w = d / d.sum()

    return w, E

def weighted_kmedoids_prob(X, weights, n_clusters=3, max_iter=400, random_state=42):
    """
    自实现 KMedoids (PAM)，支持加权特征，并输出类别概率
    ----------
    X : array, shape (n_samples, n_features)
        输入数据
    weights : array, shape (n_features,)
        特征权重
    n_clusters : int
        聚类数
    max_iter : int
        最大迭代次数
    random_state : int
        随机种子
    
    返回:
    prob : array, shape (n_samples, n_clusters)
        每个样本属于各簇的概率分布
    medoids : array, shape (n_clusters,)
        簇中心索引
    clusters : list of list
        每个簇包含的样本索引
    """

    rng = np.random.default_rng(random_state)

    # 特征加权
    X_weighted = X * weights

    n_samples = X_weighted.shape[0]

    # 随机初始化中心
    medoids = rng.choice(n_samples, n_clusters, replace=False)

    for _ in range(max_iter):
        # 计算所有点到所有中心的距离
        distances = np.linalg.norm(X_weighted[:, np.newaxis, :] - X_weighted[medoids][np.newaxis, :, :], axis=2)
        labels = np.argmin(distances, axis=1)

        new_medoids = medoids.copy()
        # 更新每个簇的 medoid
        for i in range(n_clusters):
            cluster_points = np.where(labels == i)[0]
            if len(cluster_points) == 0:
                continue
            # 计算该簇内所有点两两之间的距离和
            intra_distances = np.linalg.norm(X_weighted[cluster_points][:, np.newaxis, :] - 
                                             X_weighted[cluster_points][np.newaxis, :, :], axis=2)
            costs = intra_distances.sum(axis=1)
            new_medoids[i] = cluster_points[np.argmin(costs)]

        if np.all(new_medoids == medoids):
            break
        medoids = new_medoids

    # 最终簇划分
    distances = np.linalg.norm(X_weighted[:, np.newaxis, :] - X_weighted[medoids][np.newaxis, :, :], axis=2)
    labels = np.argmin(distances, axis=1)

    # 转换为概率分布
    epsilon = 1e-8
    inv_dist = 1 / (distances + epsilon)
    prob = inv_dist / inv_dist.sum(axis=1, keepdims=True)

    # 返回簇划分
    clusters = [np.where(labels == i)[0].tolist() for i in range(n_clusters)]

    return prob, medoids, clusters

def weighted_kmeans_prob(X, weights, n_clusters=3, random_state=42):
    """
    基于 K-Means 的加权聚类，并输出类别概率
    ----------
    X : array, shape (n_samples, n_features)
    weights : array, shape (n_features,) 特征权重
    n_clusters : int 聚类数
    
    返回:
    probs : array (n_samples, n_clusters) 概率矩阵
    centroids : array (n_clusters, n_features) 聚类中心坐标
    labels : array (n_samples,) 聚类标签
    """
    
    # 1. 特征加权
    # 在计算欧氏距离时，X * w 相当于对特征维度进行缩放
    # 权重大的特征数值变大，对距离的影响也变大
    X_weighted = X * weights

    # 2. 执行 K-Means
    kmeans = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
    kmeans.fit(X_weighted)
    
    # 获取聚类标签
    labels = kmeans.labels_
    # 获取聚类中心 (加权空间下的坐标)
    centroids = kmeans.cluster_centers_

    # 3. 计算概率 (Soft Clustering)
    # transform 返回样本到每个聚类中心的欧氏距离 (n_samples, n_clusters)
    dists = kmeans.transform(X_weighted)
    
    # 将距离转换为“相似度”或“概率”
    # 方法：使用距离的倒数 (Inverse Distance Weighting)
    # 加上极小值 epsilon 防止除以 0
    epsilon = 1e-8
    inv_dists = 1.0 / (dists + epsilon)
    
    # 归一化，使每行的概率和为 1
    probs = inv_dists / inv_dists.sum(axis=1, keepdims=True)

    return probs, centroids, labels


def clustering_kmeans_with_entropy_expert(X, region,\
    expert_weights=None, n_clusters=3, top_k=3,path=None):
    """
    主客观结合聚类 (K-Means + 熵权 + 专家权重)
    ----------
    X: (n_samples, n_features)
    region: 地区名称 (list)
    expert_weights: 可选专家权重数组 (n_features,)
    """
    # 确保 X 是 numpy 数组
    X = np.array(X)
    n_samples, n_features = X.shape
    feature_names = [f"F{i}" for i in range(n_features)]

    # 1. 熵权法计算权重
    # 假设 entropy_weight_method 已经在外部定义
    entropy_w, entropy_val = entropy_weight_method(X)
    feature_importance = pd.Series(entropy_w, index=feature_names)

    # 2. 融合专家权重
    if expert_weights is not None:
        if len(expert_weights) != n_features:
            raise ValueError("专家权重长度必须与特征数量一致")
        combined_weights = entropy_w * np.array(expert_weights)
        # 归一化权重
        combined_weights = combined_weights / combined_weights.sum()
    else:
        combined_weights = entropy_w

    # 3. K-Means 聚类 (替换了原来的 KMedoids)
    # 注意：这里返回的是 centroids (中心坐标) 而不是 medoids (样本索引)
    prob_all, centroids, labels = weighted_kmeans_prob(
        X, combined_weights, n_clusters=n_clusters
    )

    # 4. 构建结果 DataFrame
    df_result = pd.DataFrame(
        prob_all,
        index=region,
        columns=[f"Cluster_{i+1}" for i in range(n_clusters)]
    )
    df_result.index.name = "地区"

    # 5. 计算 Top-K 结果
    # argsort 默认从小到大，[::-1] 反转为从大到小
    topk_indices = np.argsort(df_result.values, axis=1)[:, ::-1][:, :top_k]
    # 获取对应的概率值
    topk_probs = np.take_along_axis(df_result.values, topk_indices, axis=1)
    
    for i in range(top_k):
        # 记录 Top i 的类别 (索引+1)
        df_result[f"Top{i+1}_Cluster"] = [
            int(str(df_result.columns[idx]).split("_")[1])
            for idx in topk_indices[:, i]
        ]
        # 记录 Top i 的概率
        df_result[f"Top{i+1}_Prob"] = topk_probs[:, i]

    # 6. 统计与输出
    print("分类结果统计：\n")
    for i in range(1, n_clusters + 1):
        mask = df_result['Top1_Cluster'] == i
        count = mask.sum()
        regions_in_cluster = df_result.index[mask].tolist()
        ratio = (count / n_samples) * 100
        print(f"类别 {i} 作为Top1的地区数: {count} / {ratio:.1f}%")
        print(f"地区: {regions_in_cluster}\n")
    
    name = f"clustering_entropy_kmeans_{n_clusters}.xlsx"
    save_file = opj(path, name)
    df_result.to_excel(save_file)
    print(f"结果已保存至: {save_file}")

    return df_result, feature_importance, combined_weights, centroids, labels