import fitz  # PyMuPDF
import re
import pikepdf
import io
import os
import fitz  
import difflib


def calculate_global_offset(doc, toc_dict):
    """
    通过对比【目录中的页码】和【正文中标题实际出现的页码】，计算全局偏移量。
    已增加：防目录误判逻辑（避免匹配到目录页本身）。
    """
    if not toc_dict: return 0
    
    print("🔄 正在利用目录内容进行偏移量校准 (Anchor Calibration)...")

    # 1. 选取锚点
    valid_entries = []
    for title, pages in toc_dict.items():
        start_page = pages[0]
        if start_page >= 1:
            valid_entries.append((title, start_page))
    
    valid_entries.sort(key=lambda x: x[1])
    anchors = valid_entries[:3] # 取前3个

    if not anchors: return 0

    # 2. 遍历锚点
    for title, logic_page in anchors:
        # 扩大搜索范围，但跳过极前部（防止匹配到封面/摘要）
        # 假设 Offset 可能很大（比如前言有15页），所以往后多搜一点
        search_start = max(0, logic_page - 5) 
        search_end = min(doc.page_count, logic_page + 30)

        # 清洗标题
        clean_target = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", title)
        if len(clean_target) < 2: continue

        for i in range(search_start, search_end):
            try:
                page = doc[i]
                
                # === 核心修改 1: 获取更详细的文本块 ===
                # 我们不仅要看 text，还要看这一行长什么样
                # 获取页面上部 40%
                header_rect = fitz.Rect(0, 0, page.rect.width, page.rect.height * 0.4)
                
                # 获取 text 及其布局位置，按行分割
                page_text = page.get_text("text", clip=header_rect)
                lines = page_text.split('\n')
                
                is_real_header = False
                
                for line in lines:
                    clean_line = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", line)
                    
                    # 检查是否包含标题
                    if clean_target in clean_line:
                        # === 核心修改 2: 排除目录特征 ===
                        # 特征 A: 后面紧跟数字 (e.g., "第一章... 1")
                        # 特征 B: 包含大量虚线/点 (e.g., "......")
                        
                        # 检查原始 line 是否以数字结尾 (允许少量空格)
                        if re.search(r'[\.\…\s]+\d+\s*$', line.strip()):
                            # print(f"   [跳过] 第 {i+1} 页疑似目录项: {line.strip()}")
                            continue 
                        # 特征 C: 检查该页是不是明确写着“目录”
                        # (如果页面最顶端写着“目录”，哪怕这行没有数字也跳过)
                        if "目录" in page_text[:50] and i < 20: 
                             continue
                        # 通过所有检查，认为是正文标题
                        is_real_header = True
                        break
                if is_real_header:
                    # 计算偏移量
                    offset = i - (logic_page - 1)
                    
                    # 再次校验：Offset 通常 >= 0
                    if offset >= 0:
                        print(f"✅ 校准成功！锚点: '{title}'")
                        print(f"   - 目录页码: {logic_page}")
                        print(f"   - 物理索引: {i} (第 {i+1} 页)")
                        print(f"   - 修正 Offset: {offset}")
                        return offset
            except:
                continue

    print("⚠️ 未能通过内容校准偏移量，默认 Offset = 0")
    return 0


