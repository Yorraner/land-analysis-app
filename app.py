import streamlit as st
import os
import io
import pandas as pd
import numpy as np
import time
import json
import zipfile
import time
import shutil
from utils.utils_pdf import extract_section_to_pdf, extract_section_to_pdf_self, \
    extract_info,parser_file,extract_pages_by_keywords,dict_save2csv
from utils.api_client import CozeClient, get_mock_data, WORKFLOW_CONFIG 
from utils.utils_fusion import unify_and_concatenate, preprocess_X 
from utils.utils_vis import plot_heatmap ,plot_horizontal_bars_from_df,plot_category_radar_chart,plot_clusters
from utils.utils_parse import process_raw_data
from utils.algorithm import clustering_kmeans_with_entropy_expert,build_weight_vector
from utils.login import check_password

# from utils_parsers import process_raw_data
# from utils_fusion import unify_and_concatenate
bg_path = "imgs/bg1.png"
json_path="./users.json"
# === login ===
if not check_password(bg_path,json_path):
    st.stop()
# === 页面配置 ===
st.set_page_config(page_title="土地整治智能分析平台", layout="wide")
st.title("🏗️ 土地整治文档智能分类系统")

# === 临时文件管理 ===
TEMP_DIR = "temp_workspace"
DIRS = {
    "upload": os.path.join(TEMP_DIR, "1_uploads"),
    "crop": os.path.join(TEMP_DIR, "2_cropped"),
    "raw": os.path.join(TEMP_DIR, "3_raw_data"),
    "result": os.path.join(TEMP_DIR, "4_results"), 
    "final": os.path.join(TEMP_DIR, "5_final")
}
TEMPLATE_COLUMNS = {
    "spatial": ["地区", "永农调入规模（公顷）", "永农调出规模（公顷）", "城镇开发调入规模（公顷）", "城镇开发调出规模（公顷）", "规划单元空间调整打分（最高5分）"],
    "potential": ["地区", "垦造水田潜力", "新增耕地潜力", "耕地“非粮化”整治潜力","耕地恢复潜力", "高标准农田建设潜力","耕地提质改造潜力",
                  "补充耕地潜力","耕地集中整治区建设潜力","低效工业用地腾退潜力","存量低效用地潜力","矿山修复潜力", "红树林保护潜力","低效用地再开发潜力",
                  "三旧改造潜力","城镇低效用地再开发潜力","建设用地增减挂钩（拆旧复垦）潜力",	"土壤整治潜力","造林绿化潜力","流域生态修复潜力"],
    "issue": ["地区", "耕地碎片化", "产业发展与用地供给矛盾","人地协调矛盾","人与自然的矛盾","低效用地问题"],
    "LandUse": ["地区", "农用地", "建设用地", "生态保护", "林地占比"],
    "project": ["地区", "农用地整理类项目_数量", "农用地整理类项目_投资", "农用地整理类项目_规模",
                "建设用地整理类项目_数量", 	"建设用地整理类项目_投资", 	"建设用地整理类项目_规模", 	
                "生态保护修复类项目_数量", 	"生态保护修复类项目_投资", 	"生态保护修复类项目_规模", 	
                "乡村风貌提升和历史文化保护类项目_数量", "乡村风貌提升和历史文化保护类项目_投资", "乡村风貌提升和历史文化保护类项目_规模"	, 
                "公共服务与基础设施建设类项目_数量"	"公共服务与基础设施建设类项目_投资", "公共服务与基础设施建设类项目_规模"	, 
                "产业导入类项目_数量", 	"产业导入类项目_投资", 	"产业导入类项目_规模", 
                "其他类项目_数量", 	"其他类项目_投资", 	"其他类项目_规模", ],
    "default": ["地区", "指标1", "指标2", "指标3"]
}


# 初始化目录
for d in DIRS.values():
    if not os.path.exists(d): os.makedirs(d)

# === 侧边栏：流程控制 ===
with st.sidebar:
    st.header("工作流导航")
    step = st.radio("选择步骤", [
        "1. 文档上传与裁剪", 
        "2. 大模型数据获取", 
        "3. 数据解析", 
        "4. 数据融合&展示",
        "5. 数据分类与导出"
    ])
    st.divider()
    if st.button("清理临时文件"):
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
            for d in DIRS.values():
                if not os.path.exists(d): os.makedirs(d)
        st.success("已清理缓存")

# 定义全局任务字典
TASK_DICT={
    "自然资源禀赋":"LandUse",
    "存在问题":"issue",
    "整治潜力":"potential",
    "子项目":"project",
    "空间布局":"spatial"
}

