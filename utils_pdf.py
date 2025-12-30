import fitz  # PyMuPDF
import re
import pikepdf
import io
import os

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

        # 清洗与正则
        clean_toc_text = re.sub(r"[…\.．]{2,}", " ", toc_text)
        clean_toc_text = re.sub(r'(?m)^\s*([（(]?\s*[\d一二三四五六七八九十][\d.．)）]*[、]?)\s*\n', r'\1 ', clean_toc_text)
        pattern = r"(?m)^\s*([（(]?\s*[\d一二三四五六七八九十].*?)\s+(\d+)\s*$"
        matches = re.findall(pattern, clean_toc_text)

        toc = []
        for title, page in matches:
            clean_title = title.strip().rstrip('.').rstrip()
            compact_title = re.sub(r"\s+", "", clean_title)
            toc.append((compact_title, int(page)))
            
        # 查找逻辑
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
    clean_name = re.sub(r'(_landuse|_issue|_potential|_project|_spatial|_data|_cropped|_manual).*$', '', clean_name)

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
    
    # --- 数据清洗与格式化 (针对原始文件名) ---
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
    
    # 编译正则
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
