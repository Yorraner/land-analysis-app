import pandas as pd
import json
import re
import numpy as np

# ==========================================
# 1. 土地利用现状 (自然资源禀赋) 解析器
# ==========================================
def parse_land_use_row(raw_json_input):
    """
    解析“土地利用现状”数据，提取 12 个基础地类。
    支持处理 "100 + 20" 这种算术表达式。
    """
    # 定义12个标准地类
    target_categories = [
        # 农用地相关
        "耕地", "园地", "林地", "草地", "设施农用地", "田坎",
        # 建设用地相关
        "商服用地", "工矿用地", "住宅用地", "公共管理与公共服务用地", "特殊用地资源", "交通运输用地", 
        "城镇村及工矿用地", # <--- 新增：大模型常返回这个汇总类
        # 生态相关
        "水域及水利设施用地", "其他用地", "其他土地" # <--- 新增：国标常用名
    ]
    
    # 初始化全0
    final_result = {cat: 0.0 for cat in target_categories}

    if pd.isna(raw_json_input) or raw_json_input == "":
        return pd.Series(final_result)

    try:
        # 1. 获取内部内容 (剥离外层 JSON)
        inner_content = str(raw_json_input)
        try:
            if isinstance(raw_json_input, str):
                # 尝试解析最外层的 {"output": "..."}
                try:
                    outer_data = json.loads(raw_json_input)
                except:
                    outer_data = None
                
                if isinstance(outer_data, dict):
                    inner_content = outer_data.get("output", raw_json_input)
                # 如果解析出来是列表，说明没有 output 包裹，直接用
                elif isinstance(outer_data, list):
                    inner_content = raw_json_input # 保持原样，后面处理
        except:
            pass

        # 2. 核心解析逻辑
        extracted_data = {}
        
        # 尝试将 inner_content 解析为 Python 对象 (Dict 或 List)
        try:
            # 如果 inner_content 已经是对象（在某些流程里可能已经被解包）
            if isinstance(inner_content, (dict, list)):
                parsed_obj = inner_content
            else:
                parsed_obj = json.loads(str(inner_content))
            
            # --- 情况 A: 列表格式 [{"类别": "耕地", "面积": 100}, ...] ---
            if isinstance(parsed_obj, list):
                for item in parsed_obj:
                    if isinstance(item, dict):
                        # 模糊匹配 Key，找到"类别"和"面积"
                        key_name = None
                        val_num = 0.0     
                        # 找名字
                        for k in ["类别", "类型", "name", "category", "地类"]:
                            if k in item:
                                key_name = item[k]
                                break
                        # 找数值
                        for k in ["面积", "数值", "area", "value", "规模"]:
                            if k in item:
                                try:
                                    val_num = float(item[k])
                                except:
                                    val_num = 0.0
                                break
                        
                        if key_name:
                            extracted_data[key_name.strip()] = val_num

            # --- 情况 B: 字典格式 {"数据": {"耕地": 100, ...}} 或 {"耕地": 100} ---
            elif isinstance(parsed_obj, dict):
                # 兼容 {"数据": ...} 嵌套
                source_dict = parsed_obj.get("数据", parsed_obj)
                if isinstance(source_dict, dict):
                    for k, v in source_dict.items():
                        try:
                            extracted_data[k.strip()] = float(v)
                        except: pass
        
        except Exception:
            # --- 情况 C: 正则暴力提取 (处理非标准 JSON 字符串) ---
            # 匹配 "耕地": 123.45 或 "类别":"耕地","面积":123.45
            # 简单策略：找所有 "中文": 数字 的对
            pattern = r'"([\u4e00-\u9fa5]+)"\s*[:：]\s*([0-9\.]+)'
            items = re.findall(pattern, str(inner_content))
            for k, v in items:
                try:
                    extracted_data[k] = float(v)
                except: pass

        # 3. 填入结果
        for cat in target_categories:
            # 优先精确匹配
            if cat in extracted_data:
                final_result[cat] = extracted_data[cat]
            else:
                # 尝试模糊匹配 (防止少许错别字)
                pass 

    except Exception as e:
        print(f"解析出错: {e}")

    return pd.Series(final_result)