def render_file_manager(dir_path, title="结果文件管理", file_ext=".csv", key_prefix="common"):
    """
    通用文件管理组件：列表、预览、下载、删除
    """
    st.divider()
    st.subheader(f"📂 {title}")
    
    if not os.path.exists(dir_path):
        st.info("暂无文件生成。")
        return
    # scan files
    # files = [f for f in os.listdir(dir_path) if f.endswith(file_ext)]
    files =  os.listdir(dir_path)
    files.sort(key=lambda x: os.path.getmtime(os.path.join(dir_path, x)), reverse=True) # 按时间倒序

    if files:
        # 1. file table displayview
        view_files = files
        if  key_prefix =="step3":
            view_files = [i for i in files if i.startswith('parsed') and not i.endswith("matrix.csv")]
        elif  key_prefix =="step4":
            view_files = [i for i in files if i.startswith('fusion')]
        df_files = pd.DataFrame(view_files, columns=["文件名"],index=range(1, len(view_files)+1))
        st.dataframe(df_files, width="stretch", height=150)
        
        # 2. file delete
        with st.expander("🗑️ 管理/删除文件"):
            files_to_del = st.multiselect("选择要删除的文件", files, key=f"{key_prefix}_del_multi")
            if st.button("确认删除", key=f"{key_prefix}_del_btn"):
                for f in files_to_del:
                    try: os.remove(os.path.join(dir_path, f))
                    except: pass
                st.success(f"已删除 {len(files_to_del)} 个文件")
                time.sleep(1)
                st.rerun()

        # 3. preview & single download
        c1, c2 = st.columns([2, 1])
        with c1:
            select_files = files
            if  key_prefix =="step3":
                select_files = [i for i in files if i.startswith('parsed') ]
            elif  key_prefix =="step4":
                select_files = [i for i in files if not i.startswith('parsed')]
            sel_file = st.selectbox("选择文件预览:", select_files, key=f"{key_prefix}_sel")
            if sel_file:
                file_path = os.path.join(dir_path, sel_file)
                file_ext = os.path.splitext(sel_file)[1].lower()
                if file_ext == ".csv":
                    try:
                        try: df = pd.read_csv(file_path)
                        except: df = pd.read_csv(file_path, encoding='gbk')
                        st.write(f"📊 `{sel_file}` :")
                        df_preview = df.head()
                        df_preview.index = df_preview.index+1
                        st.dataframe(df_preview)
                    except Exception as e:
                        st.error(f"读取失败: {e}")
                elif file_ext == ".png":
                    st.caption("png 文件不支持直接预览，请下载查看。")
        with c2:
            if sel_file:
                file_path = os.path.join(dir_path, sel_file)
                with open(file_path, "rb") as f:
                    mime_type = "text/csv" if file_ext == ".csv" else "application/pdf"
                    st.download_button(
                        label=f"📥 下载 \
                        \n{sel_file}",
                        data=f,
                        file_name=sel_file,
                        mime=mime_type,
                        key=f"{key_prefix}_down_btn",
                        type="primary"
                    )           
        # 4. package download
        st.caption("📦 **批量下载**")
        c_dl1, c_dl2 = st.columns([2, 1])
        with c_dl1:
            # 1. 提供文件类型选择 (根据当前目录下的实际文件后缀自动生成选项)
            # 获取目录下所有文件的后缀
            available_exts = list(set([f.split('.')[-1] for f in files if '.' in f]))
            # 设置默认选中的类型
            default_exts = []
            if "csv" in available_exts: default_exts.append("csv")
            # if "png" in available_exts: default_exts.append("png") # 如果有图，默认也勾选
            selected_exts = st.multiselect(
                "选择要打包的文件类型:",
                options=available_exts,
                default=default_exts,
                key=f"{key_prefix}_ext_sel"
            )
        with c_dl2:
            # 2. 根据步骤 (Key Prefix) 和 选中的类型 进行双重过滤
            files_to_zip = []
            
            for f in files:
                # 获取文件后缀
                f_ext = f.split('.')[-1]
                if f_ext in selected_exts:
                    if key_prefix == "step3":
                        # Step 3 只下载以 'parsed' 开头的文件
                        if f.startswith('parsed'):
                            files_to_zip.append(f)
                    
                    elif key_prefix == "step4":
                        files_to_zip.append(f)
                        
                    elif key_prefix == "step5":
                        files_to_zip.append(f)
                    
                    else:
                        # 其他情况，只要后缀匹配就加入
                        files_to_zip.append(f)

            # 3. 执行打包
            zip_name = f"selected_{key_prefix}_files.zip"
            zip_path = os.path.join(TEMP_DIR, zip_name) # 确保 TEMP_DIR 已定义

            # 只有当有文件被选中时才显示下载按钮
            if files_to_zip:
                # 创建 ZIP
                with zipfile.ZipFile(zip_path, 'w') as zf:
                    for f in files_to_zip:
                        # dir_path 是传入该函数的当前目录路径
                        full_path = os.path.join(dir_path, f)
                        zf.write(full_path, f)
                
                # 显示按钮
                with open(zip_path, "rb") as f:
                    st.download_button(
                        f"⬇️ 下载选中文件 ({len(files_to_zip)}个)", 
                        f, 
                        zip_name, 
                        "application/zip", 
                        key=f"{key_prefix}_zip",
                        type="primary"
                    )
            else:
                st.caption("⚠️ 没有匹配的文件可下载")
        
    
    else:
        st.info(f"当前任务的目录为空 ({dir_path})")
