import streamlit as st
import os
import pandas as pd
import shutil
from utils_pdf import extract_section_to_pdf, extract_section_to_pdf_self, extract_info
from api_client import CozeClient, get_mock_data, WORKFLOW_CONFIG 
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
    "result": os.path.join(TEMP_DIR, "4_results")
}

# 初始化目录
for d in DIRS.values():
    if not os.path.exists(d): os.makedirs(d)

# === 侧边栏：流程控制 ===
with st.sidebar:
    st.header("工作流导航")
    step = st.radio("选择步骤", [
        "1. 文档上传与裁剪", 
        "2. 关键数据获取", 
        "3. 数据解析", 
        "4. 数据融合",
        "5. 数据分类与导出"
    ])
    
    st.divider()
    if st.button("清理临时文件"):
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
            for d in DIRS.values():
                if not os.path.exists(d): os.makedirs(d)
        st.success("已清理缓存")

# ========================================================
# 1. 上传与裁剪
# ========================================================
if step == "1. 上传与裁剪":
    st.header("📄 步骤 1: PDF 文档处理")
    
    tab1, tab2 = st.tabs(["🚀 批量自动裁剪", "🛠️ 手动裁剪修复"])
    
    # --- Tab 1: 自动裁剪 ---
    with tab1:
        st.markdown("上传原始文档，系统将自动识别并裁剪包含关键词（如“问题”）的章节。")
        uploaded_files = st.file_uploader("上传 PDF 文件", type=["pdf"], accept_multiple_files=True, key="auto_uploader")
        keyword = st.text_input("章节关键词", value="问题")
        
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
                    
                    # === 修改点：使用 extract_info 进行重命名 ===
                    # 1. 提取信息
                    info = extract_info(f.name)
                    clean_region_name = info["新文件名"]
                    
                    # 2. 构造新文件名: 地区名_关键词.pdf (例如: 潮州-湘桥_问题.pdf)
                    dst_name = f"{clean_region_name}_{keyword}.pdf"
                    dst_path = os.path.join(DIRS["crop"], dst_name)
                    
                    # 3. 执行裁剪
                    if extract_section_to_pdf(src_path, dst_path, keyword): 
                        success_count += 1
                        # 可选：显示重命名结果
                        # st.caption(f"已保存为: {dst_name}")
                    
                    bar.progress((i + 1) / len(uploaded_files))
                
                if success_count == len(uploaded_files): 
                    st.success(f"✅ 全部处理完成！成功 {success_count} 个。")
                else: 
                    st.warning(f"⚠️ 成功 {success_count} 个，失败 {len(uploaded_files)-success_count} 个。")

    # --- Tab 2: 手动裁剪 ---
    with tab2:
        st.markdown("针对自动识别失败的文件，**手动指定起止页码**进行提取。")
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
            c1, c2, c3 = st.columns([1, 1, 2])
            with c1: start_p = st.number_input("起始页码", min_value=1, value=1)
            with c2: end_p = st.number_input("结束页码", min_value=1, value=5)
            with c3: 
                st.write(""); st.write("")
                if st.button("✂️ 执行裁剪"):
                    if end_p <= start_p: st.error("结束页码必须大于起始页码！")
                    else:
                        f_name = os.path.basename(target_file_path)
                        
                        # === 修改点：手动裁剪也尝试规范化命名 ===
                        info = extract_info(f_name)
                        # 手动裁剪通常是为了修复某个特定问题，这里加上 _manual 后缀以示区别
                        # 或者如果您希望手动修复的文件也能直接被 API 识别，可以去掉 _manual，
                        # 但为了防止覆盖自动生成的文件，建议保留标识。
                        # 这里我们使用: 地区名_manual.pdf
                        dst_name = f"{info['新文件名']}_manual.pdf"
                        dst_path = os.path.join(DIRS["crop"], dst_name)
                        
                        if extract_section_to_pdf_self(target_file_path, start_p, end_p, dst_path):
                            st.success(f"✅ 裁剪成功！已保存为: {dst_name}")
                        else: st.error("❌ 裁剪失败")

    st.divider()
    # 查看已裁剪文件
    cropped_files = []
    if os.path.exists(DIRS["crop"]):
        cropped_files = [f for f in os.listdir(DIRS["crop"]) if f.endswith(".pdf")]
    
    if cropped_files:
        with st.expander(f"📂 查看已处理文件 ({len(cropped_files)} 个)"):
            st.dataframe(pd.DataFrame(cropped_files, columns=["文件名"]), height=200)