# ==========================================
# 2. 存在问题 解析器
# ==========================================
def parse_issue_row(raw_json_input, target_problems):
    final_result = {f"{p}_排序": 0 for p in target_problems}
    final_result.update({f"{p}_说明": None for p in target_problems})

    if pd.isna(raw_json_input) or raw_json_input == "":
        return pd.Series(final_result)

    try:
        inner_content = str(raw_json_input)
        try:
            if isinstance(raw_json_input, str):
                outer = json.loads(raw_json_input)
                if isinstance(outer, dict): inner_content = outer.get("output", raw_json_input)
        except: pass

        if "存在问题类别排序" not in inner_content:
            return pd.Series(final_result)

        for prob in target_problems:
            pattern = (r"【" + re.escape(prob) + r"】"
                       r".*?严重性说明[：:]\s*(.*?)\s*\n"
                       r".*?排序[：:]\s*(\d+)")
            match = re.search(pattern, inner_content, re.DOTALL)
            if match:
                final_result[f"{prob}_说明"] = match.group(1).strip()
                final_result[f"{prob}_排序"] = int(match.group(2))
            else:
                try:
                    simple_match = re.search(r"【" + re.escape(prob) + r"】.*?排序[：:]\s*(\d+)", inner_content, re.DOTALL)
                    if simple_match: final_result[f"{prob}_排序"] = int(simple_match.group(1))
                except: pass
    except: pass
    return pd.Series(final_result)

# ==========================================
# 3. 整治潜力 解析器
# ==========================================
def parse_potential_row(raw_json_input, target_potentials):
    final_result = {item: 0.0 for item in target_potentials}
    
    if pd.isna(raw_json_input) or raw_json_input == "": return pd.Series(final_result)

    try:
        inner_content = str(raw_json_input)
        try:
            outer = json.loads(inner_content)
            data_dict = json.loads(outer.get("output", inner_content)) if isinstance(outer, dict) else outer
        except:
            # 如果不是标准JSON，尝试直接当文本处理
            return pd.Series(final_result)

        if isinstance(data_dict, dict):
            for _, items in data_dict.items():
                if isinstance(items, dict):
                    for name, desc in items.items():
                        if name in final_result:
                            val_match = re.search(r"(-?\d+\.?\d*)", str(desc))
                            if val_match and "未提及" not in str(desc):
                                final_result[name] = float(val_match.group(1))
    except: pass
    return pd.Series(final_result)

# ==========================================
# 4. 项目汇总 解析器
# ==========================================
def parse_project_row(raw_json_input):
    target_categories = ["农用地整理类项目", "建设用地整理类项目", "生态保护修复类项目", 
                         "乡村风貌提升和历史文化保护类项目", "公共服务与基础设施建设类项目", 
                         "产业导入类项目", "其他类项目"]
    metrics = ["数量", "投资", "规模"]
    final_result = {f"{c}_{m}": 0.0 for c in target_categories for m in metrics}

    if pd.isna(raw_json_input) or raw_json_input == "": return pd.Series(final_result)
    
    try:
        inner_content = str(raw_json_input)
        try:
            outer = json.loads(inner_content)
            if isinstance(outer, dict): inner_content = outer.get("output", inner_content)
        except: pass

        lines = inner_content.split('\n')
        for line in lines:
            if '|' in line and len(line.split('|')) >= 4:
                parts = [p.strip() for p in line.strip('|').split('|')]
                cat_name = parts[0].replace(" ", "")
                for target in target_categories:
                    if target in cat_name:
                        for i, val_str in enumerate(parts[1:4]): # 数量, 投资, 规模
                            match_num = re.search(r"(-?\d+\.?\d*)", val_str)
                            val = float(match_num.group(1)) if match_num and "缺失" not in val_str else 0.0
                            final_result[f"{target}_{metrics[i]}"] = val
    except: pass
    return pd.Series(final_result)