# ========================================================
# 1. 上传与裁剪
# ========================================================
if step == "1. 文档上传与裁剪":
    st.header("📄 步骤 1: PDF 文档处理")
    tab1, tab2 = st.tabs(["🚀 批量自动裁剪", "🛠️ 手动裁剪修复"])
    with tab1:
        st.markdown("上传原始文档，系统将根据提取模式自动裁剪出关键页面。")
        st.info("💡 提示：默认支持最大 1GB 文件。建议分批上传。")
        source_option = st.radio("选择文件来源", ["📤 上传新文件", "📂 使用服务器已存在文件"])
        target_files = [] 
        if source_option == "📤 上传新文件":
            uploaded_files = st.file_uploader(
                "上传 PDF 文件", 
                type=["pdf"], 
                accept_multiple_files=True, 
                key="auto_uploader"
            )
            
            if uploaded_files:
                save_status = st.empty()
                save_status.text("正在保存文件到硬盘...")
                
                saved_count = 0
                for f in uploaded_files:
                    file_path = os.path.join(DIRS["upload"], f.name)
                    with open(file_path, "wb") as buffer:
                        buffer.write(f.getbuffer()) 
                    saved_count += 1
                    target_files.append(file_path)
                save_status.success(f"✅ 已保存 {saved_count} 个文件到服务器缓存。")
        else:
            if os.path.exists(DIRS["upload"]):
                existing_pdfs = [f for f in os.listdir(DIRS["upload"]) if f.endswith(".pdf")]
                if existing_pdfs:
                    st.success(f"📂 在 `1_uploads` 目录中找到 {len(existing_pdfs)} 个 PDF 文件。")
                    
                    # 让用户选择要处理哪些 (默认全选)
                    selected_existing = st.multiselect(
                        "选择要处理的文件", 
                        existing_pdfs, 
                        default=existing_pdfs
                    )
                    # 构造完整路径
                    for f in selected_existing:
                        target_files.append(os.path.join(DIRS["upload"], f))
                else:
                    st.warning("⚠️ 目录为空，请先上传文件。")
        st.divider()
        col1, col2 = st.columns([1, 1])
        with col1:
            crop_task_type = st.selectbox(
                "选择要提取的数据类型", 
                list(TASK_DICT.keys()) 
            )
        with col2:
            default_kw = ""
            algo_type = "TOC" 
            if "自然资源禀赋" in crop_task_type:
                 # default_kw = r"(土地利用.*表|表.*土地利用.*表)" 
                # default_kw = r"(?s)(?:表\s*[\d\-\.]*\s*)?土地\s*利用.*(?:统计|现状|)?\s*表"
                # default_kw = r"(?s)(?:表\s*[\d\-\.]*\s*)?土\s*地\s*利\s*用.*表"
                default_kw = r"(?s)(?:表\s*[\d\-\.]*\s*)?(?:土\s*地|地\s*类).*(?:利\s*用|现\s*状|统\s*计).*表"
                algo_type = "Content"
            elif "存在问题" in crop_task_type:
                default_kw = "存在问题"
            elif "整治潜力" in crop_task_type:
                default_kw = "整治可行性分析"
            elif "子项目" in crop_task_type:
                default_kw = "子项目安排"
            elif "空间布局" in crop_task_type:
                default_kw = "空间布局优化"
            
            keyword = st.text_input("提取关键词 (支持正则)", value=default_kw)
            
            if algo_type == "Content" or crop_task_type == "自定义全文搜索":
                st.caption("ℹ️ 模式：**全文关键词扫描**")
                use_content_mode = True
            else:
                st.caption("ℹ️ 模式：**目录章节匹配**")
                use_content_mode = False
        
        # --- 开始处理 ---
        error_files = []
        if st.button("开始自动裁剪", type="primary"):
            if not target_files:
                st.error("没有待处理的文件！")
            else:
                bar = st.progress(0)
                status = st.empty()
                success_count = 0
                total_files = len(target_files)
                import gc 

                for i, src_path in enumerate(target_files):
                    f_name = os.path.basename(src_path)
                    status.text(f"正在处理 ({i+1}/{total_files}): {f_name} ...")
                    
                    try:
                        info = extract_info(f_name)
                        clean_region_name = info["文件名"]
                        
                        task_suffix = "data"
                        if crop_task_type in TASK_DICT:
                            task_suffix = TASK_DICT[crop_task_type]
                        else:
                            task_suffix = keyword.replace("*", "")[:5]

                        dst_name = f"{clean_region_name}_{task_suffix}.pdf"
                        dst_path = os.path.join(DIRS["crop"], dst_name)
                        
                        # 3. 执行裁剪
                        is_ok = False
                        if use_content_mode:
                            is_ok = extract_pages_by_keywords(src_path, dst_path, keyword)
                        else:
                            is_ok = extract_section_to_pdf(src_path, dst_path, keyword)
                        
                        if is_ok: 
                            success_count += 1
                        else:
                            error_files.append(f_name)
                            
                    except Exception as e:
                        print(f"处理出错 {f_name}: {e}")
                        error_files.append(f_name)
                    
                    bar.progress((i + 1) / total_files)
                    
                    # 手动清理内存
                    gc.collect() 
                if success_count == total_files: 
                    st.success(f"✅ 全部完成！成功 {success_count} 个。")
                else: 
                    st.warning(f"⚠️ 完成，但有 {len(error_files)} 个失败。失败列表：{error_files}")

    with tab2:
        st.info("如果自动裁剪失败，可在此手动指定页码修复。")
        existing_files = [f for f in os.listdir(DIRS["upload"]) if f.endswith(".pdf")]
        
        c1, c2 = st.columns([1, 2])
        with c1:
            # 手动上传单个作为补充
            manual_file = st.file_uploader("上传新文件", type=["pdf"], key="manual_uploader")
        with c2:
            # 或者从已有列表选
            sel_file = st.selectbox("或选择已上传的文件", ["--请选择--"] + existing_files)
        
        target_file_path = None
        if manual_file:
            target_file_path = os.path.join(DIRS["upload"], manual_file.name)
            with open(target_file_path, "wb") as f: f.write(manual_file.getbuffer())
        elif sel_file != "--请选择--":
            target_file_path = os.path.join(DIRS["upload"], sel_file)
        
        if target_file_path:
            st.write(f"当前选中: `{os.path.basename(target_file_path)}`")
            c_m1, c_m2 = st.columns(2)
            with c_m1:
                manual_task_type = st.selectbox(
                    "这是哪类数据？", list(TASK_DICT.keys()), key="manual_task_sel"
                )
            with c_m2:
                col_p1, col_p2 = st.columns(2)
                with col_p1: start_p = st.number_input("起始页码", 1, value=1)
                with col_p2: end_p = st.number_input("结束页码", 1, value=5)
            
            if st.button("✂️ 执行裁剪", type="primary"):
                f_name = os.path.basename(target_file_path)
                info = extract_info(f_name)
                task_suffix = TASK_DICT[manual_task_type]
                dst_name = f"{info['文件名']}_{task_suffix}_manual.pdf"
                dst_path = os.path.join(DIRS["crop"], dst_name)
                
                if extract_section_to_pdf_self(target_file_path, start_p, end_p, dst_path):
                    st.success(f"✅ 修复成功: {dst_name}")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("裁剪失败")

    st.divider()
    st.subheader("📂 结果文件管理")
    cropped_files = []
    if os.path.exists(DIRS["crop"]):
        cropped_files = [f for f in os.listdir(DIRS["crop"]) if f.endswith(".pdf")]
    
    if cropped_files:
        file_data = []
        for f in cropped_files:
            file_path = os.path.join(DIRS["crop"], f)
            file_size_bytes = os.path.getsize(file_path)
            stats = os.stat(file_path)
            if stats.st_size < 1024 * 1024:
                size_str = f"{stats.st_size / 1024:.1f} KB"
            else:
                size_str = f"{stats.st_size / (1024 * 1024):.2f} MB"
            time_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(stats.st_mtime))
            file_data.append({
                "选择": False,
                "📄 文件名称": f,
                "📄 大小": size_str,
                "🕒 修改时间": time_str,
                "_timestamp": stats.st_mtime 
            })
        file_data.sort(key=lambda x: x["_timestamp"], reverse=True)
        df_display = pd.DataFrame(file_data,index=range(1,len(file_data)+1)).drop(columns=["_timestamp"])

        edited_df = st.data_editor(
            df_display,
            column_config={
                "选择": st.column_config.CheckboxColumn("选中", help="勾选进行操作", width="small"),
                "📄 文件名称": st.column_config.TextColumn(width="large"), # 让文件名列宽一些
                "📄  文件大小": st.column_config.TextColumn(width="small"),
                "🕒 修改时间": st.column_config.TextColumn(width="medium"),
            },
            hide_index=True,
            width='content', 
            height=300 # 增加高度，避免滚动条太短
        )

        files_to_delete = edited_df[edited_df["选择"]]["📄 文件名称"].tolist()

        if files_to_delete:
            if st.button(f"🗑️ 删除选中的 {len(files_to_delete)} 个文件", type="primary"):
                success_num = 0
                for f_del in files_to_delete:
                    try:
                        os.remove(os.path.join(DIRS["crop"], f_del))
                        success_num += 1
                    except Exception as e:
                        st.error(f"删除失败 {f_del}: {e}")
                if success_num > 0:
                    st.success(f"已删除 {success_num} 个文件")
                    time.sleep(1)
                    st.rerun()
        
        with st.expander("🗑️ 管理/删除已处理文件"):
            def delete_callback():
                # 从 Session State 获取当前选中的文件
                files = st.session_state.get("files_to_delete_key", [])
                if not files:
                    return # 没选文件，直接返回
                success_num = 0
                fail_num = 0
                
                for f_del in files:
                    path_to_del = os.path.join(DIRS["crop"], f_del)
                    try:
                        if os.path.exists(path_to_del):
                            os.remove(path_to_del)
                            success_num += 1
                    except:
                        fail_num += 1
                
                st.session_state["delete_result_msg"] = (success_num, fail_num)
                
                st.session_state["files_to_delete_key"] = []

            c_btn1, c_btn2, c_space = st.columns([1, 1, 4])
            
            if c_btn1.button("✅ 全选"):
                st.session_state["files_to_delete_key"] = cropped_files
                st.rerun()        
            if c_btn2.button("⬜ 清空"):
                st.session_state["files_to_delete_key"] = []
                st.rerun()
            st.multiselect(
                "选择要删除的文件 (支持多选)", 
                cropped_files,
                key="files_to_delete_key" 
            )

            # --- 3. 删除按钮 (绑定回调) ---
            st.button("🚨 确认删除选中文件", type="primary", on_click=delete_callback)

            # --- 4. 显示操作结果 ---
            if "delete_result_msg" in st.session_state:
                s_count, f_count = st.session_state["delete_result_msg"]
                
                if s_count > 0:
                    st.success(f"✅ 已成功删除 {s_count} 个文件！")
                if f_count > 0:
                    st.warning(f"⚠️ {f_count} 个文件删除失败。")
                
                del st.session_state["delete_result_msg"]

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.subheader("📦 文件下载")
            source_dir = DIRS["crop"]
            all_pdfs = []
            if os.path.exists(source_dir):
                all_pdfs = [f for f in os.listdir(source_dir) if f.endswith(".pdf")]

            if not all_pdfs:
                st.info("暂无文件可下载")
            else:
                # 2. 创建筛选选项： ["所有文件"] + [TASK_DICT 的中文键名]
                download_options = ["所有文件"] + list(TASK_DICT.keys())
                
                # 让用户选择下载类型
                selected_type = st.selectbox(
                    "选择要下载的数据类型", 
                    download_options, 
                    key="download_type_selector"
                )

                # 3. 根据选择进行文件筛选
                files_to_zip = []
                zip_filename = "download.zip"

                if selected_type == "所有文件":
                    files_to_zip = all_pdfs
                    zip_filename = "all_cropped_files.zip"
                else:
                    # 获取对应的英文后缀，例如 "landuse"
                    suffix = TASK_DICT[selected_type]
                    # 筛选结尾匹配 _{suffix}.pdf 的文件
                    # 注意：我们要匹配如 "xxx_landuse.pdf"
                    target_ending = f"_{suffix}.pdf"
                    
                    files_to_zip = [f for f in all_pdfs if f.endswith(target_ending)]
                    zip_filename = f"{suffix}_files.zip"

                # 4. 生成并显示下载按钮
                if files_to_zip:
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                        for f_name in files_to_zip:
                            file_full_path = os.path.join(source_dir, f_name)
                            zf.write(file_full_path, arcname=f_name)
                    
                    # 将指针移回头部
                    zip_buffer.seek(0)

                    # 显示下载按钮
                    st.download_button(
                        label=f"📥 下载 {selected_type} ({len(files_to_zip)}个)",
                        data=zip_buffer,
                        file_name=zip_filename,
                        mime="application/zip",
                        type="primary"
                    )
                else:
                    st.warning(f"未找到属于“{selected_type}”类型的文件 (需包含 _{TASK_DICT.get(selected_type)} 后缀)")
