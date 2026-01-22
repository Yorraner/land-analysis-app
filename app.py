import streamlit as st
import os
import pandas as pd
import numpy as np
import time
import json
import zipfile
import shutil
from utils_pdf import extract_section_to_pdf, extract_section_to_pdf_self, \
    extract_info,parser_file,extract_pages_by_keywords,dict_save2csv
from api_client import CozeClient, get_mock_data, WORKFLOW_CONFIG 
from utils_fusion import unify_and_concatenate, preprocess_X # 引入归一化函数
from utils_vis import plot_heatmap ,plot_horizontal_bars_from_df,plot_category_radar_chart,plot_clusters
from utils_parse import process_raw_data
from style import set_bg_hack
from algorithm import clustering_kmeans_with_entropy_expert,build_weight_vector

# from utils_parsers import process_raw_data
# from utils_fusion import unify_and_concatenate


def check_password():
    """Returns `True` if the user had a correct password."""
    
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["username"] in ["admin", "user"] and st.session_state["password"] == "123456":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    # === 核心修改：定义登录界面的布局函数 ===
    def show_login_form(error_msg=None):
        # 1. 设置背景图
        set_bg_hack("./imgs/bg1.png")
        
        # 2. 增加垂直方向的空白，把登录框往下挤 (Vertical Center)
        st.markdown("<br><br><br><br>", unsafe_allow_html=True) 

        # 3. 使用列布局实现水平居中 (Horizontal Center)
        col1, col2, col3 = st.columns([1, 2, 1]) 
        with col2:
            st.markdown("""
                <style>
                div[data-testid="stVerticalBlock"] > div[style*="flex-direction: column;"] > div[data-testid="stVerticalBlock"] {
                    background-color: rgba(255, 255, 255, 0.9); /* 白色背景，90%不透明 */
                    padding: 30px;
                    border-radius: 15px;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.2);
                }
                </style>
                """, unsafe_allow_html=True)
            st.markdown(
        """
        <div style='text-align: center; margin-bottom: 20px;'>
            <div style='font-size: 26px; font-weight: bold; color: #333;'>全域土地综合整治</div>
            <div style='font-size: 26px; font-weight: bold; color: #333;'>地区类型分类平台</div>
        </div>
        """,
        unsafe_allow_html=True
    )
            st.text_input("用户名", key="username")
            st.text_input("密码", type="password", key="password")
            st.button("登录", on_click=password_entered, use_container_width=True) # 按钮填满宽度
            
            if error_msg:
                st.error(error_msg)

    # === 逻辑判断 ===
    if "password_correct" not in st.session_state:
        show_login_form()
        return False
    elif not st.session_state["password_correct"]:
        show_login_form(error_msg="😕 用户名或密码错误")
        return False
        
    else:
        return True

if not check_password():
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
                    dst_name = f"{info['原始文件名']}_{task_suffix}.pdf"
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
        st.dataframe(pd.DataFrame(cropped_files, columns=["已生成的文件名"]), width="stretch", height=200)
        
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
    st.header("🤖 步骤 2: 调用 AI 提取数据")
    col1, col2 = st.columns([1, 1])
    with col1:
        task_type = st.selectbox("选择分析任务类型", list(TASK_DICT.keys()))
    with col2:
        use_mock = st.checkbox("使用模拟数据 (调试用)", value=True)
    
    # 获取对应的后缀标识
    target_suffix = TASK_DICT.get(task_type)
    
    # 2. 扫描并过滤文件
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
            # 预览文件信息
            file_info_list = []
            for f in target_files:
                info = extract_info(f)
                file_info_list.append(info)
            
            st.dataframe(
                pd.DataFrame(file_info_list)[["原始文件名", "文件名", "城市", "地区/县"]], 
                height=150,
                width="stretch"
            )
            
            st.divider()
            st.subheader("2️⃣ 开始提取")
            
            if st.button("🚀 发送至扣子(Coze)进行分析", type="primary"):
                results = []
                progress_bar = st.progress(0)
                log_container = st.container()
                
                client = None
                workflow_id = None
                if not use_mock:
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
                                if use_mock:
                                    time.sleep(0.5)
                                    # 传入类型，模拟不同数据
                                    raw_data = get_mock_data(file_path, task_type.split(' ')[0])
                                    st.info("✅ 模拟数据获取成功")
                                else:
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
    render_file_manager(DIRS["raw"], title="已获取的原始数据文件", file_ext=".csv", key_prefix="step2")
    