# ==========================================
# 统一处理入口
# ==========================================
def process_raw_data(df, data_type):
    """
    根据选择的数据类型，调用不同的解析器，并执行特定的聚合计算。
    """
    # 1. 存在问题
    if "存在问题" in data_type or "问题" in data_type:
        problems = [col[:-3] for col in df.columns if col.endswith("_排序")]
        if not problems: problems = ["耕地碎片化", "产业发展与用地供给矛盾", "人地协调矛盾", "人与自然的矛盾", "低效用地问题"]
        return df.apply(lambda row: parse_issue_row(row.get('rawdata'), problems), axis=1)
    
    # 2. 自然资源禀赋 (土地利用现状) - 特殊聚合逻辑
    elif "自然资源" in data_type or "土地利用" in data_type:
        # A. 先提取基础的 12 个地类
        base_df = df['rawdata'].apply(parse_land_use_row)
        
        # B. 执行聚合计算 (农用地、建设用地、生态保护、林地占比)
        # 定义分类规则
        agri_cols = ['耕地', '林地', '园地', '草地', '设施农用地', '田坎']
        # 建设用地：优先用 "城镇村及工矿用地" (如果它有值且很大)，否则用分项求和
        # 这里采用“加和”策略，并在 base_df 中寻找所有可能的建设用地列
        cons_cols = ['商服用地', '工矿用地', '住宅用地', '公共管理与公共服务用地', '特殊用地资源', '交通运输用地']
        # 生态用地
        eco_cols = ['水域及水利设施用地', '其他用地', '其他土地']
          result_df = pd.DataFrame()
        
        # 1. 农用地
        result_df['农用地'] = base_df[agri_cols].fillna(0).sum(axis=1)
        
        # 2. 建设用地 (智能判断)
        # 如果 "城镇村及工矿用地" 有值，且远大于 分项之和，则优先使用它 (因为分项可能缺失)
        # 加上 "交通运输用地" (它通常不包含在城镇村中)
        
        # 先算分项和
        sum_cons_sub = base_df[cons_cols].fillna(0).sum(axis=1)
        # 拿总项
        val_cons_total = base_df['城镇村及工矿用地'].fillna(0)
        result_df['建设用地'] = np.where(
            val_cons_total > 0,
            val_cons_total + base_df['交通运输用地'].fillna(0) + base_df['特殊用地资源'].fillna(0),
            sum_cons_sub
        )
        # 3. 生态保护
        result_df['生态保护'] = base_df[eco_cols].fillna(0).sum(axis=1)
        
        # 4. 林地占比
        total_area = result_df['农用地'] + result_df['建设用地'] + result_df['生态保护']
        result_df['林地占比'] = np.where(total_area > 0, base_df['林地'].fillna(0) / total_area, 0.0) 
        return result_df
    # 3. 整治潜力
    elif "潜力" in data_type:
        potentials = ["垦造水田潜力", "新增耕地潜力", "耕地“非粮化”整治潜力", "耕地恢复潜力", "高标准农田建设潜力", 
                      "耕地提质改造潜力", "补充耕地潜力", "耕地集中整治区建设潜力", "低效工业用地腾退潜力", "存量低效用地潜力", 
                      "低效用地再开发潜力", "三旧改造潜力", "城镇低效用地再开发潜力", "建设用地增减挂钩（拆旧复垦）潜力", 
                      "红树林保护潜力", "矿山修复潜力", "土壤整治潜力", "造林绿化潜力", "流域生态修复潜力"]
        return df.apply(lambda row: parse_potential_row(row.get('rawdata'), potentials), axis=1)
    
    # 4. 项目汇总
    elif "项目" in data_type:
        return df.apply(lambda row: parse_project_row(row.get('rawdata')), axis=1)
    
    # 5. 空间布局 (如果后续有单独的解析逻辑，可加在这里，目前暂无特定逻辑)
    elif "空间" in data_type:
        # 假设空间布局也是类似潜力的 JSON 提取
        spatial_cols = ['永农调入规模（公顷）', '永农调出规模（公顷）', '城镇开发调入规模（公顷）', '城镇开发调出规模（公顷）', '规划单元空间调整打分（最高5分）']
        return df.apply(lambda row: parse_potential_row(row.get('rawdata'), spatial_cols), axis=1)
    
    return df