# ========================================================
# 2. 数据提取 (API)
# ========================================================
elif step == "2. 大模型数据获取":
    st.header("🤖 步骤 2: 调用 AI 提取数据")
    col1, col2 = st.columns([1, 1])
    with col1:
        task_type = st.selectbox("选择分析任务类型", list(TASK_DICT.keys()))
    
    target_suffix = TASK_DICT.get(task_type)
    
    # 2. scan crop directory for relevant files
    if not os.path.exists(DIRS["crop"]):
        st.warning("⚠️ 裁剪目录不存在。")
    else:
        all_pdfs = [f for f in os.listdir(DIRS["crop"]) if f.endswith(".pdf")]
        
        target_files = [f for f in all_pdfs if f.endswith(f"_{target_suffix}.pdf")]
        
        if not target_files:
            st.warning(f"⚠️ 未找到后缀为 `_{target_suffix}.pdf` 的文件。")
            st.info("请回到 **步骤 1**，选择对应的数据类型并执行裁剪。")
        else:
            st.subheader(f"1️⃣ 待处理文件列表 ({len(target_files)} 个)")
            # preview file info
            file_info_list = []
            for f in target_files:
                info = extract_info(f)
                file_info_list.append(info)
            
            st.dataframe(
                pd.DataFrame(file_info_list,index=range(1,len(file_info_list)+1))[["原始文件名", "文件名", "城市", "地区/县"]], 
                height=150,
                width="stretch"
            )
            
            st.divider()
            st.subheader("2️⃣ 开始提取")
            
            if st.button("🚀 大模型解析，数据提取", type="primary"):
                results = []
                progress_bar = st.progress(0)
                log_container = st.container()
                
                client = None
                workflow_id = None

                client = CozeClient()
                workflow_id = WORKFLOW_CONFIG.get(task_type) # 直接用完整key或简单key，取决于api_client配置
                # 只遍历筛选后的文件
                for i, info in enumerate(file_info_list):
                    file_name = info["原始文件名"]
                    file_path = os.path.join(DIRS["crop"], file_name)
                    region_name = info["文件名"] 
                    with log_container:
                        status_expander = st.expander(f"🔄 正在处理: {region_name} ...", expanded=True)
                        with status_expander:
                            st.write(f"📄 文件: `{file_name}`")
                            raw_data = None
                            try:
                                    if not workflow_id:
                                        st.error(f"❌ 未配置 '{task_type}' 的 Workflow ID")
                                    else:
                                        st.write("📤 上传中...")
                                        file_id = client.upload_file(file_path)
                                        if file_id:
                                            st.write("🤖 分析中...")
                                            raw_data = client.run_workflow(workflow_id, file_id)
                                            if raw_data: st.success("✅ 成功")
                                            else: st.error("❌ 返回为空")
                                        else: st.error("❌ 上传失败")
                                        time.sleep(1)
                            except Exception as e:
                                st.error(f"❌ 异常: {e}")
                            
                            if raw_data:
                                try:
                                    json_data = json.loads(raw_data)
                                    if "output" in json_data:
                                        st.text_area("Output 文本", json_data["output"], height=200)
                                except: pass
                                results.append({
                                    "地区": region_name, 
                                    "rawdata": raw_data, 
                                    "原始文件名": file_name
                                })
                    
                    progress_bar.progress((i + 1) / len(target_files))
                
                st.success(f"🎉 处理完成！获取 {len(results)} 条数据。")
                
                if results:
                    df_result = pd.DataFrame(results)
                    # 保存文件名带上后缀，对应 Step 3 的读取
                    save_filename = f"coze_raw_output_{target_suffix}.csv"
                    save_path = os.path.join(DIRS["raw"], save_filename)
                    
                    df_result.to_csv(save_path, index=False, encoding='utf-8-sig')
                    st.write(f"数据已分类保存至: `{save_path}`")
                    st.dataframe(df_result.head())
            
    # 文件管理
    render_file_manager(DIRS["raw"], title="大模型获取的数据", file_ext=".csv", key_prefix="step2")
    
