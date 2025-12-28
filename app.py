import streamlit as st
import os
import pandas as pd
import time
import json
import zipfile
import shutil
from utils_pdf import extract_section_to_pdf, extract_section_to_pdf_self, \
    extract_info,parser_file,extract_pages_by_keywords,dict_save2csv
from api_client import CozeClient, get_mock_data, WORKFLOW_CONFIG 
from utils_fusion import unify_and_concatenate, preprocess_X # 引入归一化函数
from utils_vis import plot_heatmap # 引入可视化
from utils_parse import process_raw_data

# from utils_parsers import process_raw_data
# from utils_fusion import unify_and_concatenate

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
    "potential": ["地区", "垦造水田潜力", "新增耕地潜力", "耕地恢复潜力", "高标准农田建设潜力", "矿山修复潜力", "红树林保护潜力"],
    "issue": ["地区", "耕地碎片化_排序", "耕地碎片化_说明", "低效用地问题_排序", "低效用地问题_说明"],
    "landuse": ["地区", "农用地", "建设用地", "生态保护", "林地占比"],
    "project": ["地区", "农用地整理类项目_数量", "农用地整理类项目_投资", "农用地整理类项目_规模"],
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
    "自然资源禀赋":"landuse",
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
    files = [f for f in os.listdir(dir_path) if f.endswith(file_ext)]
    files.sort(key=lambda x: os.path.getmtime(os.path.join(dir_path, x)), reverse=True) # 按时间倒序

    if files:
        # 1. file table display
        df_files = pd.DataFrame(files, columns=["文件名"])
        st.dataframe(df_files, use_container_width=True, height=150)
        
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
            sel_file = st.selectbox("选择文件预览:", files, key=f"{key_prefix}_sel")
            if sel_file:
                file_path = os.path.join(dir_path, sel_file)
                if file_ext == ".csv":
                    try:
                        try: df = pd.read_csv(file_path)
                        except: df = pd.read_csv(file_path, encoding='gbk')
                        st.write(f"📊 `{sel_file}` :")
                        st.dataframe(df.head())
                    except Exception as e:
                        st.error(f"读取失败: {e}")
                elif file_ext == ".pdf":
                    st.caption("PDF 文件不支持直接预览，请下载查看。")
        with c2:
            if sel_file:
                file_path = os.path.join(dir_path, sel_file)
                with open(file_path, "rb") as f:
                    mime_type = "text/csv" if file_ext == ".csv" else "application/pdf"
                    st.download_button(
                        label=f"📥 下载 {sel_file}",
                        data=f,
                        file_name=sel_file,
                        mime=mime_type,
                        key=f"{key_prefix}_down_btn",
                        type="primary"
                    )           
        # 4. package download
        zip_name = f"all_{key_prefix}_files.zip"
        zip_path = os.path.join(TEMP_DIR, zip_name)
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for f in files:
                zf.write(os.path.join(dir_path, f), f)
        with open(zip_path, "rb") as f:
            st.download_button(f"📦 打包下载全部 ({len(files)}个)", f, zip_name, "application/zip", key=f"{key_prefix}_zip")        
    else:
        st.info(f"当前任务的目录为空 ({dir_path})")
