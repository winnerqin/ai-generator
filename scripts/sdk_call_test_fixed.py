import os
import json
import traceback
import argparse
from datetime import datetime

from volcengine.visual.VisualService import VisualService


def build_args():
    p = argparse.ArgumentParser(description='SDK text2img test with env/CLI support (fixed)')
    p.add_argument('--prompt', '-p', type=str, help='Prompt text')
    p.add_argument('--neg', '-n', type=str, help='Negative prompt')
    p.add_argument('--width', type=int, help='Width in px')
    p.add_argument('--height', type=int, help='Height in px')
    p.add_argument('--steps', type=int, help='Sampling steps')
    p.add_argument('--seed', type=int, help='Seed (0 for random)')
    p.add_argument('--model', type=str, help='Model version')
    p.add_argument('--req_key', type=str, help='Request key / model identifier')
    return p.parse_args()


def get_setting(cli_val, env_keys, default=None):
    if cli_val is not None:
        return cli_val
    for k in env_keys:
        v = os.environ.get(k)
        if v is not None:
            return v
    return default


def main():
    args = build_args()

    ak = os.environ.get('VOLCENGINE_AK') or os.environ.get('VOLCENGINE_ACCESS_KEY') or os.environ.get('ACCESS_KEY')
    sk = os.environ.get('VOLCENGINE_SK') or os.environ.get('VOLCENGINE_SECRET_KEY') or os.environ.get('SECRET_KEY')
    endpoint = os.environ.get('VOLCENGINE_ENDPOINT', '')
    print('Python executable:', __import__('sys').executable)
    print('Found AK:', bool(ak), 'Found SK:', bool(sk))

    if not (ak and sk):
        print('ERROR: VOLCENGINE_AK and VOLCENGINE_SK environment variables not set. Aborting.')
        return

    prompt = get_setting(args.prompt, ['PROMPT', 'VOLCENG_PROMPT'], "A high-quality photo-realistic portrait of a fox in a suit, soft studio lighting")
    negative = get_setting(args.neg, ['NEG_PROMPT', 'VOLCENG_NEG_PROMPT'], "")
    width = int(get_setting(args.width, ['WIDTH', 'VOLCENGINE_WIDTH'], 1024))
    height = int(get_setting(args.height, ['HEIGHT', 'VOLCENGINE_HEIGHT'], 1024))
    steps = int(get_setting(args.steps, ['STEPS', 'VOLCENGINE_STEPS'], 20))
    seed = int(get_setting(args.seed, ['SEED', 'VOLCENGINE_SEED'], 0))
    model_version = get_setting(args.model, ['MODEL_VERSION', 'VOLCENGINE_MODEL'], 'v1')
    req_key = get_setting(args.req_key, ['REQ_KEY', 'VOLCENGINE_REQ_KEY'], 'jimeng_t2i_v40')

    svc = VisualService()
    try:
        svc.set_ak(ak)
        svc.set_sk(sk)
    except Exception:
        pass
    if endpoint:
        host = endpoint
        if host.startswith('http'):
            host = host.split('://', 1)[1]
        svc.set_host(host)

    body = {
        'prompt': prompt,
        'negative_prompt': negative,
        'width': width,
        'height': height,
        'steps': steps,
        'seed': seed,
        'model_version': model_version,
        'req_key': req_key,
    }

    method_name = 'text2img_xl_sft'
    if not hasattr(svc, method_name):
        print('ERROR: VisualService does not expose', method_name)
        return

    method = getattr(svc, method_name)
    print(f"Calling {method_name} with req_key={req_key} width={width} height={height} steps={steps} seed={seed}")
    try:
        resp = method(body)
    except Exception:
        print('SDK call raised exception:')
        traceback.print_exc()
        return

    print('Call returned type:', type(resp))
    try:
        print('Response (truncated 4000 chars):')
        print(json.dumps(resp, ensure_ascii=False)[:4000])
    except Exception:
        print('Raw response:', resp)

    # Save full response JSON for auditing
    try:
        out_dir = os.path.join(os.getcwd(), 'output')
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        resp_path = os.path.join(out_dir, f'sdk_response_{ts}.json')
        with open(resp_path, 'w', encoding='utf-8') as fh:
            json.dump(resp, fh, ensure_ascii=False, indent=2)
        print('Saved full response JSON to', resp_path)
    except Exception:
        print('Failed to save full response JSON:')
        traceback.print_exc()

    # Save binary_data_base64 if present
    try:
        if isinstance(resp, dict) and resp.get('data') and isinstance(resp['data'], dict):
            b64_list = resp['data'].get('binary_data_base64') or resp['data'].get('binary_base64')
            if b64_list and isinstance(b64_list, list) and len(b64_list) > 0:
                for i, img_b64 in enumerate(b64_list):
                    try:
                        import base64
                        raw = base64.b64decode(img_b64)
                        out_dir = os.path.join(os.getcwd(), 'output')
                        os.makedirs(out_dir, exist_ok=True)
                        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                        out_path = os.path.join(out_dir, f'sdk_generated_{ts}_{i+1}_{width}x{height}.jpg')
                        with open(out_path, 'wb') as fh:
                            fh.write(raw)
                        print('Saved image to', out_path)
                    except Exception:
                        print('Failed to decode/save image index', i)
    except Exception as e:
        print('Error while checking binary_data_base64:', e)


if __name__ == '__main__':
    main()