# # ========================================================
# # 3. 数据解析
# # ========================================================
elif step == "3. 数据解析":
    st.header("🧹 步骤 3: 结构化数据解析")
    tab1, tab2,tab3 = st.tabs(["⚙️ 解析原始数据", 
                               "📤 上传外部数据 (补充缺失项)",
                               "🔄 加载历史中间数据 (.pkl)"])
    
    # 正常数据解析
    with tab1:
        col1, col2 = st.columns([1, 1])
        with col1:
            parse_type = st.selectbox("选择解析数据类型", list(TASK_DICT.keys()))
        task_suffix = TASK_DICT[parse_type]
        raw_filename = f"coze_raw_output_{task_suffix}.csv"
        raw_file = os.path.join(DIRS["raw"], raw_filename)
        
        if not os.path.exists(raw_file):
            st.warning(f"⚠️ 未找到对应的数据文件：{raw_filename}。请先完成步骤 2 中该类型的提取。")
        else:
            df_raw = pd.read_csv(raw_file)
            df_raw_preview = df_raw.head()
            df_raw_preview.index = df_raw_preview.index + 1
            st.write(f"📂 读取数据源: `{raw_filename}`")
            st.write("原始数据预览:", df_raw_preview.head(3))
            
            if col2.button("数据解析", type="primary"):
                # 1. 调用 utils_parsers 中的处理函数
                # process_raw_data 会返回纯特征数据的 DataFrame (不含地区列)
                parsed_df = process_raw_data(df_raw, parse_type)
                
                # 2. 合并地区列 (确保数据对齐)
                # 关键：确保 parsed_df 的索引与 df_raw 一致，防止错位
                parsed_df.index = df_raw.index 
                
                # 使用 join 或者 concat (axis=1)
                # 只取 '地区' 列和新生成的特征列
                final_df = pd.concat([df_raw[['地区']], parsed_df], axis=1)
                
                # 3. 构造输出文件名 (parsed_landuse.csv, parsed_issue.csv ...)
                out_name = f"parsed_{task_suffix}.csv"
                save_path = os.path.join(DIRS["result"], out_name)
                
                # 4. 保存
                final_df.to_csv(save_path, index=False, encoding='utf-8-sig')
                
                st.success(f"✅ 解析成功！结果已保存至: {out_name}")
                st.dataframe(final_df.head())
    # 手动上传外部数据
    with tab2:
        st.markdown("""
        **功能说明：** 如果某些数据（如空间布局规划）无法通过 `PDF` 提取，或者您已经有整理好的 `Excel/CSV `数据，在此处上传。
        系统会自动将其保存为标准格式，以便后续步骤进行融合。
        """)
        c1, c2 = st.columns([1, 1])
        with c1:
            upload_type = st.selectbox("选择上传的数据类型", list(TASK_DICT.keys()), key="upload_type_sel")
            target_suffix = TASK_DICT[upload_type]
        with c2:
            # 生成模板下载
            st.write("📝 **数据格式要求：**")
            st.caption("必须包含 `地区` 列，其他列为特征数值。")
            # 获取对应的模板列名
            cols = TEMPLATE_COLUMNS.get(target_suffix, TEMPLATE_COLUMNS["default"])
            template_df = pd.DataFrame(columns=cols)
            template_csv = template_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(f"📥 下载 {upload_type} 模板", template_csv, f"template_{target_suffix}.csv", "text/csv")

        uploaded_ext = st.file_uploader("上传处理好的文件 (.csv / .xlsx)", type=["csv", "xlsx"])
        
        if uploaded_ext:
            try:
                if uploaded_ext.name.endswith('.csv'):
                    ext_df = pd.read_csv(uploaded_ext)
                else:
                    ext_df = pd.read_excel(uploaded_ext)
                if "地区" not in ext_df.columns:
                    st.error("❌ 上传失败：文件中缺少 `地区` 列！请参照模板格式。")
                    st.write("当前列名:", list(ext_df.columns))
                else:
                    # 预览
                    st.write("📊 数据预览:", ext_df.head())
                    if st.button("💾 确认并保存"):
                        target_name = f"parsed_{target_suffix}_manual.csv"
                        save_path = os.path.join(DIRS["result"], target_name)
                        ext_df.to_csv(save_path, index=False, encoding='utf-8-sig')
                        
                        st.success(f"✅ 文件已保存为: `{target_name}`")
                        st.info("💡 现在您可以前往 **步骤 4**，该文件将自动参与数据融合。")    
            except Exception as e:
                st.error(f"文件读取失败: {e}")
    with tab3:
        st.markdown("""
        **功能说明：** 如果您之前保存了处理过程中的 `.pkl` (Pickle) 文件，可以直接在此处恢复。
        系统会自动将其转换为标准格式，**您可以直接跳过解析步骤，直接进行步骤 4 的融合与步骤 5 的分类**。
        """)
        uploaded_pkl = st.file_uploader("上传处理好的 .pkl 字典文件", type=["pkl"], key="tab3_uploader")
        
        if uploaded_pkl:
            try:
                data_dict = pd.read_pickle(uploaded_pkl)
                required_keys = {'X', 'features', 'regions'}
                if isinstance(data_dict, dict) and required_keys.issubset(data_dict.keys()):
                    st.success("✅ 检测到合法的特征字典结构！")
                    regions = data_dict['regions']
                    feats = data_dict['features']
                    
                    st.write(f"📊 数据维度: {len(regions)} 个地区 × {len(feats)} 个特征")
                    # 此处需要进行更改需那种 norm
                    # 既然已经有 X_norm，我们允许用户选择是否直接使用它
                    use_norm_data = st.checkbox("使用已归一化的数据 (X_norm)", value=True, 
                                              help="如果选中，将使用 pkl 中的 X_norm 直接生成最终矩阵；否则使用 X 重新生成。")
                    matrix_data = preprocess_X(data_dict['X'], eps=1e-8, use_log=True) if use_norm_data  else data_dict['X']
                    if len(regions) == matrix_data.shape[0] and len(feats) == matrix_data.shape[1]:
                        df_reconstructed = pd.DataFrame(matrix_data, index=regions, columns=feats)
                        df_reconstructed.index.name = "地区"
                        
                        st.dataframe(df_reconstructed.head(3))
                        col_btn1, col_btn2 = st.columns([1,2])
                        with col_btn1:
                            if st.button("🚀 恢复为最终矩阵", type="primary"):
                                # === 核心操作：直接生成 Step 4 的产出文件 ===
                                # 保存为 parsed_final_matrix.csv，这样 Step 5 可以直接读取
                                histroy_files = "parsed_origion_matrix.csv"
                                history_x_files = "parsed_hist_matrix.csv"
                                save_path_final = os.path.join(DIRS["result"], histroy_files)
                                df_reconstructed.to_csv(save_path_final, encoding='utf-8-sig')
                                if 'X' in data_dict:
                                    df_raw_backup = pd.DataFrame(data_dict['X'], index=regions, columns=feats)
                                    df_raw_backup.index.name = "地区"
                                    df_raw_backup.to_csv(os.path.join(DIRS["result"],history_x_files ), encoding='utf-8-sig')
                                st.success(f"✅ 数据已恢复！")
                                st.info("💡 您现在可以直接点击侧边栏的 **'5. 数据分类与导出'** 进行分析。")
                    else:
                        st.error(f"❌ 维度不匹配：地区数 {len(regions)} vs 矩阵行数 {matrix_data.shape[0]}") 
                else:
                    st.error(f"❌ 未知的数据结构。Keys: {data_dict.keys() if isinstance(data_dict, dict) else type(data_dict)}")

            except Exception as e:
                st.error(f"❌ 读取出错: {e}")
    render_file_manager(DIRS["result"], title="已解析的结构化数据", file_ext=".csv", key_prefix="step3")