# # ========================================================
# # 3. 数据解析
# # ========================================================
elif step == "3. 数据解析":
    st.header("🧹 步骤 3: 结构化解析")
    # === 使用 Tabs 分流：正常解析 vs 手动上传 ===
    tab1, tab2,tab3 = st.tabs(["⚙️ 解析原始数据", 
                               "📤 上传外部数据 (补充缺失项)",
                               "🔄 加载历史中间数据 (.pkl)"])
    
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
    with tab3:
        st.markdown("""
        **功能说明：** 如果您之前保存了处理过程中的 `.pkl` (Pickle) 文件，可以直接在此处恢复。
        系统会自动将其转换为标准格式，**您可以直接跳过解析步骤，直接进行步骤 4 的融合与步骤 5 的分类**。
        """)
        uploaded_pkl = st.file_uploader("上传处理好的 .pkl 字典文件", type=["pkl"], key="tab3_uploader")
        
        if uploaded_pkl:
            try:
                # 1. 读取 Pickle
                data_dict = pd.read_pickle(uploaded_pkl)
                # 2. 检查数据结构 (基于你提供的 keys)
                required_keys = {'X', 'features', 'regions'}
                # 允许 X_norm 不存在（兼容旧数据），但必须有 X
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
                    # 4. 重构 DataFrame
                    # 确保矩阵形状匹配
                    if len(regions) == matrix_data.shape[0] and len(feats) == matrix_data.shape[1]:
                        df_reconstructed = pd.DataFrame(matrix_data, index=regions, columns=feats)
                        df_reconstructed.index.name = "地区"
                        
                        st.dataframe(df_reconstructed.head(3))
                        col_btn1, col_btn2 = st.columns([1,2])
                        with col_btn1:
                            if st.button("🚀 恢复为最终矩阵", type="primary"):
                                # === 核心操作：直接生成 Step 4 的产出文件 ===
                                # 保存为 parsed_final_matrix.csv，这样 Step 5 可以直接读取
                                save_path_final = os.path.join(DIRS["result"], "parsed_origion_final_matrix.csv") # 这个名称是否需要更改，这是原始操作得到的结果
                                df_reconstructed.to_csv(save_path_final, encoding='utf-8-sig')
                                
                                # 同时保存一份 raw 用于备份 (如果有 X 的话)
                                if 'X' in data_dict:
                                    df_raw_backup = pd.DataFrame(data_dict['X'], index=regions, columns=feats)
                                    df_raw_backup.index.name = "地区"
                                    df_raw_backup.to_csv(os.path.join(DIRS["result"], "parsed_raw_matrix.csv"), encoding='utf-8-sig')
                                
                                st.success(f"✅ 数据已恢复！")
                                st.info("💡 您现在可以直接点击侧边栏的 **'5. 数据分类与导出'** 进行分析。")
                    else:
                        st.error(f"❌ 维度不匹配：地区数 {len(regions)} vs 矩阵行数 {matrix_data.shape[0]}")
                
                # --- 兼容逻辑：如果上传的是普通 DataFrame pkl ---
                elif isinstance(data_dict, pd.DataFrame):
                    st.info("📦 检测到普通 DataFrame 格式 (非字典)。")
                    df_pkl = data_dict
                    if "地区" not in df_pkl.columns and df_pkl.index.name == "地区":
                        df_pkl = df_pkl.reset_index()
                    
                    st.write("预览:", df_pkl.head(3))
                    if st.button("💾 转存为 CSV (需经步骤4融合)", key="save_df_pkl"):
                        # 普通 DataFrame 通常是中间态，建议走步骤4
                        pkl_task_type = st.selectbox("选择数据类型", list(TASK_DICT.keys()))
                        target_name = f"parsed_{TASK_DICT[pkl_task_type]}.csv"
                        df_pkl.to_csv(os.path.join(DIRS["result"], target_name), index=False, encoding='utf-8-sig')
                        st.success(f"已保存为 {target_name}，请前往步骤 4 融合。")
                        
                else:
                    st.error(f"❌ 未知的数据结构。Keys: {data_dict.keys() if isinstance(data_dict, dict) else type(data_dict)}")

            except Exception as e:
                st.error(f"❌ 读取出错: {e}")
        
    render_file_manager(DIRS["result"], title="已解析的结构化数据", file_ext=".csv", key_prefix="step3")