# ========================================================
# 2. 数据提取 (API)
# ========================================================
elif step == "2. 数据提取(API)":
    st.header("🤖 步骤 2: 调用 AI 提取数据")
    
    # 1. 扫描文件
    files = [f for f in os.listdir(DIRS["crop"]) if f.endswith(".pdf")]
    
    if not files:
        st.warning("⚠️ 暂无已裁剪文件，请先完成步骤 1。")
    else:
        # 2. 文件名清洗预览
        st.subheader("1️⃣ 文件名清洗与地区识别")
        file_info_list = []
        for f in files:
            info = extract_info(f) # 调用 utils_pdf 中的新函数
            file_info_list.append(info)
        
        info_df = pd.DataFrame(file_info_list)
        st.dataframe(info_df[["原始文件名", "新文件名", "城市", "地区/县"]], use_container_width=True)
        
        st.divider()
        
        # 3. 任务配置
        st.subheader("2️⃣ 开始提取")
        col1, col2 = st.columns([1, 1])
        with col1:
            task_type = st.selectbox("选择分析任务类型", ["整治潜力", "土地利用现状", "存在问题", "项目汇总"])
        with col2:
            use_mock = st.checkbox("使用模拟数据 (调试用)", value=True)
            
        if st.button("🚀 发送至扣子(Coze)进行分析", type="primary"):
            # 初始化结果容器
            results = []
            progress_bar = st.progress(0)
            log_container = st.container() # 用于显示实时日志
            
            # 初始化客户端
            client = None
            if not use_mock:
                client = CozeClient() # 需在 api_client.py 配好 Token
                workflow_id = WORKFLOW_CONFIG.get(task_type)
            
            # 开始循环处理
            for i, info in enumerate(file_info_list):
                file_name = info["原始文件名"]
                # 这里的“新文件名”实际上就是步骤1生成的规范化文件名 (例如: 潮州-湘桥_问题)
                # 我们可以再次处理一下，或者直接用文件名作为地区ID
                # 因为步骤1已经重命名过了，这里的文件名已经是 "潮州-湘桥_问题.pdf"
                # extract_info 会把它解析为 "潮州-湘桥" (去掉了后缀)
                region_name = info["新文件名"] 
                
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
                                if not workflow_id:
                                    st.error(f"❌ 未配置 {task_type} 的 Workflow ID")
                                else:
                                    # 1. 上传
                                    st.write("📤 上传文件中...")
                                    file_id = client.upload_file(file_path)
                                    if file_id:
                                        # 2. 执行
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
                            # 尝试美化 JSON 显示
                            try:
                                json_data = json.loads(raw_data)
                                st.json(json_data)
                                # 提取 output 字段里的纯文本展示
                                if "output" in json_data:
                                    st.text_area("Output 文本", json_data["output"], height=100)
                            except:
                                st.text(raw_data)
                            
                            # 保存结果
                            results.append({
                                "地区": region_name,
                                "rawdata": raw_data,
                                "原始文件名": file_name
                            })
                
                # 更新总进度
                progress_bar.progress((i + 1) / len(files))
            
            # 循环结束
            st.success(f"🎉 所有文件处理完成！成功获取 {len(results)} 条数据。")
            
            # 保存到 CSV
            if results:
                df_result = pd.DataFrame(results)
                save_path = os.path.join(DIRS["raw"], "coze_raw_output.csv")
                df_result.to_csv(save_path, index=False, encoding='utf-8-sig')
                st.write(f"数据已保存至: `{save_path}`")
                st.dataframe(df_result.head())
# # ========================================================
# # 3. 数据解析
# # ========================================================
# elif step == "3. 数据解析":
#     st.header("🧹 步骤 3: 结构化解析")
    
#     raw_file = os.path.join(DIRS["raw"], "coze_raw_output.csv")
#     if not os.path.exists(raw_file):
#         st.warning("请先完成步骤 2 获取原始数据。")
#     else:
#         df_raw = pd.read_csv(raw_file)
#         st.write("原始数据预览:", df_raw.head(3))
        
#         col1, col2 = st.columns([1, 1])
#         with col1:
#             parse_type = st.selectbox("选择解析模式", ["存在问题", "整治潜力", "项目汇总"])
        
#         if col2.button("执行解析"):
#             parsed_df = process_raw_data(df_raw, parse_type)
            
#             # 合并地区列
#             final_df = pd.concat([df_raw[['地区']], parsed_df], axis=1)
            
#             # 存为中间结果
#             out_name = f"parsed_{parse_type}.csv"
#             final_df.to_csv(os.path.join(DIRS["result"], out_name), index=False, encoding='utf-8-sig')
            
#             st.success(f"解析成功！已保存为 {out_name}")
#             st.dataframe(final_df.head())

# # ========================================================
# # 4. 数据融合
# # ========================================================
# elif step == "4. 数据融合":
#     st.header("🔗 步骤 4: 多源数据融合 (N×d 矩阵)")
    
#     csvs = [f for f in os.listdir(DIRS["result"]) if f.startswith("parsed_")]
#     selected = st.multiselect("选择要融合的数据表", csvs, default=csvs)
    
#     if st.button("开始融合") and selected:
#         matrices, maps, names = [], [], []
        
#         for f in selected:
#             path = os.path.join(DIRS["result"], f)
#             df = pd.read_csv(path)
#             # 假设第1列是地区，后面是特征
#             region_col = df.columns[0]
#             df = df.set_index(region_col)
#             # 只取数值列，忽略文字说明列
#             df_num = df.select_dtypes(include=['number']).fillna(0)
            
#             matrices.append(df_num.values)
#             maps.append({name: i for i, name in enumerate(df_num.index)})
#             names.append(f.replace("parsed_", "").replace(".csv", ""))
        
#         regions, X_final, slices = unify_and_concatenate(matrices, maps, names)
        
#         if len(regions) > 0:
#             st.success(f"融合完成！共 {len(regions)} 个地区，{X_final.shape[1]} 个特征。")
            
#             # 展示切片信息
#             st.json(slices)
            
#             # 导出
#             final_df = pd.DataFrame(X_final, index=regions)
#             st.dataframe(final_df.head())
#             st.download_button(
#                 "📥 下载最终矩阵 CSV",
#                 final_df.to_csv(encoding='utf-8-sig'),
#                 "final_matrix.csv"
#             )
#         else:
#             st.error("融合失败：所选数据表之间没有公共地区。")