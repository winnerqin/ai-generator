"""
测试示例图功能
"""
import requests

def test_sample_images_api():
    """测试示例图API"""
    print("测试 /api/sample-images 接口...")
    
    try:
        response = requests.get('http://localhost:5000/api/sample-images')
        data = response.json()
        
        print(f"\n状态码: {response.status_code}")
        print(f"响应数据:")
        print(f"  success: {data.get('success')}")
        print(f"  images 数量: {len(data.get('images', []))}")
        
        if data.get('images'):
            print(f"\n示例图列表:")
            for i, img in enumerate(data['images'], 1):
                print(f"  {i}. {img['filename']}")
                print(f"     URL: {img['url']}")
        else:
            print("\n提示: 当前没有示例图")
            print("使用以下命令上传示例图:")
            print("  python upload_sample_images.py <图片文件或目录>")
        
        return data.get('success', False)
        
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_sample_images_api()
    
    if success:
        print("\n✅ API测试通过")
    else:
        print("\n❌ API测试失败")
