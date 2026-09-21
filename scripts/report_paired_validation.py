"""Generate the local, self-contained visual audit report."""
from pathlib import Path
from io import BytesIO
import json,html,base64
import numpy as np
from PIL import Image
from scripts.paired_fuji_validation import ROOT,OUT


def picture(a):
    im=Image.fromarray(np.round(np.clip(a,0,1)*255).astype('uint8'));b=BytesIO();im.save(b,'JPEG',quality=90)
    return 'data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()


def main():
    fit=json.loads((OUT/'candidate-fit-per-film.json').read_text());selection=json.loads((ROOT/'selection.json').read_text())
    cards=[]
    for row in sorted(fit['images'],key=lambda x:(x['split']!='test',x['recipe']['film'],x['raf'])):
        z=np.load(ROOT/'cache'/(row['id']+'.npz'));candidate=np.load(OUT/(row['id']+'-candidate-per-film.npy'))
        uncertain='excluded_from_color_summary' in row
        title=html.escape(Path(row['raf']).name)
        settings=row['recipe']
        caption=f"{settings['film']} · DR{settings['dynamic_range']} · H {settings['highlights']:+g} · S {settings['shadows']:+g} · Couleur {settings['color']:+g}"
        m=row['gui_reference_guided'];n=row['candidate']
        imgs=''.join(f'<figure><img loading="lazy" src="{picture(a)}"><figcaption>{label}</figcaption></figure>' for label,a in [('JPEG Fuji de référence',z['target']),('Moteur actuel, import corrigé',z['gui']),('Essai par film — non intégré',candidate)])
        message="Recadrage téléconvertisseur non aligné : hors synthèse couleur." if uncertain else f"ΔE00 médian : actuel {m['de00_median']:.2f} → essai {n['de00_median']:.2f}. Erreur lumineuse : {m['luma_rmse']:.3f} → {n['luma_rmse']:.3f}."
        cards.append(f'<article data-film="{settings["film"]}" data-split="{row["split"]}"><h2>{title} <small>{"Vérification" if row["split"]=="test" else "Ajustement"}</small></h2><p>{caption}</p><div class="images">{imgs}</div><p>{message}</p></article>')
    table=[]
    for film,s in fit['summary'].items():
        a=s['current_gui_reference_guided'];b=s['candidate_no_reference']
        table.append(f'<tr><td>{film}</td><td>{s["test_images"]}</td><td>{a["de00_median"]:.2f}</td><td>{b["de00_median"]:.2f}</td><td>{b["de00_p90"]:.2f}</td><td>{b["luma_rmse"]:.3f}</td><td>Insuffisant</td></tr>')
    page='''<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Audit RAF / JPEG — KŌRA</title><style>
body{background:#191b19;color:#e7e8e2;font:16px system-ui;margin:32px auto;max-width:1300;padding:0 20px}h1{font-size:32px}p{line-height:1.55;max-width:1050px}small{font-size:14px;color:#c5caa9}article{margin:28px 0;padding:18px;background:#252824;border:1px solid #45493f;border-radius:8px}h2{font-size:20px;margin:0}.images{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}figure{margin:0}img{width:100%;height:320px;object-fit:contain;background:#101210}figcaption{margin-top:8px;color:#d4d6c9}select{padding:10px;background:#30362d;color:white;margin:8px;border:1px solid #777}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:10px;text-align:left;border-bottom:1px solid #4d5147}.verdict{padding:18px;border-left:4px solid #d8b278;background:#2d2922} @media(max-width:750px){.images{grid-template-columns:1fr}table{display:block;overflow:auto}}</style>
<h1>Comparaison des RAF et JPEG du X100VI</h1><p class="verdict"><strong>Correspondance insuffisante : pas de transfert aux DNG.</strong><br>Les deux essais d'ajustement restent des expériences locales. Seules les corrections certaines d'import des métadonnées sont intégrées au logiciel.</p>
<p>108 couples locaux inventoriés. Un lot de 27 couples a été sélectionné avant mesure, avec au maximum deux exemples par journée et recette : 15 pour ajuster les paramètres et 12 pour vérifier sur d'autres journées. Un couple avec téléconvertisseur n'est pas correctement aligné et reste affiché mais exclu de la synthèse couleur. Certains couples hors lot ont une balance des blancs différente ; ils ne permettent pas de comparer directement le décodage actuel.</p>
<p>Les métriques évaluent les couleurs et les tons à 384 pixels, après léger lissage et exclusion des zones presque noires ou blanches. Elles ne valident pas le grain, la netteté, les détails à pleine résolution ou chaque curseur séparément. ΔE00 plus faible = couleurs plus proches. Les critères choisis sont ΔE00 médian ≤3, percentile 90 ≤6 et erreur lumineuse ≤0,03 ; ce sont des objectifs du projet, pas des seuils officiels Fuji.</p>
<table><thead><tr><th>Film</th><th>Vérifications</th><th>ΔE actuel</th><th>ΔE essai</th><th>P90 essai</th><th>Erreur lumière</th><th>Décision</th></tr></thead><tbody>'''+''.join(table)+'''</tbody></table>
<p>Le moteur actuel estime déjà l'exposition depuis l'aperçu incorporé : cette aide doit être prise en compte dans l'interprétation de son score. Les essais ajustent des paramètres sur les seules photos d'apprentissage et n'utilisent pas l'aperçu du fichier pour leur exposition. La vérification n'est donc pas celle d'un moteur entièrement sans référence pour la colonne « actuel ». Les deux modèles ont été examinés sur ce même lot de vérification ; ce n'est pas un test final aveugle.</p>
<p>Les réglages optimisés poussent plusieurs commandes presque à zéro. Les adopter rendrait ces commandes inopérantes sans prouver la réponse Fuji. Les JPEG ne fournissent qu'une recette par prise de vue : les copies retrouvées ne constituent pas des variations isolées d'un même réglage.</p>
<label>Film<select id="film"><option value="">Tous</option><option>classic_negative</option><option>classic_chrome</option><option>acros</option></select></label><label>Lot<select id="split"><option value="">Tous</option><option value="test" selected>Vérification</option><option value="train">Ajustement</option></select></label>
'''+''.join(cards)+'''<script>function filter(){document.querySelectorAll('article').forEach(a=>{a.hidden=(film.value&&a.dataset.film!==film.value)||(split.value&&a.dataset.split!==split.value)})}const film=document.querySelector('#film'),split=document.querySelector('#split');film.onchange=split.onchange=filter;filter();</script></html>'''
    (OUT/'rapport.html').write_text(page)
    print(OUT/'rapport.html')

if __name__=='__main__':main()
