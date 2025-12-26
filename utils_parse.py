import pandas as pd
import json
import re

def process_land_use(file,output_file):

    # 定义分类规则
    agricultural_land = ['耕地', '林地', '园地', '草地']  # 农用地
    construction_land = ['商服用地', '工矿用地', '住宅用地', '公共管理与公共服务用地', '特殊用地资源', '交通运输用地']  # 建设用地
    ecological_land = ['水域及水利设施用地', '其他用地']  # 生态保护

    # 读取Excel文件
    df = pd.read_csv(file)

    print("原始数据列名:")
    for i, col in enumerate(df.columns):
        print(f"{i+1}. {col}")

    # 创建新的DataFrame用于存储结果
    result_df = pd.DataFrame()
    result_df['地区'] = df['地区']  # 假设第一列是地区

    # 计算各类用地的总和
    # 农用地总和
    agricultural_sum = df[agricultural_land].sum(axis=1)
    result_df['农用地'] = agricultural_sum

    # 建设用地总和
    construction_sum = df[construction_land].sum(axis=1)
    result_df['建设用地'] = construction_sum

    # 生态保护用地总和
    ecological_sum = df[ecological_land].sum(axis=1)
    result_df['生态保护'] = ecological_sum
    
    result_df['林地占比'] = df["林地"]/(agricultural_sum + construction_sum + ecological_sum) 

    # 显示结果
    print("\n处理后的数据:")
    print(result_df.head())

    # 保存到新的Excel文件
    result_df.to_csv(output_file,index=False, encoding='utf-8-sig',float_format='%.4f') # type: ignore
    
    print(f"\n结果已保存到 {output_file}")

def parse_land_use_row(raw_json_input):
    """
    解析行数据（严格模式）
    只返回预定义的12个列，多余的字段会被丢弃，缺少的字段填0
    """
    # === 1. 定义标准列名（白名单） ===
    target_categories = [
        "耕地", "园地", "林地", "草地", "商服用地", "工矿用地", 
        "住宅用地", "公共管理与公共服务用地", "特殊用地资源", 
        "交通运输用地", "水域及水利设施用地", "其他用地"
    ]
    
    # 临时字典，用来存放提取到的原始数据
    extracted_data = {}

    if pd.isna(raw_json_input) or raw_json_input == "":
        # 如果是空的，直接返回全0
        return pd.Series({cat: 0.0 for cat in target_categories})

    try:
        # === 2. 获取内部内容 ===
        inner_content = ""
        try:
            # 尝试解析外层包裹
            if isinstance(raw_json_input, str):
                outer_data = json.loads(raw_json_input)
                if isinstance(outer_data, dict):
                    inner_content = outer_data.get("output", "")
                else:
                    inner_content = raw_json_input
            else:
                inner_content = str(raw_json_input)
        except:
            inner_content = str(raw_json_input)

        # === 3. 混合解析策略 ===
        
        # 策略 A: 尝试把 inner_content 当作标准 JSON 直接解析
        # (针对你刚刚提供的 "和平县" 这种纯数字的 Clean JSON 数据)
        json_success = False
        try:
            inner_json = json.loads(inner_content)
            # 找到 "数据" 节点
            if "数据" in inner_json and isinstance(inner_json["数据"], dict):
                source_dict = inner_json["数据"]
                # 直接读取字典
                for k, v in source_dict.items():
                    # 清理 Key 的空格，防止 " 耕地" 造成新列
                    clean_key = k.strip()
                    # 转换数值 (如果是 100+20 这种字符串，这里会报错，转入 except)
                    extracted_data[clean_key] = float(v)
                json_success = True
        except Exception:
            # 如果 JSON 解析失败（比如里面有 100+20 算式），或者是格式不对
            json_success = False

        # 策略 B: 如果 A 失败，使用正则暴力提取
        # (针对 "1474.0067 + 37.3245" 这种算式数据)
        if not json_success:
            # 匹配 "数据": { ... } 内容
            block_match = re.search(r'"数据":\s*\{(.*?)\}', inner_content, re.DOTALL)
            search_source = block_match.group(1) if block_match else inner_content
            
            pattern = r'"([^"]+)"\s*:\s*([0-9\.\s\+]+)'
            items = re.findall(pattern, search_source)
            
            for key, expression in items:
                try:
                    clean_key = key.strip() # 去除 Key 的空格
                    # 计算加法
                    val = sum([float(num.strip()) for num in expression.split('+') if num.strip()])
                    extracted_data[clean_key] = val
                except:
                    pass

    except Exception as e:
        print(f"解析异常: {e}")

    # === 4. 关键步骤：强制对齐列名 ===
    # 只有在这里存在的 key 才会被返回，这就杜绝了“新开12个标题”的问题
    final_result = {}
    for cat in target_categories:
        # 从提取的数据中取值，如果没有就填 0.0
        final_result[cat] = extracted_data.get(cat, 0.0)

    return pd.Series(final_result)


