import sys
import json
p = sys.argv[1] if len(sys.argv) > 1 else r"e:\cursor\jimeng4_image\jimeng4_image_generator\output\sdk_response_20251130_094136.json"
with open(p, 'r', encoding='utf-8') as f:
    j = json.load(f)
imgs = j.get('data', {}).get('binary_data_base64', [])
print('images=', len(imgs))
print('status=', j.get('data', {}).get('algorithm_base_resp'))
print('top_keys=', list(j.keys()))

# Print first 3 chars of first base64 to confirm it's JPEG
if imgs:
    b0 = imgs[0]
    print('first_img_prefix=', b0[:20])
else:
    print('no images')
