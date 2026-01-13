import os
import json
import traceback
import random
import argparse
from datetime import datetime
from pathlib import Path

from volcengine.visual.VisualService import VisualService


def build_args():
    p = argparse.ArgumentParser(description='SDK text2img test with env/CLI support (restored)')
    p.add_argument('--prompt', '-p', type=str, help='Prompt text')
    p.add_argument('--neg', '-n', type=str, help='Negative prompt')
    p.add_argument('--width', type=int, help='Width in px')
    p.add_argument('--height', type=int, help='Height in px')
    p.add_argument('--steps', type=int, help='Sampling steps')
    p.add_argument('--seed', type=int, help='Seed (0 for random)')
    p.add_argument('--model', type=str, help='Model version')
    p.add_argument('--req_key', type=str, help='Request key / model identifier')
    p.add_argument('--image_urls', type=str, help='Comma-separated source image URLs (for img2img/inpainting)')
    p.add_argument('--size', type=str, help='Size shorthand, e.g. 1024x1024 (overrides width/height if provided)')
    p.add_argument('--num_images', type=int, help='Number of images to request')
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
    # Try environment first
    ak = os.environ.get('VOLCENGINE_AK') or os.environ.get('VOLCENGINE_ACCESS_KEY') or os.environ.get('ACCESS_KEY')
    sk = os.environ.get('VOLCENGINE_SK') or os.environ.get('VOLCENGINE_SECRET_KEY') or os.environ.get('SECRET_KEY')
    # If credentials not found in env, try to locate and load a .env file in cwd or parent directories
    def find_dotenv(start_dir=None):
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
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    # support `export KEY=VAL` or `KEY=VAL`
                    if line.lower().startswith('export '):
                        line = line[7:].strip()
                    if '=' not in line:
                        continue
                    k, v = line.split('=', 1)
                    k = k.strip()
                    v = v.strip()
                    if v.startswith(('"', "'")) and v.endswith(('"', "'")) and len(v) >= 2:
                        v = v[1:-1]
                    # don't overwrite existing env vars
                    if os.environ.get(k) is None:
                        os.environ[k] = v
        except Exception:
            pass

    if not (ak and sk):
        dotenv_path = find_dotenv()
        if dotenv_path:
            print('Found .env at', dotenv_path, '- loading missing variables')
            load_dotenv_file(dotenv_path)
            # re-read
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
    image_urls_raw = get_setting(args.image_urls, ['IMAGE_URLS', 'VOLCENGINE_IMAGE_URLS'], None)
    size_raw = get_setting(args.size, ['SIZE', 'VOLCENGINE_SIZE'], None)
    num_images = int(get_setting(args.num_images, ['NUM_IMAGES', 'VOLCENGINE_NUM_IMAGES'], 1))

    # parse size if provided (e.g. "1024x1024")
    if size_raw:
        try:
            if 'x' in size_raw:
                parts = size_raw.lower().split('x')
                w = int(parts[0])
                h = int(parts[1])
                width = w
                height = h
        except Exception:
            pass

    # parse image_urls CSV into list
    image_urls = None
    if image_urls_raw:
        # allow either comma or semicolon separated
        raw = image_urls_raw.strip()
        if raw:
            sep = ',' if ',' in raw else ';'
            image_urls = [u.strip() for u in raw.split(sep) if u.strip()]

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
        # optional fields per docs
        'num_images': num_images,
        # include alternative count field names to maximize compatibility
        'n': num_images,
        'image_count': num_images,
    }