# ========================================================
# 1. 上传与裁剪
# ========================================================
if step == "1. 文档上传与裁剪":
    st.header("📄 步骤 1: PDF 文档处理")
    
    tab1, tab2 = st.tabs(["🚀 批量自动裁剪", "🛠️ 手动裁剪修复"])
    
    # --- Tab 1: 自动裁剪 ---
    with tab1:
        st.markdown("上传原始文档，系统将根据提取模式自动裁剪出关键页面。")
        uploaded_files = st.file_uploader("上传 PDF 文件", type=["pdf"], accept_multiple_files=True, key="auto_uploader")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            # === 修改点：基于业务场景的选择 ===
            crop_task_type = st.selectbox(
                "选择要提取的数据类型", 
                list(TASK_DICT.keys()) + ["自定义目录匹配", "自定义全文搜索"])
        with col2:
            # === 核心逻辑：根据选择自动预设参数 ===
            default_kw = ""
            algo_type = "TOC" # 默认目录匹配
            
            if "自然资源禀赋" in crop_task_type:
                default_kw = r"(土地利用.*表|表.*土地利用.*表)"
                algo_type = "Content" # 全文扫描
            elif "存在问题" in crop_task_type:
                default_kw = "存在问题"
            elif "整治潜力" in crop_task_type:
                default_kw = "整治可行性分析"
            elif "子项目" in crop_task_type:
                default_kw = "子项目安排" # 或者是 "项目"
            elif "空间布局" in crop_task_type:
                default_kw = "空间布局优化"
            # 允许用户微调关键词
            keyword = st.text_input("提取关键词 (支持正则)", value=default_kw)
            
            # 显示当前使用的算法提示
            if algo_type == "Content" or crop_task_type == "自定义全文搜索":
                st.caption("ℹ️ 模式：**全文关键词扫描** (适合跨页大表)")
                use_content_mode = True
            else:
                st.caption("ℹ️ 模式：**目录章节匹配** (适合标准文本章节)")
                use_content_mode = False
        
        if st.button("开始自动裁剪", type="primary"):
            if not uploaded_files:
                st.error("请先上传文件！")
            else:
                bar = st.progress(0)
                status = st.empty()
                success_count = 0
                for i, f in enumerate(uploaded_files):
                    src_path = os.path.join(DIRS["upload"], f.name)
                    with open(src_path, "wb") as buffer: buffer.write(f.getbuffer())
                    status.text(f"正在处理: {f.name}...")
                    
                    # 1. 提取信息
                    info = extract_info(f.name)
                    clean_region_name = info["文件名"]
                    
                    # 2. 构造新文件名 (带上任务类型标识，方便后续识别)
                    # 简化后缀：自然资源禀赋 -> landuse, 存在问题 -> issue 等
                    task_suffix = "data"
                    if crop_task_type in TASK_DICT:
                        task_suffix = TASK_DICT[crop_task_type]
                    else:
                        task_suffix = keyword.replace("*", "")[:5]

                    dst_name = f"{clean_region_name}_{task_suffix}.pdf"
                    dst_path = os.path.join(DIRS["crop"], dst_name)
                    
                    # 3. 执行裁剪 (根据模式选择函数)
                    is_ok = False
                    
                    if use_content_mode:
                        # 全文扫描模式 (用于自然资源/土地利用表)
                        is_ok = extract_pages_by_keywords(src_path, dst_path, keyword)
                    else:
                        # 目录匹配模式 (用于其他)
                        is_ok = extract_section_to_pdf(src_path, dst_path, keyword)
                    
                    if is_ok: 
                        success_count += 1
                    
                    bar.progress((i + 1) / len(uploaded_files))
                
                if success_count == len(uploaded_files): 
                    st.success(f"✅ 全部处理完成！成功 {success_count} 个。")
                else: 
                    st.warning(f"⚠️ 成功 {success_count} 个，失败 {len(uploaded_files)-success_count} 个。建议尝试手动修复失败的文件。")

    # --- Tab 2: 手动裁剪 ---
    with tab2:
        st.info("自动裁剪失败或裁剪内容有误，请在此处手动指定页码。**系统会自动覆盖同名的旧文件**，确保后续流程顺利运行。")
        # 1. choose file to crop
        existing_files = [f for f in os.listdir(DIRS["upload"]) if f.endswith(".pdf")]
        col_up, col_sel = st.columns([1, 2])
        with col_up: manual_file = st.file_uploader("上传单个文件", type=["pdf"], key="manual_uploader")
        target_file_path = None
        if manual_file:
            target_file_path = os.path.join(DIRS["upload"], manual_file.name)
            with open(target_file_path, "wb") as f: f.write(manual_file.getbuffer())
            st.info(f"已选中: {manual_file.name}")
        elif existing_files:
            sel = col_sel.selectbox("选择已上传文件", existing_files)
            if sel: target_file_path = os.path.join(DIRS["upload"], sel)
        
        if target_file_path:
            st.divider()
            c1, c2 = st.columns(2)

            with c1:
                manual_task_type = st.selectbox(
                    "这是哪类数据的文档？", 
                    list(TASK_DICT.keys()), 
                    key="manual_task_sel",
                    help="选择正确的类型，系统将自动生成标准文件名（如 _landuse.pdf），覆盖之前自动生成的错误文件。"
                )
            # split pages
            with c2:
                col_p1, col_p2 = st.columns(2)
                with col_p1: start_p = st.number_input("起始页码", min_value=1, value=1)
                with col_p2: end_p = st.number_input("结束页码", min_value=1, value=5)
            
            if st.button("✂️ 执行裁剪并覆盖", type="primary"):
                if end_p <= start_p: 
                    st.error("结束页码必须大于起始页码！")
                else:
                    f_name = os.path.basename(target_file_path)
                    info = extract_info(f_name)
                    
                    # === 关键：使用标准后缀生成文件名 ===
                    task_suffix = TASK_DICT[manual_task_type]
                    # 生成如 "东莞-凤岗_landuse.pdf"
                    dst_name = f"{info['文件名']}_{task_suffix}.pdf"
                    dst_path = os.path.join(DIRS["crop"], dst_name)
                    # check file replace
                    if os.path.exists(dst_path):
                        st.info(f"🔄 检测到旧文件 `{dst_name}`，将被新裁剪的文件覆盖。")
                    if extract_section_to_pdf_self(target_file_path, start_p, end_p, dst_path):
                        st.success(f"✅ 修复成功！文件已保存为: `{dst_name}`")
                        # 稍微延迟后刷新，让文件列表更新
                        time.sleep(1)
                        st.rerun() 
                    else: 
                        st.error("❌ 裁剪失败，请检查PDF是否损坏或页码越界。")
    st.divider()
    st.subheader("📂 结果文件管理")
    
    cropped_files = []
    if os.path.exists(DIRS["crop"]):
        cropped_files = [f for f in os.listdir(DIRS["crop"]) if f.endswith(".pdf")]
    
    if cropped_files:
        # 1. 列表展示
        st.dataframe(pd.DataFrame(cropped_files, columns=["已生成的文件名"]), use_container_width=True, height=200)
        
        with st.expander("🗑️ 管理/删除已处理文件"):
            files_to_delete = st.multiselect("选择要删除的文件 (支持多选)", cropped_files)
            if st.button("确认删除选中文件"):
                if files_to_delete:
                    for f_del in files_to_delete:
                        path_to_del = os.path.join(DIRS["crop"], f_del)
                        try:
                            os.remove(path_to_del)
                        except Exception as e:
                            st.error(f"删除失败 {f_del}: {e}")
                    st.success(f"已删除 {len(files_to_delete)} 个文件")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("请先选择要删除的文件")
        col_d1, col_d2 = st.columns(2)
        
        # 2. 批量打包下载功能
        with col_d1:
            zip_path = os.path.join(TEMP_DIR, "cropped_files.zip")
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for f in cropped_files:
                    zipf.write(os.path.join(DIRS["crop"], f), f)
            
            with open(zip_path, "rb") as f:
                st.download_button(
                    label="📦 打包下载所有文件 (.zip)",
                    data=f,
                    file_name="cropped_files.zip",
                    mime="application/zip",
                    type="primary"
                )
        
        # 3. 单文件下载功能
        with col_d2:
            selected_download = st.selectbox("或者选择单个文件下载:", cropped_files)
            if selected_download:
                file_path = os.path.join(DIRS["crop"], selected_download)
                with open(file_path, "rb") as f:
                    st.download_button(
                        label=f"📄 下载 {selected_download}",
                        data=f,
                        file_name=selected_download,
                        mime="application/pdf"
                    )
    else:
        st.info("暂无处理好的文件，请先执行裁剪操作。")
