import os
# Install SDK:  pip install 'volcengine-python-sdk[ark]'
from volcenginesdkarkruntime import Ark 

client = Ark(
    base_url="https://ark.cn-beijing.volces.com/api/v3", 
    api_key=os.getenv('ARK_API_KEY'), 
)

# 设置宽高比和分辨率
aspect_ratio = '16:9'  # 可选: '1:1', '4:3', '3:4', '16:9', '9:16', '3:2', '2:3'
resolution = '2k'  # 可选: '2k', '4k'

# 宽高比和分辨率配置（根据方舟大模型2K/4K标准）
ASPECT_RATIOS = {
    '1:1': {'2k': (2048, 2048), '4k': (4096, 4096)},
    '4:3': {'2k': (2560, 1920), '4k': (3840, 2880)},
    '3:4': {'2k': (1920, 2560), '4k': (2880, 3840)},
    '16:9': {'2k': (2560, 1920), '4k': (3840, 2160)},
    '9:16': {'2k': (1440, 2560), '4k': (2160, 3840)},
    '3:2': {'2k': (2560, 1706), '4k': (3840, 2560)},
    '2:3': {'2k': (1706, 2560), '4k': (2560, 3840)},
}

# 获取对应的宽高
width, height = ASPECT_RATIOS.get(aspect_ratio, {}).get(resolution, (2048, 2048))

# 根据分辨率确定size参数
ark_size = f"{resolution.upper()}K"  # '2K' 或 '4K'

# 生成图片
imagesResponse = client.images.generate( 
    model="doubao-seedream-4-5-251128",
    prompt="充满活力的特写编辑肖像，模特眼神犀利，头戴雕塑感帽子，色彩拼接丰富，眼部焦点锐利，景深较浅，具有Vogue杂志封面的美学风格，采用中画幅拍摄，工作室灯光效果强烈。",
    size=ark_size,  # '2K' 或 '4K'
    response_format="url",
    watermark=False,
    extra_body={
        "width": width,
        "height": height,
    }
) 
 
print(f"生成的图片URL: {imagesResponse.data[0].url}")
print(f"宽高比: {aspect_ratio}, 分辨率: {resolution}, 尺寸: {width}x{height}")
