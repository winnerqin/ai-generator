"""
上传示例图到阿里云 OSS 的 ai-images/sample 目录

使用方法:
python upload_sample_images.py <图片文件或目录>
"""
import os
import sys
from pathlib import Path

def find_dotenv(start_dir=None):
    """查找 .env 文件"""
    cur = Path(start_dir or os.getcwd()).resolve()
    root = cur.anchor
    while True:
        candidate = cur / '.env'
        if candidate.exists() and candidate.is_file():
            return str(candidate)
        if str(cur) == root:
            return None
        cur = cur.parent

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

# 加载环境变量
dotenv_path = find_dotenv()
if dotenv_path:
    print(f'从 {dotenv_path} 加载环境变量')
    load_dotenv_file(dotenv_path)
else:
    print("警告: 未找到 .env 文件")

def upload_to_sample_folder(file_path):
    """上传图片到 OSS sample 目录"""
    try:
        import oss2
        
        # 获取配置
        oss_endpoint_full = os.environ.get('OSS_ENDPOINT', 'shor-file.oss-cn-wulanchabu.aliyuncs.com')
        access_key_id = os.environ.get('OSS_ACCESS_KEY_ID')
        access_key_secret = os.environ.get('OSS_ACCESS_KEY_SECRET')
        
        if not all([oss_endpoint_full, access_key_id, access_key_secret]):
            print("错误: OSS 配置不完整")
            return False
        
        # 提取 bucket 和 endpoint
        parts = oss_endpoint_full.split('.', 1)
        if len(parts) == 2:
            bucket_name = parts[0]
            oss_endpoint = parts[1]
        else:
            print(f"错误: OSS_ENDPOINT 格式不正确: {oss_endpoint_full}")
            return False
        
        # 初始化 OSS
        auth = oss2.Auth(access_key_id, access_key_secret)
        bucket = oss2.Bucket(auth, f"https://{oss_endpoint}", bucket_name)
        
        # 上传文件到 sample 目录
        filename = os.path.basename(file_path)
        object_key = f"ai-images/sample/{filename}"
        
        print(f"上传 {filename} 到 OSS...")
        with open(file_path, 'rb') as f:
            result = bucket.put_object(object_key, f)
        
        # 生成公网访问 URL
        public_url = f"https://{oss_endpoint_full}/{object_key}"
        print(f"✅ 上传成功: {public_url}")
        return True
        
    except ImportError:
        print("错误: 未安装 oss2 库")
        print("安装命令: pip install oss2")
        return False
    except Exception as e:
        print(f"上传失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    if len(sys.argv) < 2:
        print("使用方法: python upload_sample_images.py <图片文件或目录>")
        print("示例:")
        print("  python upload_sample_images.py image.jpg")
        print("  python upload_sample_images.py ./samples/")
        sys.exit(1)
    
    path = sys.argv[1]
    
    if not os.path.exists(path):
        print(f"错误: 路径不存在: {path}")
        sys.exit(1)
    
    # 支持的图片格式
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'}
    
    if os.path.isfile(path):
        # 单个文件
        ext = os.path.splitext(path)[1].lower()
        if ext in image_extensions:
            upload_to_sample_folder(path)
        else:
            print(f"错误: 不支持的文件格式: {ext}")
    
    elif os.path.isdir(path):
        # 目录
        uploaded_count = 0
        for root, dirs, files in os.walk(path):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in image_extensions:
                    file_path = os.path.join(root, file)
                    if upload_to_sample_folder(file_path):
                        uploaded_count += 1
        
        print(f"\n总计上传 {uploaded_count} 个文件")
    else:
        print(f"错误: 无效的路径: {path}")
        sys.exit(1)

if __name__ == '__main__':
    main()