# ========================================================
# 2. 数据提取 (API)
# ========================================================
elif step == "2. 大模型数据获取":
    st.header("🤖 步骤 2: 调用大模型智能体获取数据")
    # 1. 扫描文件
    files = [f for f in os.listdir(DIRS["crop"]) if f.endswith(".pdf")]    
    if not files:
        st.warning("⚠️ 暂无已裁剪文件，请先完成步骤 1。")
    else:
        # 2. 文件名清洗预览
        st.subheader("1️⃣ 文件名清洗与地区识别")
        file_info_list = []
        for f in files:
            info = parser_file(f) # 调用 utils_pdf 中的新函数
            file_info_list.append(info)
        
        info_df = pd.DataFrame(file_info_list)
        st.dataframe(info_df[["文件名", "城市", "地区/县","详细单元"]], use_container_width=True)

        st.divider()
        
        # 3. 任务配置
        st.subheader("2️⃣ 开始提取")
        col1, col2 = st.columns([1, 1])
        with col1:
            task_type = st.selectbox("选择分析任务类型", list(TASK_DICT.keys()))
        with col2:
            use_mock = st.checkbox("使用模拟数据 (调试用)", value=True)
            
        if st.button("🚀 大模型分析", type="primary"):
            results = []
            progress_bar = st.progress(0)
            log_container = st.container() # 用于显示实时日志
            
            # 初始化客户端
            client = None
            if not use_mock:
                client = CozeClient() 
                workflow_id = WORKFLOW_CONFIG.get(task_type)
            # 开始循环处理
            for i, info in enumerate(file_info_list):
                file_name = info["原始文件名"]
                # 这里的“新文件名”实际上就是步骤1生成的规范化文件名 (例如: 潮州-湘桥_问题)

                region_name = info["文件名"] 
                
                file_path = os.path.join(DIRS["crop"], file_name)
                
                # --- UI 显示当前状态 ---
                with log_container:
                    status_expander = st.expander(f"🔄 正在处理: {region_name} ...", expanded=True)
                    with status_expander:
                        st.write(f"📄 文件: `{file_name}`")
                        # --- 调用 API ---
                        raw_data = None
                        try:
                            if use_mock:
                                time.sleep(0.5)
                                raw_data = get_mock_data(file_path, task_type)
                                st.info("✅ 模拟数据获取成功")
                            else:
                                st.write("📤 上传文件中...")
                                file_id = client.upload_file(file_path)
                                if file_id:
                                    st.write("🤖 AI 思考中...")
                                    raw_data = client.run_workflow(workflow_id, file_id)
                                    if raw_data:
                                        st.success("✅ 工作流执行成功")
                                    else:
                                        st.error("❌ 工作流返回为空")
                                else:
                                    st.error("❌ 上传失败")
                                time.sleep(1) # 限流保护
                        except Exception as e:
                            st.error(f"❌ 发生异常: {e}")
                        # --- 显示输出内容 ---
                        if raw_data:
                            st.markdown("**🔎 输出内容预览:**")
                            try:
                                json_data = json.loads(raw_data)
                                st.json(json_data)
                                if "output" in json_data:
                                    st.text_area("解析文本", json_data["output"], height=200)
                            except:
                                st.text(raw_data)
                            # 保存结果
                            results.append({
                                "地区": region_name,
                                "rawdata": raw_data,
                            })
                # 更新总进度
                progress_bar.progress((i + 1) / len(files))
            
            # 循环结束
            st.success(f"🎉 所有文件处理完成！成功获取 {len(results)} 条数据。")
            
            # 保存到 CSV
            if results:
                df_result = pd.DataFrame(results)
                task_suffix = TASK_DICT[task_type]
                save_filename = f"coze_raw_output_{task_suffix}.csv"
                save_path = os.path.join(DIRS["raw"], save_filename)
                
                df_result.to_csv(save_path, index=False, encoding='utf-8-sig')
                st.write(f"数据已保存至: `{save_path}`")
                st.dataframe(df_result.head())
            
    # 保存文件可视化 & 下载
    st.divider()
    st.subheader("📂 结果文件管理")
    coze_files = []
    if os.path.exists(DIRS["raw"]):
        coze_files = [f for f in os.listdir(DIRS["raw"]) if f.endswith(".csv")]
    if coze_files:
        # 2. file list display
        st.dataframe(pd.DataFrame(coze_files, columns=["大模型解析生成的数据文件"]), use_container_width=True)
        
        col_preview, col_down = st.columns([2, 1])
        with col_preview:
            # 3. file preview
            selected_preview = st.selectbox("选择文件进行预览:", coze_files, key="preview_sel")
            if selected_preview:
                preview_path = os.path.join(DIRS["raw"], selected_preview)
                try:
                    pre_df = pd.read_csv(preview_path)
                    st.write(f"📊 `{selected_preview}` 数据预览 (前 5 行):")
                    st.dataframe(pre_df.head())
                except Exception as e:
                    st.error(f"读取失败: {e}")
        with col_down:
            # 4. download 
            if selected_preview:
                preview_path = os.path.join(DIRS["raw"], selected_preview)
                with open(preview_path, "rb") as f:
                    st.download_button(
                        label=f"📥 下载 {selected_preview}",
                        data=f,
                        file_name=selected_preview,
                        mime="text/csv",
                        type="primary"
                    )
    else:
        st.info("暂无生成的原始数据文件。")        
