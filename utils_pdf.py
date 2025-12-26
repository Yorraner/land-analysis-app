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