"""Measure public Fuji reference pairs; never changes the GUI renderer.

Run: .venv/bin/python -m scripts.audit_online_references
Inputs remain in research/reference-tones. Display-luma measurements are not
scene-linear exposure measurements or a recovered native processing curve.
"""
import hashlib
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, ImageDraw
from kora.recipe_effects import chrome_effect

ROOT = Path('research/reference-tones')
OUT = Path('outputs/online-reference-audit')
WEIGHTS = np.array([.2126, .7152, .0722], np.float32)
FAQ = 'https://digitalcamera-support-en.fujifilm.com/digitalcameraengpcdetail?aid=000008353'
IMPRESS = 'https://dc.watch.impress.co.jp/docs/review/minirepo/1407441.html'
PELTIER = 'https://www.jmpeltier.com/fujifilm-highlight-shadow-tones/'


def read(name, crop=None):
    with Image.open(ROOT/name) as im:
        im = ImageOps.exif_transpose(im).convert('RGB')
        if crop:
            im = im.crop(crop)
        im.thumbnail((720, 720), Image.Resampling.LANCZOS)
        return np.asarray(im, dtype=np.float32)/255


def luma(a):
    return np.sum(a*WEIGHTS, axis=-1)


def align(a, b):
    b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
    matrix = np.eye(2, 3, dtype=np.float32)
    error = None
    try:
        score, matrix = cv2.findTransformECC(luma(a), luma(b), matrix,
            cv2.MOTION_AFFINE, (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 120, 1e-6), None, 5)
    except cv2.error as exc:
        score, error = None, str(exc)
    sane = bool(score is not None and score > .85 and
                np.max(np.abs(matrix[:, :2]-np.eye(2))) < .04 and
                np.max(np.abs(matrix[:, 2])) < 12)
    warped = cv2.warpAffine(b, matrix, (a.shape[1], a.shape[0]),
        flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
    valid = cv2.warpAffine(np.ones(b.shape[:2], np.uint8), matrix,
        (a.shape[1], a.shape[0]), flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP).astype(bool)
    valid[:8] = False; valid[-8:] = False; valid[:, :8] = False; valid[:, -8:] = False
    if not sane:
        valid[:] = False
    return warped, valid, {'correlation': score, 'sane': sane, 'matrix': matrix.tolist(), 'error': error}


def measure(a, b, valid):
    # Smooth resampling/compression differences. Keep edges out of the curve
    # estimate: a subpixel geometric error must not become a tonal response.
    y = cv2.GaussianBlur(luma(a), (5, 5), .8)
    z = cv2.GaussianBlur(luma(b), (5, 5), .8)
    gradient = np.hypot(*np.gradient(y))
    valid = valid & (gradient < .035) & (y > .02) & (y < .98)
    bins = []
    for low in np.arange(0, 1, .1):
        mask = valid & (y >= low) & (y < low+.1)
        count = int(mask.sum())
        bins.append({'input_interval': [float(low), float(low+.1)], 'pixels': count,
            'median_delta_8bit': float(np.median((z-y)[mask])*255) if count >= 50 else None,
            'delta_p10_p90_8bit': (np.percentile((z-y)[mask]*255, [10, 90]).tolist() if count >= 50 else None)})
    return {'valid_pixels': int(valid.sum()), 'bins': bins}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    assets = []
    refs = {'highlight-0': 'PCE3', 'highlight-minus2': 'PCE8', 'highlight-plus4': 'PCEI',
            'shadow-0': 'PCEX', 'shadow-minus2': 'PCF1', 'shadow-plus4': 'PCF6'}
    for path in sorted(ROOT.iterdir()):
        if path.suffix not in ('.jpg', '.png'):
            continue
        with Image.open(path) as im:
            size = list(im.size)
            im.verify()
        if path.stem in refs:
            source = FAQ
            url = 'https://digitalcamera-support-en.fujifilm.com/servlet/rtaImage?eid=ka0RC000000djbZ&feoid=00N2w000004gL1A&refid=0EM5i000003'+refs[path.stem]
            quality = 'annotated low-resolution illustration; camera for individual tone examples unspecified'
        elif path.stem.startswith('peltier-'):
            source = PELTIER
            url = 'https://www.jmpeltier.com/wp-content/uploads/2019/07/HSTXR'+path.stem.split('-')[-1]+'.jpg'
            quality = 'X-T2 X RAW STUDIO screenshot; multiple tone controls changed together'
        else:
            source = IMPRESS
            url = 'https://asset.watch.impress.co.jp/img/dcw/docs/1407/441/'+path.stem.split('-')[-1]+'.jpg'
            quality = 'X-E4 author-described camera/X RAW STUDIO comparison; Lightroom export in EXIF; no paired RAF'
        assets.append({'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                       'size': size, 'source': source, 'url': url, 'quality': quality})
    (ROOT/'manifest.json').write_text(json.dumps(assets, indent=2))
    paths = [str(ROOT/a['file']) for a in assets if a['file'].startswith('impress-')]
    meta = subprocess.run(['exiftool', '-j', '-G1', '-a', '-Model', '-Software', '-ColorSpace',
        '-DateTimeOriginal', '-ExposureTime', '-ISO', '-FNumber', '-ImageSize', '-ProfileDescription', *paths],
        check=True, capture_output=True, text=True).stdout
    (ROOT/'metadata.json').write_text(meta)
    pairs = []
    # Right-hand detail, excluding the yellow arrow and frames. Identical
    # coordinates followed by constrained affine registration; no colour fit.
    for control in ('highlight', 'shadow'):
        for setting in ('minus2', 'plus4'):
            pairs.append((f'official-{control}-{setting}', f'{control}-0.png',
                          f'{control}-{setting}.png', (540, 8, 865, 274), None))
    for title, first, second, settings in [
        ('exposure-plus1', '12b', '12c', {'exposure_ev': 1}),
        ('provia-to-classic-negative', '13b', '13c', {'film': 'classic_negative'}),
        ('fx-blue-strong', '15b', '15c', {'color_chrome_fx_blue': 'strong'}),
        ('wb-shade', '16b', '16c', {'white_balance': 'shade'}),
        ('wb-r4-b4', '16b', '16e', {'wb_red': 4, 'wb_blue': 4}),
        ('tone-soft', '17b', '17c', {'highlights': -1, 'shadows': -1.5}),
        ('color-plus3', '18b', '18c', {'color': 3}),
        ('tone-hard', '26a', '26b', {'highlights': 2.5, 'shadows': 1}),
    ]:
        pairs.append(('impress-'+title, 'impress-'+first+'.jpg', 'impress-'+second+'.jpg', None, settings))
    results = []
    for title, first, second, crop, settings in pairs:
        a = read(first, crop); b, mask, registration = align(a, read(second, crop))
        row = {'id': title, 'files': [first, second], 'crop': crop,
               'settings_from_article': settings, 'registration': registration,
               'response': measure(a, b, mask)}
        if title == 'impress-fx-blue-strong' and registration['sane']:
            prediction = chrome_effect(a, 'strong', blue_only=True)
            blue = mask & (a[..., 2] > a[..., 0]+.05) & (a[..., 2] > a[..., 1]+.03)
            row['current_fx_blue_secondary_check'] = {
                'blue_pixels': int(blue.sum()),
                'identity_rgb_mae_8bit': float(np.abs(a-b)[blue].mean()*255),
                'model_rgb_mae_8bit': float(np.abs(prediction-b)[blue].mean()*255),
                'observed_median_luma_delta_8bit': float(np.median(luma(b-a)[blue])*255),
                'model_median_luma_delta_8bit': float(np.median(luma(prediction-a)[blue])*255),
                'scope': 'Post-display effect only, not full RAW pipeline accuracy; no fit on this scene.'}
        results.append(row)
        canvas = Image.new('RGB', (a.shape[1]*2, a.shape[0]+30), '#202020')
        canvas.paste(Image.fromarray(np.uint8(np.clip(a, 0, 1)*255)), (0, 30))
        canvas.paste(Image.fromarray(np.uint8(np.clip(b, 0, 1)*255)), (a.shape[1], 30))
        ImageDraw.Draw(canvas).text((8, 8), title+' | published base / registered variant', fill='white')
        canvas.save(OUT/(title+'.jpg'), quality=92)
    report = {'units': 'weighted encoded RGB (display luma), scaled to 8-bit; not EV',
              'production_changed': False,
              'limitations': ['No RAF for these scenes', 'Web/export processing may alter the response',
                  'Not a validation of X100VI or DNG fidelity', 'Do not fit film or WB from luminance bins'],
              'pairs': results}
    (OUT/'measurements.json').write_text(json.dumps(report, indent=2))
    for row in results:
        print(row['id'], row['registration']['sane'], row['response']['valid_pixels'])
        if 'current_fx_blue_secondary_check' in row:
            print(json.dumps(row['current_fx_blue_secondary_check'], indent=2))


if __name__ == '__main__':
    main()