# ========================================================
# 解析目录生成字典
# ========================================================
def parse_toc_to_dict(doc, max_scan_pages=20):
    """
    解析PDF目录，返回结构化字典：
    {
        "clean_title_string": [start_page, end_page],
        ...
    }
    """
    toc_list = [] # 临时存储 [(title, page), ...]
    full_toc_text = ""

    # --- A. 提取前N页文本 ---
    for i in range(min(max_scan_pages, doc.page_count)):
        try:
            page_text = doc[i].get_text()
            if page_text:
                full_toc_text += page_text + "\n"
        except:
            continue

    # --- B. 清洗文本 (关键步骤) ---
    # 1. 去除目录中的虚线/点 (如 "......")
    clean_text = re.sub(r"[…\.．]{2,}", " ", full_toc_text)
    # 2. 尝试修复换行 (有些标题被断成两行，通常下一行是页码)
    # 这一步比较激进，根据实际情况微调
    # clean_text = re.sub(r'\n\s*(\d+)', r' \1', clean_text) 

    # --- C. 正则匹配 (提取 标题 + 页码) ---
    # 匹配模式：行首(可能含章节号) + 内容 + 空格 + 页码(行尾)
    # (?m) 开启多行模式
    # ([^\n\d]+?) 匹配非数字的标题部分 (非贪婪)
    # (\d+) 匹配页码
    pattern = r"(?m)^\s*(.*?)\s+(\d+)\s*$"
    matches = re.findall(pattern, clean_text)

    for title, page_str in matches:
        # 清洗标题：去掉首尾空格、去掉末尾的点
        clean_title = title.strip().rstrip('.').rstrip()
        # 去掉中间的所有空白字符（方便后续模糊匹配）
        compact_title = re.sub(r"\s+", "", clean_title)
        
        # 过滤掉过短的误判 (比如只有 "1")
        if len(compact_title) > 1:
            try:
                page_num = int(page_str)
                # 过滤掉页码大得离谱的误判
                if page_num <= doc.page_count + 10: 
                    toc_list.append((compact_title, page_num))
            except:
                continue

    # --- D. 构建闭环字典 {Title: [Start, End]} ---
    toc_dict = {}
    total_items = len(toc_list)
    
    if total_items == 0:
        return {}

    for i in range(total_items):
        title, start_p = toc_list[i]
        
        # 确定结束页：默认为下一条目的开始页
        if i < total_items - 1:
            next_start_p = toc_list[i+1][1]
            # 逻辑修正：有时候下一章可能和当前章在同一页，或者页码回溯（目录页码错误）
            # 我们取 max(start_p, next_start_p) 保证不倒退
            end_p = max(start_p, next_start_p) 
        else:
            # 最后一项，结束页为文档总页数
            end_p = doc.page_count

        toc_dict[title] = [start_p, end_p]
    # print("current file toc_dict:")
    # print(toc_dict)

    return toc_dict
# ========================================================
# 匹配逻辑：在字典中查表
# ========================================================
def match_section_from_dict(toc_dict, keyword, threshold=0.4, min_pages=1):
    """
    在目录字典中寻找最匹配 keyword 的条目 (增强版)
    改进点：
    1. 引入"标题纯度"：优先匹配"字数更少、更精准"的标题，解决父子标题包含问题。
    2. 引入"页数过滤"：过滤掉页数为0或过短的无效章节。
    """
    if not toc_dict:
        return None, None, None

    candidates = []
    clean_keyword = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", keyword)
    if not clean_keyword: clean_keyword = keyword

    for title, pages in toc_dict.items():
        start_page, end_page = pages
        page_len = end_page - start_page
        
        # === 过滤条件 1: 页数检查 ===
        if page_len < min_pages:
            continue

        # 清洗标题 (去掉 "六、", "(一)", "1." 等序号)
        # 这一步很重要，否则 "(三) 子项目" 的纯度会比 "子项目" 低
        clean_title_full = re.sub(r"^[第\d一二三四五六七八九十\(\)（）\.、\s]+", "", title)
        # 再次清洗，去掉中间空格
        clean_title = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", clean_title_full)

        # === 评分逻辑 ===
        # 1. 基础相似度 (Fuzzy Match)
        if clean_keyword in clean_title:
            base_score = 1.0
        else:
            base_score = difflib.SequenceMatcher(None, clean_keyword, clean_title).ratio()

        # 2. 标题纯度 (Purity) - 解决父子包含问题的核心！
        # 纯度 = 关键词长度 / 标题长度
        # 例子：
        # 关键词="子项目" (3字)
        # 标题A="建设内容与子项目" (8字) -> 纯度 0.375
        # 标题B="子项目" (3字) -> 纯度 1.0
        # 结果：标题B胜出
        if len(clean_title) > 0:
            purity_score = len(clean_keyword) / len(clean_title)
            # 防止关键词比标题长导致的 >1
            purity_score = min(1.0, purity_score)
        else:
            purity_score = 0

        # 3. 综合得分 (加权)
        # 相似度占 60%，纯度占 40% (纯度权重越高，越倾向于短标题)
        final_score = base_score * 0.6 + purity_score * 0.4
        
        # 如果包含关键词，给予额外奖励，确保它比单纯的模糊匹配高
        if clean_keyword in clean_title:
            final_score += 0.2

        if final_score >= threshold:
            candidates.append({
                "title": title,
                "start": start_page,
                "end": end_page,
                "score": final_score,
                "purity": purity_score,
                "len": page_len
            })

    # === 排序选优 ===
    if candidates:
        # 按分数降序排列
        candidates.sort(key=lambda x: x["score"], reverse=True)
        
        best = candidates[0]
        print(f"🔍 搜索: '{keyword}'")
        print(f"   🏆 最佳命中: '{best['title']}' (分: {best['score']:.2f}, 纯度: {best['purity']:.2f}, 页数: {best['len']})")
        
        # 打印其他候选（调试用）
        if len(candidates) > 1:
            second = candidates[1]
            print(f"   🥈 次选匹配: '{second['title']}' (分: {second['score']:.2f})")

        return best["start"], best["end"], best["title"]

    return None, None, None

