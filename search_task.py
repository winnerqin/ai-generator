# 列出视频生成任务
import os
import json
from volcenginesdkarkruntime import Ark


def load_dotenv_file(path):
    """加载 .env 文件"""
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.lower().startswith('export '):
                    line = line[7:].strip()
                if '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k = k.strip()
                v = v.strip()
                if v.startswith(('"', "'")) and v.endswith(('"', "'")) and len(v) >= 2:
                    v = v[1:-1]
                if os.environ.get(k) is None:
                    os.environ[k] = v
    except Exception as e:
        print(f"加载 .env 文件失败: {e}")


def find_dotenv(start_dir=None):
    """查找 .env 文件"""
    import pathlib
    cur = pathlib.Path(start_dir or os.getcwd()).resolve()
    root = cur.anchor
    while True:
        candidate = cur / '.env'
        if candidate.exists() and candidate.is_file():
            return str(candidate)
        if str(cur) == root:
            return None
        cur = cur.parent


def convert_to_dict(obj):
    """将响应对象转换为字典"""
    if isinstance(obj, dict):
        return {k: convert_to_dict(v) for k, v in obj.items()}
    elif hasattr(obj, '__dict__'):
        return {k: convert_to_dict(v) for k, v in obj.__dict__.items()}
    elif hasattr(obj, '_asdict'):  # namedtuple
        return convert_to_dict(obj._asdict())
    elif isinstance(obj, (list, tuple)):
        return [convert_to_dict(item) for item in obj]
    else:
        return obj


def main():
    # 加载 .env 文件
    print("="*60)
    print("🔍 视频任务列表查询工具")
    print("="*60)
    
    dotenv_path = find_dotenv()
    if dotenv_path:
        print(f"📁 找到 .env 文件: {dotenv_path}")
        load_dotenv_file(dotenv_path)
    else:
        print("⚠️  未找到 .env 文件，将使用环境变量")
    
    # 获取 API Key
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        print("\n❌ 错误: ARK_API_KEY 未配置")
        print("   请在 .env 文件中设置 ARK_API_KEY=your_api_key")
        return
    
    print(f"✅ API Key 已加载 (长度: {len(api_key)})")
    
    # 初始化客户端
    client = Ark(api_key=api_key)
    print("✅ 客户端初始化成功\n")
    
    # 获取用户输入的查询参数
    print("="*60)
    print("📋 请输入查询参数 (直接回车使用默认值)")
    print("="*60)
    
    # 获取分页大小
    page_size_input = input("每页数量 (默认: 10): ").strip()
    page_size = int(page_size_input) if page_size_input.isdigit() else 10
    
    # 获取状态过滤
    print("\n可选状态: queued, running, succeeded, failed, cancelled")
    status_input = input("状态过滤 (默认: 全部，直接回车): ").strip()
    status = status_input if status_input else None
    
    # 获取页码
    page_input = input("页码 (默认: 1): ").strip()
    page = int(page_input) if page_input.isdigit() else 1
    
    print("\n" + "="*60)
    print("🔄 正在查询任务列表...")
    print("="*60)
    print(f"  每页数量: {page_size}")
    print(f"  页码: {page}")
    if status:
        print(f"  状态过滤: {status}")
    else:
        print(f"  状态过滤: 全部")
    print("="*60)
    
    try:
        # 构建查询参数
        query_params = {
            "page_size": page_size,
        }
        
        if status:
            query_params["status"] = status
        
        # 如果有页码参数，也添加进去（如果API支持）
        if page > 1:
            query_params["page"] = page
        
        # 列出任务
        resp = client.content_generation.tasks.list(**query_params)
        
        # 转换为字典格式
        resp_dict = convert_to_dict(resp)
        
        # 格式化输出为 JSON
        print("\n" + "="*60)
        print("📊 任务列表查询结果 (JSON格式)")
        print("="*60)
        print(json.dumps(resp_dict, indent=2, ensure_ascii=False))
        print("="*60)
        
        # 尝试提取任务数量信息 - 检查多种可能的字段名
        task_count = 0
        tasks = None
        
        if isinstance(resp_dict, dict):
            # 尝试多种可能的字段名
            possible_keys = ['tasks', 'data', 'items', 'results', 'list', 'content']
            for key in possible_keys:
                if key in resp_dict:
                    tasks = resp_dict[key]
                    if isinstance(tasks, list):
                        task_count = len(tasks)
                        break
            
            # 如果没找到，检查是否有直接包含列表的字段
            if tasks is None:
                for key, value in resp_dict.items():
                    if isinstance(value, list):
                        tasks = value
                        task_count = len(value)
                        print(f"📌 在字段 '{key}' 中找到任务列表")
                        break
        elif isinstance(resp_dict, list):
            tasks = resp_dict
            task_count = len(resp_dict)
        
        # 显示任务数量
        if task_count > 0:
            print(f"\n✅ 共查询到 {task_count} 个任务")
        else:
            print(f"\n⚠️  未找到任务列表，请检查响应结构")
            print(f"   响应类型: {type(resp_dict)}")
            if isinstance(resp_dict, dict):
                print(f"   响应字段: {list(resp_dict.keys())}")
        
    except Exception as e:
        print(f"\n❌ 查询任务失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