# # ========================================================
# # 3. 数据解析
# # ========================================================
elif step == "3. 数据解析":
    st.header("🧹 步骤 3: 结构化解析")
    # === 使用 Tabs 分流：正常解析 vs 手动上传 ===
    tab1, tab2 = st.tabs(["⚙️ 解析原始数据", "📤 上传外部数据 (补充缺失项)"])
    
    # 正常数据解析
    with tab1:
        col1, col2 = st.columns([1, 1])
        with col1:
            parse_type = st.selectbox("选择解析模式", list(TASK_DICT.keys()))
        task_suffix = TASK_DICT[parse_type]
        raw_filename = f"coze_raw_output_{task_suffix}.csv"
        raw_file = os.path.join(DIRS["raw"], raw_filename)
        
        if not os.path.exists(raw_file):
            st.warning(f"⚠️ 未找到对应的数据文件：{raw_filename}。请先完成步骤 2 中该类型的提取。")
        else:
            df_raw = pd.read_csv(raw_file)
            st.write(f"📂 读取数据源: `{raw_filename}`")
            st.write("原始数据预览:", df_raw.head(3))
            
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
                # 读取文件
                if uploaded_ext.name.endswith('.csv'):
                    ext_df = pd.read_csv(uploaded_ext)
                else:
                    ext_df = pd.read_excel(uploaded_ext)
                # 简单校验
                if "地区" not in ext_df.columns:
                    st.error("❌ 上传失败：文件中缺少 `地区` 列！请参照模板格式。")
                    st.write("当前列名:", list(ext_df.columns))
                else:
                    # 预览
                    st.write("📊 数据预览:", ext_df.head())
                    
                    # 保存按钮
                    if st.button("💾 确认并保存"):
                        target_name = f"parsed_{target_suffix}.csv"
                        save_path = os.path.join(DIRS["result"], target_name)
                        
                        # 强制转为 csv utf-8-sig
                        ext_df.to_csv(save_path, index=False, encoding='utf-8-sig')
                        
                        st.success(f"✅ 文件已保存为: `{target_name}`")
                        st.info("💡 现在您可以前往 **步骤 4**，该文件将自动参与数据融合。")
                        
            except Exception as e:
                st.error(f"文件读取失败: {e}")
    render_file_manager(DIRS["result"], title="已解析的结构化数据", file_ext=".csv", key_prefix="step3")
    