# ========================================================
# 裁剪函数
# ========================================================
def extract_section_to_pdf(pdf_path, output_path, section_keyword="问题"):
    src_doc = None
    out_doc = None
    try:
        src_doc = fitz.open(pdf_path)
       
        # 2. 解析目录
        print("正在解析目录结构...")
        toc_dict = parse_toc_to_dict(src_doc)
        
        offset = calculate_global_offset(src_doc, toc_dict)
        print(f"📄 文档总页数: {src_doc.page_count}, 计算偏移量 Offset = {offset}")
        
        if not toc_dict:
            print("⚠️ 文本目录解析失败，尝试使用书签...")
            return False

        # 3. 匹配区间 (得到的是目录上的逻辑页码，例如 5 -> 8)
        start_logic, end_logic, matched_title = match_section_from_dict(toc_dict, section_keyword)
        
        if start_logic is None:
            print("❌ 未找到匹配章节")
            return False
        
        start_idx = start_logic + offset - 1
        
        # 处理最后一章的情况 (end_logic 为 99999)
        if end_logic > 90000:
            end_idx = src_doc.page_count - 1 # 直到文档末尾
        else:
            end_idx = end_logic + offset - 1
        # 5. 边界修正
        if start_idx < 0: start_idx = 0
        if start_idx >= src_doc.page_count: 
            print("❌ 计算出的起始页超出文档范围")
            return False
            
        if end_idx >= src_doc.page_count: end_idx = src_doc.page_count - 1
        
        # 关键修正：如果算出来的 end_idx 比 start_idx 还小（目录页码标错了），强制取一页
        if end_idx < start_idx: 
            # 尝试往后多取几页，比如默认提取 3 页
            print("⚠️ 结束页码异常，默认提取 3 页")
            end_idx = min(start_idx + 2, src_doc.page_count - 1)

        print(f"✅ 执行裁剪: {matched_title}")
        print(f"   逻辑页码: {start_logic} -> {end_logic}")
        print(f"   物理索引: {start_idx} -> {end_idx} (Offset={offset})")

        out_doc = fitz.open()
        # insert_pdf 的 to_page 是包含在内的，所以不需要 -1
        out_doc.insert_pdf(src_doc, from_page=start_idx, to_page=end_idx)
        out_doc.save(output_path)
        return True

    except Exception as e:
        print(f"裁剪过程异常: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if src_doc: src_doc.close()
        if out_doc: out_doc.close()



def open_pdf_auto_repair(pdf_path):
    """
    尝试打开 PDF 的通用工具函数。
    优先尝试 fitz 直接打开，失败则调用 pikepdf 修复流。
    """
    try:
        return fitz.open(pdf_path)
    except Exception as e:
        # print(f"fitz 打开失败: {e}，尝试修复...")
        try:
            with pikepdf.open(pdf_path, allow_overwriting_input=True) as p:
                mem_stream = io.BytesIO()
                p.save(mem_stream)
                mem_stream.seek(0)
                return fitz.open("pdf", mem_stream)
        except Exception:
            return None

'''
def compute_page_offset(pdf_path, max_pages_to_check=20):
    """计算页码偏移量"""
    doc = None
    try:
        doc = open_pdf_auto_repair(pdf_path)
        if doc is None: return 0

        for i in range(min(max_pages_to_check, doc.page_count)):
            try:
                page = doc[i]
                text = page.get_text()
                if not text: continue
                lines = [line.strip() for line in text.split("\n") if line.strip()]
                if not lines: continue
                
                last_line = lines[-1]
                match = re.search(r"(?:第\s*(\d+)\s*页)|^\s*(\d+)\s*$", last_line)
                if match:
                    logical_page = int(match.group(1)) if match.group(1) else int(match.group(2))
                    offset = i - (logical_page - 1)
                    return offset
            except:
                continue
    except:
        return 0
    finally:
        if doc: doc.close()
    return 0
'''

'''
def find_section_pages(pdf_path, section_title="问题"):
    """查找章节起止页码"""
    start_page, end_page = None, None
    doc = None

    try:
        doc = open_pdf_auto_repair(pdf_path)
        if doc is None: return None, None

        toc_text = ""
        # 扫描前 20 页作为目录
        for i in range(min(20, doc.page_count)):
            try:
                page_text = doc[i].get_text()
                if page_text: toc_text += page_text + "\n"
            except: continue
        clean_toc_text = re.sub(r"[…\.．]{2,}", " ", toc_text)
        clean_toc_text = re.sub(r'(?m)^\s*([（(]?\s*[\d一二三四五六七八九十][\d.．)）]*[、]?)\s*\n', r'\1 ', clean_toc_text)
        pattern = r"(?m)^\s*([（(]?\s*[\d一二三四五六七八九十].*?)\s+(\d+)\s*$"
        matches = re.findall(pattern, clean_toc_text)

        toc = []
        for title, page in matches:
            clean_title = title.strip().rstrip('.').rstrip()
            compact_title = re.sub(r"\s+", "", clean_title)
            toc.append((compact_title, int(page)))
            
        for idx, (title, page) in enumerate(toc):
            if section_title in title:
                start_page = page
                found_valid_end = False
                for next_idx in range(idx + 1, len(toc)):
                    candidate_end = toc[next_idx][1]
                    if candidate_end > start_page:
                        end_page = candidate_end
                        found_valid_end = True
                        break 
                if not found_valid_end:
                    end_page = doc.page_count + 1
                break 
                
    except:
        return None, None
    finally:
        if doc: doc.close()

    return start_page, end_page
'''

'''
def extract_section_to_pdf(pdf_path, output_path, section_title="问题"):
    """执行裁剪主逻辑"""
    src_doc = None
    out_doc = None
    try:
        offset = compute_page_offset(pdf_path)
        start_logic, end_logic = find_section_pages(pdf_path, section_title)
        
        if start_logic is None or end_logic is None:
            return False

        src_doc = open_pdf_auto_repair(pdf_path)
        if not src_doc: return False

        start_idx = start_logic + offset - 1
        end_idx = end_logic + offset - 1
        
        # 边界修正
        if start_idx < 0: start_idx = 0
        if end_idx > src_doc.page_count: end_idx = src_doc.page_count
        if start_idx >= end_idx: return False

        out_doc = fitz.open()
        out_doc.insert_pdf(src_doc, from_page=start_idx, to_page=end_idx - 1)
        out_doc.save(output_path)
        return True
    except:
        return False
    finally:
        if src_doc: src_doc.close()
        if out_doc: out_doc.close()     
'''

def extract_section_to_pdf_self(pdf_path, start, end, output_path):
    """
    按指定页码裁剪 PDF 并保存 (PyMuPDF 增强版)
    start/end: 逻辑页码 (从 1 开始)
    end: 结束页码 (不包含，与 Python range 习惯一致，例如 start=1, end=3 提取第1,2页)
         (注意：请确认您的调用逻辑，如果 end 是包含的，请在下方 indices 计算时调整)
    """
    offset = 0  # 默认不偏移，如果需要自动计算偏移，可调用 compute_page_offset
    src_doc = None
    out_doc = None
    
    try:
        # 1. 使用自动修复功能打开源文件
        src_doc = open_pdf_auto_repair(pdf_path)
        if not src_doc:
            print(f"❌ 无法打开或修复文件: {pdf_path}")
            return False

        # 2. 转换页码为物理索引 (0-based)
        # 用户传入的 start 是 1-based，所以减 1
        start_idx = start + offset - 1
        # 用户传入的 end 是 1-based 且通常作为 range 的结尾 (exclusive)，所以减 1
        end_idx = end + offset - 1
        
        # 边界检查
        if start_idx < 0: start_idx = 0
        if end_idx > src_doc.page_count: end_idx = src_doc.page_count
        
        if start_idx >= end_idx:
            print(f"⚠ 页码范围无效或为空: {start}-{end} (Indices: {start_idx}-{end_idx})")
            return False

        # 3. 提取并保存
        out_doc = fitz.open()
        
        # fitz.insert_pdf 的参数 from_page 是包含的，to_page 也是包含的
        # 我们要提取 [start_idx, end_idx) 区间
        # 所以 to_page 应该是 end_idx - 1
        out_doc.insert_pdf(src_doc, from_page=start_idx, to_page=end_idx - 1)
        
        out_doc.save(output_path)
        print(f"自定义处理完成 -> {os.path.basename(output_path)}")
        return True

    except Exception as e:
        print(f"❌ 自定义提取失败: {e}")
        return False
    finally:
        # 确保关闭文件句柄
        if src_doc: src_doc.close()
        if out_doc: out_doc.close()

def parser_file(filename):
    """
    解析文件名，返回字典。
    """
    city = "未知城市"
    district = "-"
    unit = ""
    
    # 1. 强力清洗：去掉 .pdf 和所有可能的任务后缀
    clean_name = filename.replace(".pdf", "")
    
    if '_' in clean_name:
        clean_name = clean_name.split('_')[0]
    
    # === 策略 A: 处理短横线格式 (City-District) ===
    if '-' in clean_name:
        parts = clean_name.split('-')
        if len(parts) >= 1: city = parts[0]
        if len(parts) >= 2: district = parts[1]
        if len(parts) >= 3: unit = parts[2]
            
        return {
            "原始文件名": filename,
            "文件名": clean_name,  # 直接使用清洗后的名字
            "城市": city,
            "地区/县": district,
            "详细单元": unit if unit else "无"
        }
        
def extract_info(filename):
    """
    解析文件名，返回字典。
    兼容两种模式：
    1. 已清洗过的格式：'东莞-凤岗_landuse.pdf' -> 提取为 东莞, 凤岗
    2. 原始长文件名：'东莞市凤岗镇全域...pdf' -> 提取为 东莞市, 凤岗镇
    """
    city = "未知城市"
    district = "-" 
    unit = ""
    
    # 1. 基础清洗：去掉 .pdf
    clean_name = filename.replace(".pdf", "")
    
    # 2. 剥离任务后缀 (这是关键！把 _landuse, _issue 等去掉，还原成 地区-区县)
    # 正则解释：匹配下划线开头，后面跟着任务名，直到字符串结束
    clean_name = re.sub(r'(_landuse|_issue|_potential|_project|_spatial|_data|_cropped|_manual).*$', '', 
                        clean_name,
                        flags=re.IGNORECASE)

    # === 策略 A: 处理已经清洗过的短横线格式 (City-District-Unit) ===
    # 如果名字里有横线，说明这是我们自己生成的文件，直接切分即可
    if '-' in clean_name:
        parts = clean_name.split('-')
        # 只有一段： '东莞'
        if len(parts) >= 1:
            city = parts[0]
        # 有两段： '东莞-凤岗'
        if len(parts) >= 2:
            district = parts[1]
        # 有三段： '东莞-凤岗-官井头'
        if len(parts) >= 3:
            unit = parts[2]
            
        return {
            "原始文件名": filename,
            "文件名": clean_name, # 用于显示的纯地区名
            "城市": city,
            "地区/县": district if district else "-",
            "详细单元": unit if unit else "无"
        }

    # === 策略 B: 处理原始长文件名 (Regex 匹配) ===
    # 匹配规则：以"市"结尾的前缀 + 中间区域名 + 关键词
    match = re.search(r'^(.+?市)(.+?)(?:全域|实施|项目|永久|土地)', clean_name)
    if match:
        city = match.group(1)
        district = match.group(2)
    else:
        # 特殊规则兜底
        if "广州市-湛江市" in filename:
            city = "广州湛江合作园"
            district = "奋勇高新区"
        elif "市" in clean_name and city == "未知城市":
            # 最后的尝试：按“市”字切分
            try:
                idx = clean_name.index("市")
                city = clean_name[:idx+1]
                district = clean_name[idx+1:]
            except: pass
    # 提取括号内容
    unit_match = re.search(r'[（\(](.+?)[）\)]', filename)
    if unit_match:
        unit = unit_match.group(1)
    
    short_city = city.replace("市", "")
    short_district = district
    
    # 清洗区县后缀
    for suffix in ["市", "区", "县", "镇", "街道", "自治县", "新区", "管理区", "开发区", "特别合作区"]:
        if short_district.endswith(suffix) and len(short_district) > len(suffix):
            if short_district == "南区" and suffix == "区": continue
            short_district = short_district.replace(suffix, "")
            break
            
    short_unit = unit
    for suffix in ["实施单元", "单元", "镇", "街道", "片区", "实施方案"]:
        short_unit = short_unit.replace(suffix, "")
    
    # 组装标准化名字
    components = [short_city]
    if short_district and short_district != "-": components.append(short_district)
    if short_unit: components.append(short_unit)
    
    new_name = "-".join(components)

    return {
        "原始文件名": filename,
        "文件名": new_name,
        "城市": city,
        "地区/县": short_district if short_district else "-",
        "详细单元": unit if unit else "无"
    }
    
    
def extract_pages_by_keywords(pdf_path, output_path, keyword_pattern_str):
    """
    扫描每一页内容，匹配关键词（支持正则表达式）。
    如果找到标题，且后续页面是连续表格，会自动合并后续页面。
    """
    pages_to_save = []
    in_table = False
    
    try:
        search_pattern = re.compile(keyword_pattern_str)
    except:
        # 如果用户输入的不是正则，转为普通包含匹配
        search_pattern = re.compile(re.escape(keyword_pattern_str))

    src_doc = None
    out_doc = None
    
    try:
        src_doc = open_pdf_auto_repair(pdf_path)
        if not src_doc: return False
        
        for page_index, page in enumerate(src_doc):
            text = page.get_text() or ""
            
            # 判断是否包含标题
            has_title = bool(search_pattern.search(text))
            
            # 判断是否有表格 (PyMuPDF 功能)
            # find_tables 比较耗时，仅在必要时调用或每一页调用
            tables = page.find_tables()
            has_table = len(tables.tables) > 0
            
            if has_title:
                in_table = True
                pages_to_save.append(page_index)
            elif in_table and has_table:
                # 如果处于"表格连续模式"且当前页也有表格，判定为跨页表格
                pages_to_save.append(page_index)
            else:
                # 断开连续
                in_table = False
        
        if not pages_to_save:
            return False
            
        # 保存结果
        out_doc = fitz.open()
        for p_idx in pages_to_save:
            out_doc.insert_pdf(src_doc, from_page=p_idx, to_page=p_idx)
            
        out_doc.save(output_path)
        return True

    except Exception as e:
        print(f"关键词提取失败: {e}")
        return False
    finally:
        if src_doc: src_doc.close()
        if out_doc: out_doc.close()


        
def dict_save2csv(data: dict, save_path: str):
    """
    将字典数据保存为 CSV 文件
    """
    import pandas as pd
    df = pd.DataFrame.from_dict(data, orient='index')
    df.reset_index(inplace=True)
    df.rename(columns={'index': '地区'}, inplace=True)
    df.to_csv(save_path, index=False, encoding='utf-8-sig')
    print(f"数据已保存到 {save_path}")
