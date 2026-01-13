import json,sys
p='e:\\cursor\\jimeng4_image\\jimeng4_image_generator\\output\\sdk_response_20251130_093331.json'
with open(p,'r',encoding='utf-8') as f:
    data=json.load(f)
print('code=',data.get('code'))
keys=data.get('data',{}).keys()
print('data keys=', list(keys))
b64 = data.get('data',{}).get('binary_data_base64')
print('binary_data_base64 type=', type(b64), 'len=', len(b64) if b64 else 0)
if b64:
    for i, s in enumerate(b64[:5],1):
        print(i, 'len', len(s), 'head', s[:50])
print('echoed prompt in response?', 'prompt' in data)
print('full response keys at top:', list(data.keys()))
