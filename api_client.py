import requests
import os
import time
import json
import pandas as pd

DEFAULT_COZE_TOKEN = "pat_XVznFiiHmr09YOp51Pta9rss6fuMKtL8IJMypv6JQYDbEbrfMEU70OLLshD9Cjvk"
COZE_CN_BASE_URL = "https://api.coze.cn"


WORKFLOW_CONFIG = {
    "整治潜力": "7574817225950822434",      # 您提供的潜力数据 Workflow ID
    "土地利用现状": "7541696293958729738",  # 您提供的自然资源禀赋 Workflow ID
    "存在问题": '7542773461622472739',  
    "子项目": '7543134980516380707'  }

class CozeClient:
    """
    Coze API 客户端封装
    使用 requests 原生实现，避免依赖 cozepy 库导致的安装问题
    """
    def __init__(self, api_token=None, base_url=COZE_CN_BASE_URL):
        self.token = api_token or DEFAULT_COZE_TOKEN
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        self.upload_headers = {
            "Authorization": f"Bearer {self.token}"
        }

    def upload_file(self, file_path):
        """上传文件到 Coze，返回 file_id"""
        url = f"{self.base_url}/v1/files/upload"
        file_name = os.path.basename(file_path)
        
        try:
            with open(file_path, 'rb') as f:
                response = requests.post(
                    url,
                    headers=self.upload_headers,
                    files={'file': f}
                )
                response.raise_for_status()
                # 解析返回结果
                res_json = response.json()
                if res_json.get('code') == 0:
                    return res_json['data']['id']
                else:
                    print(f"❌ 上传 API 错误: {res_json}")
                    return None
        except Exception as e:
            print(f"❌ 上传文件失败 [{file_name}]: {e}")
            return None

    def run_workflow(self, workflow_id, file_id):
        """执行工作流"""
        url = f"{self.base_url}/v1/workflow/run"
        
        # 构造参数，匹配您提供的 parameters 结构
        payload = {
            "workflow_id": workflow_id,
            "parameters": {
                "input": {
                    "file_id": file_id
                }
            }
        }
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            res_json = response.json()
            
            if res_json.get('code') == 0:
                # 获取 data 字段，这通常是工作流输出的 JSON 字符串
                return res_json.get('data', "")
            else:
                print(f"❌ 工作流 API 错误: {res_json}")
                return None
        except Exception as e:
            print(f"❌ 执行工作流失败: {e}")
            return None

# === 模拟数据生成器 (用于没有 Token 或测试时) ===
def get_mock_data(file_path, task_type):
    f_name = os.path.basename(file_path)
    if task_type == "存在问题":
        return json.dumps({"output": f"模拟数据：{f_name} 存在问题类别排序...\n1. 【耕地碎片化】... 排序：1"})
    elif task_type == "整治潜力":
        return json.dumps({"output": f"模拟数据：{f_name} {{'垦造水田潜力': 100.5, '新增耕地潜力': 20.0}}"})
    else:
        return json.dumps({"output": f"模拟数据：{f_name} 分析结果..."})

# === 统一调用入口 ===
def batch_process_via_coze(file_list, task_type="存在问题", use_mock=False):
    """
    批量处理文件的主函数
    """
    results = []
    
    # 1. 获取对应任务的 Workflow ID
    workflow_id = WORKFLOW_CONFIG.get(task_type)
    
    # 初始化客户端
    client = None
    if not use_mock:
        client = CozeClient()
    
    print(f"开始处理 {len(file_list)} 个文件，任务类型: {task_type} (ID: {workflow_id})")
    
    # 创建进度条容器 (在 Streamlit 中通常由外部控制，这里打印日志)
    for i, file_path in enumerate(file_list):
        region_name = os.path.basename(file_path).split('_')[0]
        raw_data = None
        
        if use_mock or not workflow_id:
            if not use_mock:
                print(f"⚠ 未配置 {task_type} 的 Workflow ID，使用模拟数据。")
            raw_data = get_mock_data(file_path, task_type)
            time.sleep(0.5)
        else:
            # 1. 上传
            file_id = client.upload_file(file_path)
            if file_id:
                # 2. 执行
                raw_data = client.run_workflow(workflow_id, file_id)
                # 防止请求过快触发限流
                time.sleep(1)
            else:
                raw_data = json.dumps({"output": "上传失败"})

        # 结果存入列表
        if raw_data:
            results.append({
                "地区": region_name,
                "rawdata": raw_data
            })
            
    return pd.DataFrame(results)