# # ========================================================
# # 4. 数据融合
# # ========================================================
elif step == "4. 数据融合&展示":
    st.header("🔗 步骤 4: 多源数据融合 (N×d 矩阵)及可视化展示")
    # 扫描已解析的 CSV
    csvs = [f for f in os.listdir(DIRS["result"]) if f.startswith("parsed_")]
    # 结果路径
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
        # 1. 定义核心任务后缀顺序
        strict_order_suffixes = ["landuse", "potential", "spatial", "issue", "project"]
        
        # 2. 构建默认选中列表 (Default Selection) - 仅包含严格匹配的核心文件
        default_files = []
        for suffix in strict_order_suffixes:
            target_name = f"parsed_{suffix}.csv"
            if target_name in csvs:
                default_files.append(target_name)
        # 3. 构建所有选项列表 (All Options) - 核心在前，其他在后
        # 这样用户可以看到所有 parsed_*.csv，但默认只选对的 5 个
        other_files = [f for f in csvs if f not in default_files]
        all_options = default_files + other_files
        
        if not default_files:
            st.warning("⚠️ 未找到任何符合标准命名规范的核心文件（如 parsed_landuse.csv）。请检查步骤 3 是否已正确执行。")
            
        selected = st.multiselect(
            "选择要融合的文件 (默认仅选中 5 类核心数据)", 
            options=all_options, 
            default=default_files
        )
        
        c1, c2 = st.columns([1, 2])
        with c1:
            use_log = st.checkbox("☑️ 启用对数变换", value=True, help="对面积/金额/数量列进行 Log(x+1) 变换，拉近长尾分布的差距，避免小数值在归一化后变为0。")
        with c2:
            start_btn = st.button("开始融合与归一化", type="primary")
        if  start_btn:
            if not selected:
                st.error("请至少选择一个文件。")
            else:
                matrices, maps, names,all_feature_names = [], [], [],[]
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
                        final_df.index.name = "地区"
                        final_df.to_csv(norm_res_path, encoding='utf-8-sig', index_label="地区")
                        
                        raw_df = pd.DataFrame(X_final, index=regions, columns=all_feature_names)
                        raw_df.index.name = "地区"
                        raw_df.to_csv(raw_res_path, encoding='utf-8-sig', index_label="地区")

                        st.rerun()
                    except Exception as e:
                            st.error(f"归一化失败: {e}")
                else:
                        st.error("融合失败：所选数据表之间没有公共地区。")
    if os.path.exists(norm_res_path):
        st.divider()
        st.subheader("🎨 多维度可视化看板")
        # 1. 准备可视化选项
        vis_options = {"🏆 最终融合矩阵 (归一化)": norm_res_path}
        # 自动扫描并添加分项数据
        for f in csvs: 
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
                do_norm = False
            else:
                df_vis = pd.read_csv(target_path)
                if "地区" in df_vis.columns: df_vis = df_vis.set_index("地区")
                # 筛选数值列
                else: df_vis = df_vis.set_index(df_vis.columns[0])
                df_vis = df_vis.select_dtypes(include=['number'])
                
                with c_vis2:
                    do_norm = st.checkbox(
                        "应用 Log1p + Min-Max 归一化", 
                        value=True, 
                        key=f"norm_{selected_vis}",
                        help="防止长尾数据导致热力图全黑。Log1p用于拉近数量级差距。"
                    )
                if not df_vis.empty:
                    if do_norm:
                        # 1. Log1p
                        df_log = np.log1p(df_vis)
                        # 2. Min-Max
                        range_val = df_log.max() - df_log.min()
                        # 防止除0
                        df_norm = pd.DataFrame(
                            np.where(range_val == 0, 0, (df_log - df_log.min()) / range_val),
                            index=df_vis.index, columns=df_vis.columns
                        ).fillna(0)
                        
                        # 绘图：传入特征名 (分项数据列数少，可以显示名字)
                        fig = plot_heatmap(df_norm.values, df_norm.index.tolist(), feature_names=df_norm.columns.tolist())
                    else:
                        # 不归一化直接画 (可能会很难看)
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
    st.header("📊 步骤 5: 智能分区分类")
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
                    weight_settings["自然资源-布尔项"] = st.number_input("  ↳ 林地/布尔", value=1.0, step=0.1)
                weight_settings["潜力项数据"] = st.number_input("2. 潜力数据", value=1.0, step=0.1)
                c3, c4 = st.columns(2)
                with c3: weight_settings["空间布局"] = st.number_input("3. 空间布局", value=0.1, step=0.05)
                with c4: weight_settings["存在问题"] = st.number_input("4. 存在问题", value=0.1, step=0.05)
                weight_settings["子项目数据"] = st.number_input("5. 子项目", value=0.05, step=0.01)

        # 3. algorithm
        if st.button("🚀 开始聚类分析", type="primary"):
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

                st.success("✅ 聚类完成！")
                
                # Tab 分页展示不同图表
                # tab_res1, tab_res2, tab_res3, tab_res4 = st.tabs(["📋 结果总表", "🕸️ 类别特征分布(雷达图)", "📊 地区概率分布(条形图)", "📈 降维分布(PCA)"])
                tab_res1, tab_res2, tab_res3 = st.tabs(["📋 结果总表", "🕸️ 类别特征分布(雷达图)", "📊 地区概率分布(条形图)"])
                with tab_res1:
                    st.dataframe(df_result)
                    st.download_button("📥 下载详细结果 Excel", 
                                     data=df_result.to_csv().encode('utf-8-sig'),
                                     file_name="clustering_result_full.csv")

                with tab_res2:
                    st.subheader("各类别主要关注特征 (Centroids × Weights)")
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
                            # 目的：凸显那些"数值高"且"权重高"的关键特征
                            cluster_profile = cluster_center_profile * analysis_weights
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
                        with st.expander("查看特征注意力数值详情"):
                            st.dataframe(category_feature_attention.style.background_gradient(cmap='Greens'))
                with tab_res3:
                    st.subheader("各地区归属概率可视化")
                    # 调用修改后的条形图函数
                    fig_bars = plot_horizontal_bars_from_df(df_result)
                    st.pyplot(fig_bars)
                    fig_bars_path = os.path.join(DIRS["final"], f"{n_clusters}_region_membership_bars.png")
                    fig_bars.savefig(fig_bars_path, dpi=300, bbox_inches='tight')
                    
                st.success(f"🎉 所有分析结果（表格与图表）已自动保存至: `{DIRS['final']}`")
            except Exception as e:
                st.error(f"分析过程发生错误: {str(e)}")
                # 打印详细报错方便调试
                import traceback
                st.text(traceback.format_exc())      
    # === 展示文件管理 ===
    render_file_manager(DIRS["final"], title="最终成果文件 (Step 5 Outputs)", file_ext=".png", key_prefix="step5_img")
    render_file_manager(DIRS["final"], title="最终成果数据 (Step 5 Data)", file_ext=".xlsx", key_prefix="step5_data")