# # ========================================================
# # 4. 数据融合
# # ========================================================
elif step == "4. 数据融合&展示":
    st.header("🔗 步骤 4: 多源数据融合 (N×d 矩阵)及可视化展示")
    # 扫描已解析的 CSV
    csvs = [f for f in os.listdir(DIRS["result"]) if f.startswith("parsed_")]
    norm_res_path = os.path.join(DIRS["result"], "parsed_final_matrix.csv")
    raw_res_path = os.path.join(DIRS["result"], "parsed_raw_matrix.csv")
    
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
        order_keywords = ["landuse", "potential", "spatial", "issue", "project"]
        sorted_csvs = []
        for kw in order_keywords:
            for f in csvs:
                if kw in f and f not in sorted_csvs: sorted_csvs.append(f)
        for f in csvs:
            if f not in sorted_csvs: sorted_csvs.append(f)
        
        selected = st.multiselect("选择要融合的文件 (已自动排序)", sorted_csvs, default=sorted_csvs)
        
        c1, c2 = st.columns([1, 2])
        with c1:
            use_log = st.checkbox("☑️ 启用 Log1p 对数变换", value=True, help="对面积/金额/数量列进行 Log(x+1) 变换，拉近长尾分布的差距，避免小数值在归一化后变为0。")
        with c2:
            start_btn = st.button("开始融合与归一化", type="primary")
        if  start_btn:
            if not selected:
                st.error("请至少选择一个文件。")
            else:
                matrices, maps, names = [], [], []
                all_feature_names = []
                # 按照排序后的 selected 列表读取
                for f in selected:
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
                
                # 1. 融合
                regions, X_final, slices = unify_and_concatenate(matrices, maps, names)
                
                if len(regions) > 0:
                    st.success(f"✅ 融合成功！共 {len(regions)} 个地区，特征维度: {X_final.shape[1]}")
                    try:
                        st.info(f"正在处理... (Log变换: {use_log})")
                        X_norm = preprocess_X(X_final, use_log=use_log)
                        final_df = pd.DataFrame(X_norm, index=regions, columns=all_feature_names)
                        final_df.to_csv(norm_res_path, encoding='utf-8-sig')
                        
                        raw_df = pd.DataFrame(X_final, index=regions, columns=all_feature_names)
                        raw_df.to_csv(raw_res_path, encoding='utf-8-sig')
                        st.rerun()
                    except Exception as e:
                            st.error(f"归一化失败: {e}")
                else:
                        st.error("融合失败：所选数据表之间没有公共地区。")
    # === 可视化看板 (新增) ===
    if os.path.exists(norm_res_path):
        st.divider()
        st.subheader("🎨 多维度可视化看板")
        
        # 1. 准备可视化选项
        vis_options = {"🏆 最终融合矩阵 (归一化)": norm_res_path}
        # 自动扫描并添加分项数据
        for f in sorted_csvs:
            vis_options[f"📄 分项: {f}"] = os.path.join(DIRS["result"], f)
            
        # 2. 用户选择
        c_vis1, c_vis2 = st.columns([1, 2])
        with c_vis1:
            selected_vis = st.selectbox("选择要展示的热力图数据:", list(vis_options.keys()))
        
        # 3. 加载与处理
        target_path = vis_options[selected_vis]
        try:
            if "最终融合" in selected_vis:
                df_vis = pd.read_csv(target_path, index_col=0)
                st.caption("展示最终融合并归一化后的全量数据。")
            else:
                df_vis = pd.read_csv(target_path)
                if "地区" in df_vis.columns: df_vis = df_vis.set_index("地区")
                # 筛选数值列
                df_vis = df_vis.select_dtypes(include=['number'])
                
                with c_vis2:
                    do_norm = st.checkbox("对此数据应用 Min-Max 归一化 (推荐)", value=True, key=f"norm_{selected_vis}")
                
                if do_norm and not df_vis.empty:
                    df_vis = (df_vis - df_vis.min()) / (df_vis.max() - df_vis.min())
                    df_vis = df_vis.fillna(0)
            
            if not df_vis.empty:
                fig = plot_heatmap(df_vis.values, df_vis.index.tolist(), feature_names=df_vis.columns.tolist())
                st.pyplot(fig)
            else:
                st.warning("该文件无数值数据，无法绘制热力图。")
                
        except Exception as e:
            st.error(f"可视化加载失败: {e}")
    # 这里展示的是 result 目录下的所有文件（包含 Step 3 的解析文件和 Step 4 的矩阵文件）               
    render_file_manager(DIRS["result"], title="融合及中间数据管理", file_ext=".csv", key_prefix="step4")
