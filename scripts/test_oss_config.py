"""
阿里云 OSS 配置验证脚本
用于测试 OSS 上传功能是否正常工作
"""
import os
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 加载环境变量
def load_dotenv():
    env_path = Path(__file__).parent.parent / '.env'
    if not env_path.exists():
        print("❌ 未找到 .env 文件")
        return False
    
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
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
    return True

# 加载环境变量
load_dotenv()

def check_env_config():
    """检查环境变量配置"""
    print("=" * 60)
    print("步骤 1: 检查环境变量配置")
    print("=" * 60)
    
    required_vars = {
        'OSS_ENABLED': os.environ.get('OSS_ENABLED'),
        'OSS_ENDPOINT': os.environ.get('OSS_ENDPOINT'),
        'OSS_ACCESS_KEY_ID': os.environ.get('OSS_ACCESS_KEY_ID'),
        'OSS_ACCESS_KEY_SECRET': os.environ.get('OSS_ACCESS_KEY_SECRET'),
    }
    
    all_configured = True
    for key, value in required_vars.items():
        if value:
            if key in ['OSS_ACCESS_KEY_ID', 'OSS_ACCESS_KEY_SECRET']:
                masked = value[:4] + '****' + value[-4:] if len(value) > 8 else '****'
                print(f"✅ {key}: {masked}")
            else:
                print(f"✅ {key}: {value}")
        else:
            print(f"❌ {key}: 未配置")
            all_configured = False
    
    print()
    return all_configured

def check_oss2_installed():
    """检查 oss2 SDK 是否已安装"""
    print("=" * 60)
    print("步骤 2: 检查 oss2 SDK")
    print("=" * 60)
    
    try:
        import oss2
        print(f"✅ oss2 SDK 已安装，版本: {oss2.__version__}")
        print()
        return True
    except ImportError:
        print("❌ oss2 SDK 未安装")
        print("请运行: pip install oss2")
        print()
        return False

def test_oss_connection():
    """测试 OSS 连接和权限"""
    print("=" * 60)
    print("步骤 3: 测试 OSS 连接")
    print("=" * 60)
    
    try:
        import oss2
        
        # 获取配置
        oss_endpoint_full = os.environ.get('OSS_ENDPOINT', '')
        access_key_id = os.environ.get('OSS_ACCESS_KEY_ID', '')
        access_key_secret = os.environ.get('OSS_ACCESS_KEY_SECRET', '')
        
        # 解析 endpoint
        parts = oss_endpoint_full.split('.', 1)
        if len(parts) != 2:
            print(f"❌ OSS_ENDPOINT 格式错误: {oss_endpoint_full}")
            print("正确格式: bucket-name.oss-region.aliyuncs.com")
            return False
        
        bucket_name = parts[0]
        oss_endpoint = parts[1]
        
        print(f"📦 存储桶: {bucket_name}")
        print(f"🌐 端点: {oss_endpoint}")
        print()
        
        # 创建 OSS 客户端
        auth = oss2.Auth(access_key_id, access_key_secret)
        bucket = oss2.Bucket(auth, f"https://{oss_endpoint}", bucket_name)
        
        # 测试：获取存储桶信息
        print("正在测试连接...")
        try:
            bucket_info = bucket.get_bucket_info()
            print(f"✅ 成功连接到存储桶")
            print(f"   - 创建时间: {bucket_info.creation_date}")
            print(f"   - 存储类型: {bucket_info.storage_class}")
            print(f"   - 位置: {bucket_info.location}")
            print()
        except oss2.exceptions.NoSuchBucket:
            print(f"❌ 存储桶不存在: {bucket_name}")
            return False
        except oss2.exceptions.AccessDenied:
            print("❌ 访问被拒绝，请检查 AccessKey 权限")
            return False
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_oss_upload():
    """测试文件上传"""
    print("=" * 60)
    print("步骤 4: 测试文件上传")
    print("=" * 60)
    
    try:
        import oss2
        
        # 获取配置
        oss_endpoint_full = os.environ.get('OSS_ENDPOINT', '')
        access_key_id = os.environ.get('OSS_ACCESS_KEY_ID', '')
        access_key_secret = os.environ.get('OSS_ACCESS_KEY_SECRET', '')
        
        # 解析 endpoint
        parts = oss_endpoint_full.split('.', 1)
        bucket_name = parts[0]
        oss_endpoint = parts[1]
        
        # 创建客户端
        auth = oss2.Auth(access_key_id, access_key_secret)
        bucket = oss2.Bucket(auth, f"https://{oss_endpoint}", bucket_name)
        
        # 创建测试文件
        test_content = f"OSS 上传测试 - {datetime.now().isoformat()}"
        test_filename = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        object_key = f"ai-images/test/{test_filename}"
        
        print(f"📝 创建测试文件: {test_filename}")
        print(f"📤 上传路径: {object_key}")
        
        # 上传测试
        result = bucket.put_object(object_key, test_content.encode('utf-8'))
        
        if result.status == 200:
            print(f"✅ 上传成功！")
            public_url = f"https://{oss_endpoint_full}/{object_key}"
            print(f"🔗 公网 URL: {public_url}")
            print()
            print("提示：如果存储桶配置了公共读权限，可以在浏览器中访问上述 URL")
            print()
            return True
        else:
            print(f"❌ 上传失败，状态码: {result.status}")
            return False
            
    except oss2.exceptions.AccessDenied:
        print("❌ 上传被拒绝")
        print("可能原因：")
        print("  1. AccessKey 没有 PutObject 权限")
        print("  2. 存储桶策略限制")
        return False
    except Exception as e:
        print(f"❌ 上传失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n" + "🚀 阿里云 OSS 配置验证工具 🚀".center(60))
    print()
    
    # 检查环境变量
    if not check_env_config():
        print("=" * 60)
        print("⚠️  请先在 .env 文件中配置 OSS 相关变量")
        print("=" * 60)
        print()
        print("需要配置的变量：")
        print("  OSS_ENABLED=true")
        print("  OSS_ENDPOINT=shor-file.oss-cn-wulanchabu.aliyuncs.com")
        print("  OSS_ACCESS_KEY_ID=你的AccessKeyId")
        print("  OSS_ACCESS_KEY_SECRET=你的AccessKeySecret")
        print()
        return
    
    # 检查 SDK
    if not check_oss2_installed():
        return
    
    # 测试连接
    if not test_oss_connection():
        print("=" * 60)
        print("❌ OSS 连接测试失败")
        print("=" * 60)
        return
    
    # 测试上传
    if not test_oss_upload():
        print("=" * 60)
        print("❌ OSS 上传测试失败")
        print("=" * 60)
        return
    
    # 全部通过
    print("=" * 60)
    print("🎉 所有测试通过！OSS 配置正确")
    print("=" * 60)
    print()
    print("现在你可以：")
    print("  1. 启动 Web 应用: python web_app.py")
    print("  2. 访问 http://localhost:5000")
    print("  3. 上传参考图片进行图生图")
    print()

if __name__ == '__main__':
    main()