# Attach optional fields if present
    if image_urls:
        body['image_urls'] = image_urls
    if size_raw:
        body['size'] = size_raw

    # Save request body for auditing (before call)
    try:
        out_dir = os.path.join(os.getcwd(), 'output')
        os.makedirs(out_dir, exist_ok=True)
        ts_req = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        req_path = os.path.join(out_dir, f'sdk_request_{ts_req}.json')
        with open(req_path, 'w', encoding='utf-8') as fh:
            json.dump(body, fh, ensure_ascii=False, indent=2)
        print('Saved request JSON to', req_path)
    except Exception:
        print('Failed to save request JSON:')
        traceback.print_exc()

    method_name = 'text2img_xl_sft'
    if not hasattr(svc, method_name):
        print('ERROR: VisualService does not expose', method_name)
        return

    method = getattr(svc, method_name)
    # Helper to call once and save request/response/images
    def call_once(call_body, call_index, per_seed):
        call_body = dict(call_body)
        # request-level seed handling
        call_body['seed'] = per_seed
        # many backends ignore multi-image fields; ask for 1 per call to be safe
        call_body['num_images'] = 1
        call_body['n'] = 1
        call_body['image_count'] = 1

        try:
            ts_req_i = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            req_path_i = os.path.join(os.getcwd(), 'output', f'sdk_request_{ts_req_i}_{call_index}.json')
            with open(req_path_i, 'w', encoding='utf-8') as fh:
                json.dump(call_body, fh, ensure_ascii=False, indent=2)
            print('Saved per-call request JSON to', req_path_i)
        except Exception:
            print('Failed to save per-call request JSON:')
            traceback.print_exc()

        try:
            resp_i = method(call_body)
        except Exception:
            print('SDK call raised exception on attempt', call_index)
            traceback.print_exc()
            return None, []

        try:
            print('Per-call response (truncated):')
            print(json.dumps(resp_i, ensure_ascii=False)[:2000])
        except Exception:
            print('Raw per-call response:', resp_i)

        try:
            ts_resp_i = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            resp_path_i = os.path.join(os.getcwd(), 'output', f'sdk_response_{ts_resp_i}_{call_index}.json')
            with open(resp_path_i, 'w', encoding='utf-8') as fh:
                json.dump(resp_i, fh, ensure_ascii=False, indent=2)
            print('Saved per-call response JSON to', resp_path_i)
        except Exception:
            print('Failed to save per-call response JSON:')
            traceback.print_exc()

        images_saved = []
        try:
            if isinstance(resp_i, dict) and resp_i.get('data') and isinstance(resp_i['data'], dict):
                b64_list = resp_i['data'].get('binary_data_base64') or resp_i['data'].get('binary_base64')
                if b64_list and isinstance(b64_list, list) and len(b64_list) > 0:
                    for j, img_b64 in enumerate(b64_list):
                        try:
                            import base64
                            raw = base64.b64decode(img_b64)
                            out_dir = os.path.join(os.getcwd(), 'output')
                            os.makedirs(out_dir, exist_ok=True)
                            ts_img = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                            global_index = f"{call_index}_{j+1}"
                            out_path = os.path.join(out_dir, f'sdk_generated_{ts_img}_{global_index}_{width}x{height}.jpg')
                            with open(out_path, 'wb') as fh:
                                fh.write(raw)
                            print('Saved image to', out_path)
                            images_saved.append(out_path)
                        except Exception:
                            print('Failed to decode/save image index', j)
        except Exception as e:
            print('Error while checking binary_data_base64 for per-call:', e)

        return resp_i, images_saved

    # If user requested more than 1 image, perform multiple calls (one image per call)
    if num_images and int(num_images) > 1:
        total_needed = int(num_images)
        collected = []
        for i in range(total_needed):
            if seed and int(seed) != 0:
                per_seed = int(seed) + i
                # 火山引擎 API 限制：seed 最大值为 99999999
                if per_seed > 99999999:
                    per_seed = (per_seed % 99999999) + 1
            else:
                per_seed = random.randint(1, 99999999)
            print(f"Making call {i+1}/{total_needed} with seed={per_seed}")
            resp_i, imgs_i = call_once(body, i+1, per_seed)
            if imgs_i:
                collected.extend(imgs_i)
            # small safety: don't loop forever; we'll do exactly total_needed attempts

        print(f"Requested {total_needed} images, saved {len(collected)} image files")
    else:
        # single-call path (preserve original behavior)
        print(f"Calling {method_name} with req_key={req_key} width={width} height={height} steps={steps} seed={seed} num_images={num_images}")
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