# # ========================================================
# # 4. 数据融合
# # ========================================================
elif step == "4. 数据融合&展示":
    st.header("🔗 步骤 4: 多源数据融合及可视化展示")
    # scan parser CSV files
    csvs = [f for f in os.listdir(DIRS["result"]) if not f.startswith("fusion")]
    norm_res_path = ""
    raw_res_path = ""
    if not csvs:
        st.warning("⚠️ 没有找到解析后的数据文件，请先完成步骤 3。")
    else:
        st.info("💡 提示：为了保证归一化索引正确，系统将按照 **[自然资源 -> 潜力 -> 空间 -> 问题 -> 项目]** 的顺序强制排序。")
        # === 核心逻辑：强制文件排序 ===
        # 定义期望的关键词顺序（与 preprocess_X 中的硬编码索引对应）
        # 1.自然资源: 0-3
        # 2.潜力: 4-22
        # 3.空间: 23-27
        # 4.问题: 28-32
        # 5.项目: 33+
        # 1. 定义核心任务后缀顺序
        strict_order_suffixes = ["LandUse", "potential", "spatial", "issue", "project"]
        history_filename = "parsed_hist_matrix.csv"
        
        # 2. Default Selection - only include those that exist
        default_files = []
        for suffix in strict_order_suffixes:
            target_name = f"parsed_{suffix}.csv"
            if target_name in csvs:
                default_files.append(target_name)
        has_history = history_filename in csvs
        # core files|fusion hist files
        col_sel1, col_sel2 = st.columns([2, 1])
        with col_sel1:
            selected_core = st.multiselect(  
            "选择要融合的文件 (默认仅选中 5 类核心数据)", 
            options=[f for f in csvs if f != history_filename], # 排除历史文件，防止混淆
            default=default_files,
            help="选择您刚刚从 PDF 解析出来的 parsed_*.csv 文件。"
            )
        use_history = False
        with col_sel2:
            st.write("📚 **历史数据融合**")
            use_history = False
            if has_history:
                use_history = st.checkbox(
                    "➕ 融合历史恢复数据", 
                    value=True, 
                    help=f"检测到 Step 3 恢复了 `{history_filename}`，勾选此项将其与新数据合并。"
                )
                if use_history:
                    st.caption(f"✅ 已包含: `{history_filename}`")
            else:
                st.caption("🚫 未检测到历史恢复数据 (pkl)")
        # 4. 构建最终待融合列表
        final_selected_files = default_files.copy()
        if not default_files:
            st.warning("⚠️ 未找到任何符合标准命名规范的核心文件（如 parsed_landuse.csv）。请检查步骤 3 是否已正确执行。")
        c1, c2 = st.columns([1, 2])
        with c1:
            use_log = st.checkbox("☑️ 启用对数变换", value=True, help="对面积/金额/数量列进行 Log(x+1) 变换，拉近长尾分布的差距，避免小数值在归一化后变为0。")
        with c2:
            start_btn = st.button("开始融合与归一化", type="primary")
        
        # output paths
        suffix = "_log" if use_log else ""
        norm_filename = f"fusion_final_matrix{suffix}.csv"
        raw_filename = f"fusion_raw_matrix.csv"
        
        norm_res_path = os.path.join(DIRS["result"], norm_filename)
        raw_res_path = os.path.join(DIRS["result"], raw_filename)
            
        if  start_btn:
            if not final_selected_files:
                st.error("请至少选择一个文件。")
            else:
                matrices, maps, names,all_feature_names = [], [], [],[]
                sorted_files = []   
                # process file combine
                for f in final_selected_files:
                    path = os.path.join(DIRS["result"], f)
                    df = pd.read_csv(path)
                    
                    region_col = df.columns[0]
                    df = df.set_index(region_col)
                    df_num = df.select_dtypes(include=['number']).fillna(0)
                    
                    matrices.append(df_num.values)
                    maps.append({name: i for i, name in enumerate(df_num.index)})
                    
                    feat_prefix = f.replace("parsed_", "").replace(".csv", "")
                    names.append(feat_prefix)
                    all_feature_names.extend([f"{feat_prefix}:{c}" for c in df_num.columns])

                regions, X_final, slices = unify_and_concatenate(matrices, maps, names)
                history_msg = ""
                # process history data
                if use_history:
                    hist_path = os.path.join(DIRS["result"], history_filename)
                    df_hist = pd.read_csv(hist_path)
                    region_his = df_hist["地区"].tolist()
                    df_hist = df_hist.set_index("地区")
                    
                    # regfion2index
                    df_hist_aligned = pd.DataFrame(index=df_hist.index)
                    maps = {name: i for i, name in enumerate(region_his)} 
                    # feature alignment
                    for target_col in all_feature_names:
                        raw_col_name = target_col.split(":")[-1] 
                        if raw_col_name in df_hist.columns:
                            df_hist_aligned[raw_col_name] = df_hist[raw_col_name]
                        elif raw_col_name.endswith('排序'):
                            issue_feature = raw_col_name.split('_')[0] 
                            df_hist_aligned[raw_col_name] = df_hist['存在_'+issue_feature]
                    df_hist_num = df_hist_aligned.fillna(0)
                    hist_matrix = df_hist_num.values
                    current_regions_set = set(region_his)
                    unique_indices = [i for i, r in enumerate(current_regions_set) if r not in regions]
                    if unique_indices:
                        unique_regions = [region_his[i] for i in unique_indices]
                        unique_matrix = hist_matrix[unique_indices] 
                        regions = regions + unique_regions
                        X_final = np.vstack([X_final, unique_matrix])
                        history_msg = f" (已包含 {len(unique_regions)} 个历史补全地区)"
                    else:
                        st.caption("ℹ️ 历史数据地区已全部存在，未新增行。")
                if len(regions) > 0:
                    st.success(f"✅ 融合成功！共 {len(regions)} 个地区{history_msg}，特征维度: {X_final.shape[1]}")
                    try:
                        raw_df = pd.DataFrame(X_final, index=regions, columns=all_feature_names)
                        raw_df.index.name = "地区"
                        raw_df.to_csv(raw_res_path, encoding='utf-8-sig', index_label="地区")
                        
                        st.info(f"正在处理... (Log变换: {use_log})")
                        X_norm = preprocess_X(X_final, use_log=use_log)
                        
                        final_df = pd.DataFrame(X_norm, index=regions, columns=all_feature_names)
                        final_df.index.name = "地区"
                        final_df.to_csv(norm_res_path, encoding='utf-8-sig', index_label="地区")
                        time.sleep(5)
                        st.rerun()
                    except Exception as e:
                            st.error(f"归一化失败: {e}")
                else:
                        st.error("融合失败：所选数据表之间没有公共地区。")                
    if os.path.exists(norm_res_path):
        st.divider()
        st.subheader("🎨 多维度可视化")
        # 1. 准备选项：自动扫描 result 目录
        vis_options = {}
        # 找最终矩阵 (根据你的文件名特征)
        final_files = [f for f in os.listdir(DIRS["result"]) if "fusion_final" in f]
        for f in final_files:
            vis_options[f"🏆 最终融合矩阵 ({f})"] = os.path.join(DIRS["result"], f)
        # 找其他分项数据
        sub_files = [f for f in os.listdir(DIRS["result"]) if "fusion_final" not in f and f.endswith(".csv")]
        no_vis_files = ['parsed_issue.csv','parsed_ptential.csv','parsed_potential.csv',]  # 这些文件不适合可视化
        vis_files = [f for f in sub_files if f not in no_vis_files ]
        for f in vis_files:
                vis_options[f"📄 分项数据: {f}"] = os.path.join(DIRS["result"], f)

        # 2. 用户选择
        c_vis1, c_vis2 = st.columns([2, 1])
        with c_vis1:
            selected_vis_key = st.selectbox("选择要展示的数据:", list(vis_options.keys()))
        
        target_path = vis_options[selected_vis_key]
        
        try:
            df_vis = pd.read_csv(target_path, index_col=0)
            # 仅保留数值列
            df_vis = df_vis.select_dtypes(include=['number'])

            if df_vis.empty:
                st.warning("数据为空，无法绘图")
            else:
                # === 核心判断逻辑 ===
                is_final_result = "最终融合" in selected_vis_key

                if is_final_result:
                    # Case A: 最终结果 -> 直接读取，原样绘制
                    # 你的预处理已经保证了它在 0-1 之间且没有 0 值
                    with c_vis2:
                        st.success("✅ 检测到预处理后的融合矩阵，已直接展示。")
                        # 这里不需要任何 Checkbox
                    
                    # 直接画图 (df_vis 已经是完美状态)
                    fig = plot_heatmap(df_vis.values, df_vis.index.tolist(), feature_names=df_vis.columns.tolist())
                    history_tag = "_with_history" if use_history else ""
                    fig.savefig(f"{DIRS['result']}/final_result_heatmap{suffix}{history_tag}.png", dpi=300, bbox_inches='tight')
                    st.pyplot(fig)
                else:
                    with c_vis2:
                        # 1. Log
                        df_proc = np.log1p(np.maximum(df_vis, 0))
                        # 2. Min-Max
                        range_val = df_proc.max() - df_proc.min()
                        df_plot = df_proc.copy()
                        for col in df_proc.columns:
                            if range_val[col] > 1e-8:
                                df_plot[col] = (df_proc[col] - df_proc[col].min()) / range_val[col]
                            else:
                                df_plot[col] = 0
                        name = selected_vis_key.split(":")[-1].split('.')[0]
                        history_tag = "_with_history" if use_history else ""
                        fig = plot_heatmap(df_plot.values, df_plot.index.tolist(), feature_names=df_plot.columns.tolist())
                        fig.savefig(f"{DIRS['result']}/norm_{name}_heatmap{suffix}{history_tag}.png", dpi=300, bbox_inches='tight')
                    st.pyplot(fig)

        except Exception as e:
            st.error(f"绘图出错: {e}")
    
    # 这里展示的是 result 目录下的所有文件（包含 Step 3 的解析文件和 Step 4 的矩阵文件）               
    render_file_manager(DIRS["result"], title="融合及中间数据管理", file_ext=".csv", key_prefix="step4")