# ========================================================
# 5. 数据分类与导出
# ========================================================
elif step == "5. 数据分类与导出":
    st.header("📊 步骤 5: 智能分区分类 (K-Means)")
    
    # 自动加载上一步的文件
    # 注意：这里我们优先读取 "归一化后的矩阵"
    auto_path = os.path.join(DIRS["result"], "parsed_final_matrix.csv")
    
    df_matrix = None
    
    # 1. 数据源选择
    data_source_opt = st.radio("数据来源", ["自动加载 (步骤4结果)", "手动上传 (CSV)"])
    
    if data_source_opt == "自动加载 (步骤4结果)":
        if os.path.exists(auto_path):
            st.success(f"✅ 已检测到文件: parsed_final_matrix.csv")
            df_matrix = pd.read_csv(auto_path, index_col=0)
        else:
            st.warning("⚠️ 未找到自动生成的文件，请先完成步骤 4 或选择手动上传。")
    elif data_source_opt == "手动上传 (CSV)":
        uploaded_matrix = st.file_uploader("上传特征矩阵 CSV", type=["csv"])
        if uploaded_matrix:
            df_matrix = pd.read_csv(uploaded_matrix, index_col=0)

    # 2. 如果数据加载成功，显示配置项
    if df_matrix is not None:
        st.divider()
        st.write(f"📊 **当前数据:** {df_matrix.shape[0]} 个地区, {df_matrix.shape[1]} 个特征")
        with st.expander("查看数据详情"):
            st.dataframe(df_matrix.head())
        
        st.subheader("🛠️ 模型参数配置")
        col1, col2 = st.columns([1, 2])
        
        with col1:
            n_clusters = st.slider("聚类类别数目 (K)", min_value=2, max_value=10, value=3)
            
        with col2:
            st.markdown("**⚖️ 权重设定 (专家打分)**")
            weight_settings = {}
            with st.expander("点击展开详细权重设置", expanded=True):
                c1, c2 = st.columns(2)
                with c1:
                    weight_settings["自然资源禀赋"] = st.number_input("1. 自然资源", value=5.0, step=0.1)
                with c2:
                    weight_settings["自然资源-布尔项"] = st.number_input("   ↳ 林地/布尔", value=1.0, step=0.1)
                weight_settings["潜力项数据"] = st.number_input("2. 潜力数据", value=1.0, step=0.1)
                c3, c4 = st.columns(2)
                with c3: weight_settings["空间布局"] = st.number_input("3. 空间布局", value=0.1, step=0.05)
                with c4: weight_settings["存在问题"] = st.number_input("4. 存在问题", value=0.1, step=0.05)
                weight_settings["子项目数据"] = st.number_input("5. 子项目", value=0.05, step=0.01)

        # 3. 执行分析
        if st.button("🚀 开始聚类分析", type="primary"):
            try:
                total_feats = df_matrix.shape[1]
                # 构建权重向量
                weights_vec = build_weight_vector(weight_settings, total_feats)
                
                # 执行聚类
                labels, X_pca, X_final = perform_clustering(df_matrix, n_clusters, weights_vec)
                
                # 结果处理
                df_matrix['Cluster_ID'] = labels
                df_matrix['Cluster_Label'] = df_matrix['Cluster_ID'].apply(lambda x: f"类别 {x+1}")
                
                st.success("✅ 聚类完成！")
                
                # 可视化展示
                st.subheader("📈 聚类结果可视化 (PCA)")
                fig = plot_clusters(X_pca, labels, df_matrix.index)
                st.pyplot(fig)
                
                # 结果列表
                st.subheader("📋 分类结果表")
                st.dataframe(df_matrix[['Cluster_Label']].sort_values('Cluster_Label'))
                
                # 下载按钮
                st.download_button(
                    "📥 下载带分类结果的 CSV", 
                    df_matrix.to_csv(encoding='utf-8-sig'), 
                    "clustered_result.csv", 
                    "text/csv"
                )
            except Exception as e:
                st.error(f"分析出错: {e}")        
    # === 展示文件管理 ===
    render_file_manager(DIRS["final"], title="最终分类结果", file_ext=".csv", key_prefix="step5")