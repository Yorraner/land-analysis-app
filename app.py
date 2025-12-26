import streamlit as st
import os
import pandas as pd
import shutil
# 导入我们封装好的模块
from utils_pdf import extract_section_to_pdf, extract_section_to_pdf_self
# from api_client import batch_process_via_coze
# from utils_parsers import process_raw_data
# from utils_fusion import unify_and_concatenate

# === 页面配置 ===
st.set_page_config(page_title="土地整治智能分析平台", layout="wide")
st.title("🏗️ 土地整治文档智能分析系统")

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
        "1. 上传与裁剪", 
        "2. 数据提取(API)", 
        "3. 数据解析", 
        "4. 数据融合"
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
    
    # 使用 Tabs 分离自动和手动功能
    tab1, tab2 = st.tabs(["🚀 批量自动裁剪", "🛠️ 手动裁剪修复"])
    
    # --- Tab 1: 自动裁剪 ---
    with tab1:
        st.markdown("上传原始文档，系统将自动识别并裁剪包含关键词（如“问题”）的章节。")
        uploaded_files = st.file_uploader("上传 PDF 文件 (支持批量)", type=["pdf"], accept_multiple_files=True, key="auto_uploader")
        keyword = st.text_input("章节关键词", value="问题", help="如：问题、潜力、项目")
        
        if st.button("开始自动裁剪", type="primary"):
            if not uploaded_files:
                st.error("请先上传文件！")
            else:
                bar = st.progress(0)
                status = st.empty()
                success_count = 0
                
                for i, f in enumerate(uploaded_files):
                    # 保存原文件
                    src_path = os.path.join(DIRS["upload"], f.name)
                    with open(src_path, "wb") as buffer:
                        buffer.write(f.getbuffer())
                    
                    # 裁剪
                    status.text(f"正在处理: {f.name}...")
                    dst_name = f"{os.path.splitext(f.name)[0]}_cropped.pdf"
                    dst_path = os.path.join(DIRS["crop"], dst_name)
                    
                    if extract_section_to_pdf(src_path, dst_path, keyword):
                        success_count += 1
                    
                    bar.progress((i + 1) / len(uploaded_files))
                
                if success_count == len(uploaded_files):
                    st.success(f"✅ 全部处理完成！成功裁剪 {success_count} 个文件。")
                else:
                    st.warning(f"⚠️ 处理完成。成功 {success_count} 个，失败 {len(uploaded_files)-success_count} 个。失败文件可尝试手动裁剪。")
                
                st.write(f"裁剪后文件已保存在: `{DIRS['crop']}`")

    # --- Tab 2: 手动裁剪 ---
    with tab2:
        st.markdown("针对自动识别失败的文件，**手动指定起止页码**进行提取。")
        
        # 1. 获取文件列表 (优先从已上传文件夹读取，也可以支持新上传)
        existing_files = [f for f in os.listdir(DIRS["upload"]) if f.endswith(".pdf")]
        
        col_up, col_sel = st.columns([1, 2])
        with col_up:
            manual_file = st.file_uploader("上传单个文件 (或从右侧选择)", type=["pdf"], key="manual_uploader")
        
        target_file_path = None
        if manual_file:
            # 如果新上传了文件，保存它
            target_file_path = os.path.join(DIRS["upload"], manual_file.name)
            with open(target_file_path, "wb") as f:
                f.write(manual_file.getbuffer())
            st.info(f"已选中新上传文件: {manual_file.name}")
        elif existing_files:
            # 如果没上传新文件，但文件夹里有之前的
            selected_existing = col_sel.selectbox("选择已上传的文件", existing_files)
            if selected_existing:
                target_file_path = os.path.join(DIRS["upload"], selected_existing)
        
        if target_file_path:
            st.divider()
            c1, c2, c3 = st.columns([1, 1, 2])
            with c1:
                start_p = st.number_input("起始页码 (Start Page)", min_value=1, value=1, step=1)
            with c2:
                end_p = st.number_input("结束页码 (End Page)", min_value=1, value=5, step=1)
            
            with c3:
                st.write(" ") # 占位
                st.write(" ") 
                manual_btn = st.button("✂️ 执行手动裁剪")
            
            if manual_btn:
                # 检查页码逻辑
                if end_p <= start_p:
                    st.error(f"❌ 结束页码 ({end_p}) 必须大于 起始页码 ({start_p})！")
                else:
                    f_name = os.path.basename(target_file_path)
                    dst_name = f"{os.path.splitext(f_name)[0]}_manual_crop.pdf"
                    dst_path = os.path.join(DIRS["crop"], dst_name)
                    
                    with st.spinner("正在裁剪..."):
                        # 调用 utils_pdf 中的 extract_section_to_pdf_self
                        success = extract_section_to_pdf_self(target_file_path, start_p, end_p, dst_path)
                        
                    if success:
                        st.success(f"✅ 裁剪成功！已保存为: {dst_name}")
                    else:
                        st.error("❌ 裁剪失败，请检查文件是否损坏或页码是否超出范围。")
        else:
            st.info("请先上传文件或在“批量自动裁剪”中上传文件。")

# ========================================================
# 2. 数据提取 (API)
# ========================================================
# elif step == "2. 数据提取(API)":
#     st.header("🤖 步骤 2: 调用 AI 提取数据")
    
#     files = [f for f in os.listdir(DIRS["crop"]) if f.endswith(".pdf")]
    
#     if not files:
#         st.warning("⚠️ 暂无已裁剪文件，请先完成步骤 1。")
#     else:
#         st.write(f"就绪文件: {len(files)} 个")
#         # 显示文件列表供确认
#         with st.expander("查看文件列表"):
#             st.write(files)
        
#         if st.button("发送至扣子(Coze)进行分析"):
#             with st.spinner("正在请求 API..."):
#                 file_paths = [os.path.join(DIRS["crop"], f) for f in files]
#                 df_raw = batch_process_via_coze(file_paths)
                
#                 save_path = os.path.join(DIRS["raw"], "coze_raw_output.csv")
#                 df_raw.to_csv(save_path, index=False, encoding='utf-8-sig')
                
#                 st.success("✅ 数据提取完成！")
#                 st.dataframe(df_raw.head())

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