# ========================================================
# 5. 数据分类与导出
# ========================================================
elif step == "5. 数据分类与导出":
    st.header("📊 步骤 5: 智能分区分类")
    df_matrix = None
    data_version = st.radio(
            "选择要使用的矩阵版本:",
            options=["Log 对数变换版 (推荐)", "原始数值版"],
            index=0, # 默认选 Log
            help="对应步骤 4 生成的文件。\n- Log版: 文件名为 fusion_final_matrix_log.csv，适合聚类分析。\n- 原始版: 文件名为 fusion_final_matrix.csv，数值未压缩。"
        )
    # 2. 根据选择动态构造文件名
    if "Log" in data_version:
        target_filename = "fusion_final_matrix_log.csv"
    else:
        target_filename = "fusion_final_matrix.csv"
    auto_path = os.path.join(DIRS["result"], target_filename)
    if os.path.exists(auto_path):
        st.success(f"✅ 已检测到文件: {auto_path}")
        df_matrix = pd.read_csv(auto_path, index_col=0)
    else:
        st.warning("⚠️ 未找到自动生成的文件，请先完成步骤 4 或选择手动上传。")
    if df_matrix is not None:
        st.divider()
        st.write(f"📊 **当前数据:** {df_matrix.shape[0]} 个地区, {df_matrix.shape[1]} 个特征")
        with st.expander("查看数据详情"):
            st.dataframe(df_matrix.head())
        st.subheader("🛠️ 模型参数配置")
        col1, col2 = st.columns(2)
        with col1:
            n_clusters = st.slider("聚类类别数目 (K)", min_value=5, max_value=9, value=6)
        with col2:
            st.markdown("**⚖️ 权重设定 (专家打分)**")
            weight_settings = {}
            with st.expander("点击展开详细权重设置", expanded=True):
                c1, c2 = st.columns(2)
                with c1:
                    weight_settings["自然资源禀赋"] = st.number_input("1. 自然资源", value=5.0, step=0.1)
                with c2:
                    weight_settings["自然资源-布尔项"] = st.number_input("  ↳ 林地/布尔", value=0.5, step=0.1)
                weight_settings["潜力项数据"] = st.number_input("2. 潜力数据", value=0.4, step=0.1)
                c3, c4 = st.columns(2)
                with c3: weight_settings["空间布局"] = st.number_input("3. 空间布局", value=0.1, step=0.05)
                with c4: weight_settings["存在问题"] = st.number_input("4. 存在问题", value=0.1, step=0.05)
                weight_settings["子项目数据"] = st.number_input("5. 子项目", value=0.05, step=0.01)
        c1 = st.columns(1)[0]
        with c1:
            # 给按钮一个唯一的 key
            start_btn = st.button("🚀 开始聚类分析", type="primary", key="btn_start_cluster")
        # 3. algorithm
        if start_btn:
            try:
                total_feats = df_matrix.shape[1]
                weights_vec = build_weight_vector(weight_settings, df_matrix.columns)
                print(f"权重向量形状: {weights_vec.shape}, 特征列数: {len(df_matrix.columns)}")
                with st.spinner("正在进行熵权专家聚类..."):
                    df_result, feature_imp, combined_weights, centroids, labels = \
                    clustering_kmeans_with_entropy_expert(
                            df_matrix.values, 
                            df_matrix.index.tolist(), 
                            expert_weights=weights_vec, 
                            n_clusters=n_clusters,
                            path=DIRS["final"]
                        )
                    print('df result',df_result)
                    df_result["Cluster"] = labels + 1
                    # state save
                    st.session_state['cluster_done'] = True
                    st.session_state['cluster_labels'] = labels
                    st.session_state['cluster_centroids'] = centroids
                    st.session_state['cluster_df'] = df_result
                    st.session_state['cluster_weights'] = combined_weights
                    st.success("✅ 聚类完成！")
            except Exception as e:
                st.error(f"聚类失败: {e}")
        if st.session_state.get('cluster_done', False):
            df_result = st.session_state['cluster_df']
            centroids = st.session_state['cluster_centroids']
            labels = st.session_state['cluster_labels']
            combined_weights = st.session_state.get('cluster_weights')
            
            st.divider()
            tab_res1, tab_res2, tab_res3 = st.tabs(["📋 结果总表", "🕸️ 类别特征分布(雷达图)", "📊 地区概率分布(条形图)"])
            with tab_res1:
                st.dataframe(df_result)
                st.download_button("📥 下载详细结果 Excel", 
                                    data=df_result.to_csv().encode('utf-8-sig'),
                                    file_name="clustering_result_full.csv")
            with tab_res2:
                    st.subheader("各类别主要关注特征")
                    # 1. 准备权重
                    if isinstance(combined_weights, pd.Series):
                        analysis_weights = combined_weights.values
                    else:
                        analysis_weights = combined_weights
                    if analysis_weights.shape[0] != df_matrix.shape[1]:
                         st.error(f"权重维度 {analysis_weights.shape} 与特征数 {df_matrix.shape[1]} 不符")
                    else:
                        # 2. 准备容器
                        # features = df_matrix.columns.tolist() # 确保拿到特征名列表
                        features = df_matrix.columns
                        category_feature_attention = pd.DataFrame(
                            index=features, 
                            columns=[f"Cluster_{i+1}" for i in range(n_clusters)]
                        )
                        # 3. 核心计算循环
                        # centroids 是 (n_clusters, n_features) 的 numpy 数组
                        for k in range(n_clusters):
                            # 获取第 k 类的中心点坐标 (归一化后的平均值)
                            cluster_center_profile = centroids[k]
                            # === 核心公式：中心值 × 权重 ===
                           
                            # cluster_profile = cluster_center_profile * analysis_weights
                            cluster_profile = cluster_center_profile
                            # 存入 DataFrame
                            category_feature_attention[f"Cluster_{k+1}"] = cluster_profile
                        # 4. 调用绘图
                        try:
                            fig_radar = plot_category_radar_chart(category_feature_attention)
                            st.pyplot(fig_radar)
                            save_radar_path = os.path.join(DIRS["final"], f"{n_clusters}_category_feature_radar.png")
                            fig_radar.savefig(save_radar_path, dpi=300, bbox_inches='tight')
                            
                        except Exception as e_plot:
                            st.error(f"雷达图绘制失败: {e_plot}")

                        # 5. 展示数据表格
                        with st.expander("特征注意力数值详情"):
                            st.markdown("#### 🏆 各类别关注度 Top 10 特征")
                            st.caption("格式说明：特征名称 (注意力分值)")
                            top_n = 10
                            rank_data = {}
                            for col in category_feature_attention.columns:
                                # 1. 对每一列进行降序排列
                                top_series = category_feature_attention[col].sort_values(ascending=False).head(top_n)
                                
                                # 2. 格式化为字符串: "特征名 (0.123)"
                                formatted_vals = [
                                    f"{feat} ({val:.4f})" 
                                    for feat, val in top_series.items()
                                ]
                                # 3. 防止特征总数少于10个导致长度不一致
                                while len(formatted_vals) < top_n:
                                    formatted_vals.append("-")
                                    
                                rank_data[col] = formatted_vals
                            # 4. 构建排名 DataFrame
                            df_rank = pd.DataFrame(rank_data)
                            df_rank.index = [f"No.{i+1}" for i in range(top_n)] # 设置行索引为 No.1 ~ No.10
                            # 展示排名表
                            st.dataframe(df_rank, width='content')
                           
            with tab_res3:
                    st.subheader("各地区归属概率可视化")
                    
                    with st.expander("🛠️ 视图设置 (地区过多,筛选)", expanded=True):
                        c_view1, c_view2 = st.columns([1, 2])
                        with c_view1:
                            # 1. 选择显示模式
                            view_mode = st.radio(
                                "选择展示范围:", 
                                ["🏆 仅展示前 N 个 (预览)", "🔍 手动搜索特定地区", "📄 全量展示 (可能较长)"],
                                index=0 # 默认只看前 N 个，防止刷屏
                            )
                        with c_view2:
                            # 2. 根据模式显示不同控件
                            df_to_plot = df_result.copy()
                            
                            if "前 N 个" in view_mode:
                                # 默认展示 20 个，最大不超过总数
                                max_val = len(df_result)
                                default_val = min(20, max_val)
                                top_n = st.slider("选择展示的地区数量:", min_value=5, max_value=max_val, value=default_val)
                                
                                # 截取前 N 行 (假设 df_result 已经排好序，如果没有，可以先 sort_index 或 sort_values)
                                df_to_plot = df_result.head(top_n)
                                st.caption(f"当前展示: 第 1 至 {top_n} 个地区")
                                
                            elif "手动搜索" in view_mode:
                                all_regions = df_result.index.tolist()
                                selected_regions = st.multiselect(
                                    "输入或选择要查看的地区:", 
                                    options=all_regions,
                                    default=all_regions[:5] # 默认选前5个演示
                                )
                                if selected_regions:
                                    df_to_plot = df_result.loc[selected_regions]
                                else:
                                    st.warning("⚠️ 请至少选择一个地区。")
                                    df_to_plot = pd.DataFrame() # 空表
                                    
                            else: # 全量展示
                                st.info(f"正在展示全部 {len(df_result)} 个地区，图片可能较长。")
                                df_to_plot = df_result

                    if not df_to_plot.empty:
                        # 3. 计算动态图表高度 (优化体验)
                        # 假设每个条形占 0.4 英寸，基础高度 2 英寸
                        # 这样选 100 个地区时图会自动变长，不会挤在一起
                        dynamic_figsize = (10, max(4, len(df_to_plot) * 0.4))
                        # 调用你的绘图函数 (注意：如果你原来的函数不能传 figsize，这里可能需要传整个 df_to_plot)
                        # 假设 plot_horizontal_bars_from_df 接收 DataFrame 并返回 figure
                        # 如果你的 plot 函数内部写死了 figsize，可能需要稍微改一下 plot 函数让它自适应，
                        # 或者依靠 matplotlib 的自动布局。
                        try:
                            fig_bars = plot_horizontal_bars_from_df(df_to_plot)
                            
                            # 尝试调整当前 figure 的尺寸 (如果函数内部没锁死的话)
                            fig_bars.set_size_inches(dynamic_figsize)
                            
                            st.pyplot(fig_bars, width='content')
                            # 4. 保存
                            # 注意：这里保存的是"当前视图"的图片。
                            # 如果需要保存全量图片，可以在这里用 df_result 再画一次，或者告诉用户"所见即所得"
                            save_name = f"{n_clusters}_region_membership_bars_{view_mode}.png"
                            fig_bars_path = os.path.join(DIRS["final"], save_name)
                            fig_bars.savefig(fig_bars_path, dpi=300, bbox_inches='tight')
                            st.caption(f"💾 当前视图已保存为: `{save_name}`")  
                        except Exception as e:
                            st.error(f"绘图失败: {e}")
                    
                    st.success(f"🎉 所有分析结果（表格与图表）已自动保存至: `{DIRS['final']}`") 
    # === 展示文件管理 ===
    render_file_manager(DIRS["final"], title="最终成果", file_ext=".png", key_prefix="step5_img")