MISSING_CONTENT_REGIONS = []

def parse_problem_row(raw_json_input,region_name):
    """
    解析“存在问题类别排序”的文本数据。
    针对每个标准问题类别，提取其“排序”和“严重性说明”。
    通过检查是否包含“存在问题类别排序”来判断是否有有效内容。
    """
    # === 1. 定义标准问题类别（白名单） ===
    target_problems = [
        "耕地碎片化",
        "产业发展与用地供给矛盾",
        "人地协调矛盾",
        "人与自然的矛盾",
        "低效用地问题"
    ]
    
    # 初始化结果字典
    # 按照您的要求：不存在则设置为 None 或 0
    final_result = {}
    none_data_region = []
    for prob in target_problems:
        final_result[f"{prob}_排序"] = 0      # 默认排序为 0
        final_result[f"{prob}_说明"] = None   # 默认说明为 None

    if pd.isna(raw_json_input) or raw_json_input == "":
        MISSING_CONTENT_REGIONS.append(region_name)
        return pd.Series(final_result)  # 直接返回默认值

    try:
        # === 2. 获取内部文本内容 ===
        inner_content = ""
        try:
            if isinstance(raw_json_input, str):
                outer_data = json.loads(raw_json_input)
                if isinstance(outer_data, dict):
                    inner_content = outer_data.get("output", "")
                else:
                    inner_content = raw_json_input
            else:
                inner_content = str(raw_json_input)
        except:
            inner_content = str(raw_json_input)

        # === 3. 核心校验：检查是否存在标志性表头 ===
        # 根据指示：只有包含“存在问题类别排序”时才认为有数据
        # 只要文本里没有这句话，直接视为无数据，返回默认的 0 和 None
        if "存在问题类别排序" not in inner_content:
            MISSING_CONTENT_REGIONS.append(region_name)
            return pd.Series(final_result)

        # === 4. 正则提取策略 ===
        # 文本特征是：
        # 1. 【耕地碎片化】
        # ... - 严重性说明：xxxxxx
        # ... - 排序：1
        
        for prob in target_problems:
            # 构建动态正则
            # re.escape(prob) 确保标题中的特殊字符被转义
            pattern = (
                r"【" + re.escape(prob) + r"】"
                r".*?严重性说明[：:]\s*(.*?)\s*\n"
                r".*?排序[：:]\s*(\d+)"
            )
            
            match = re.search(pattern, inner_content, re.DOTALL)
            
            if match:
                description = match.group(1).strip()
                rank = int(match.group(2))
                
                final_result[f"{prob}_说明"] = description
                final_result[f"{prob}_排序"] = rank
            else:
                # 兜底策略：尝试只匹配标题和排序
                try:
                    simple_pattern = r"【" + re.escape(prob) + r"】.*?排序[：:]\s*(\d+)"
                    simple_match = re.search(simple_pattern, inner_content, re.DOTALL)
                    if simple_match:
                        final_result[f"{prob}_排序"] = int(simple_match.group(1))
                except:
                    pass

    except Exception as e:
        print(f"解析异常: {e}")

    return pd.Series(final_result)


def batch_issue_data_parse(csv_file,output_file):
    global MISSING_CONTENT_REGIONS
    MISSING_CONTENT_REGIONS = [] 
    
    df = pd.read_csv(csv_file)
            
    # parse_problem_row 会返回一个 DataFrame，列名就是地类名称
    parsed_df = df.apply(
        lambda row: parse_problem_row(row['原始数据'], row['地区']), 
        axis=1)
    print(parsed_df.head())
    
    # 修改排序值为整数
    rank_cols = [col for col in parsed_df.columns if col.endswith('_排序')]
    if len(rank_cols) > 0:
        parsed_df[rank_cols] = parsed_df[rank_cols].astype(int)
    
    # 3. 合并结果
    # 将原始的“地区”列（如果存在）和解析出来的地类列合并
    if '地区' in df.columns:
        result_df = pd.concat([df[['地区']], parsed_df], 
        axis=1)
    else:
        result_df = pd.concat([df, parsed_df], axis=1)
        
    # 4. 预览数据
    print("\n处理完成！前 5 行数据预览：")
    print(result_df.head()[:1])
    
    # 5. 保存到新 CSV
    result_df.to_csv(output_file, index=False, encoding='utf-8-sig') # utf-8-sig 防止中文乱码
    print(f"\n✅ 结果已保存至: {output_file}")
    print(f"error regions {len(MISSING_CONTENT_REGIONS)} :",MISSING_CONTENT_REGIONS)
    return result_df