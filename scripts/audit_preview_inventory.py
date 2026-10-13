"""Read-only inventory/planning; never submits jobs or modifies live assets/stores."""
import collections, hashlib, io, json, pathlib, sqlite3, urllib.request
from PIL import Image
ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/preview-coverage';OUT.mkdir(parents=True,exist_ok=True)
EVIDENCE=ROOT/'acceptance-output/preview-coverage';EVIDENCE.mkdir(parents=True,exist_ok=True)
def load(p):return json.loads(p.read_text())
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
lib=json.load(urllib.request.urlopen('http://localhost:8123/api/library'))
aliases=load(ROOT/'catalog/v2/aliases.json')
manifest=load(ROOT/'generated/photographic-previews.json')
legacy={a['id']:a for c in lib['historical_library']['categories'] for a in c['attributes']}
print('Manifest keys:',list(manifest))
photo_records=manifest.get('tasks',{})
if isinstance(photo_records,list):photo_records={str(i):r for i,r in enumerate(photo_records)}
print('Task sample:',str(list(photo_records.items())[:1])[:1200])
items=[];cats=[];sheets=[];groups={};snap={}
for p in sorted((ROOT/'generated').glob('*.jpg')):snap[str(p.relative_to(ROOT))]=digest(p)
for p in [ROOT/'catalog/v1/library.json',ROOT/'generated/photographic-previews.json',ROOT/'gallery.sqlite3',ROOT/'presets.sqlite3']:
 if p.exists():snap[str(p.relative_to(ROOT))]=digest(p)
for p in ROOT.glob('*comparison*.sqlite3'):snap[str(p.relative_to(ROOT))]=digest(p)
for c in lib['categories']:
 count=collections.Counter();methods=collections.Counter();attr_count=collections.Counter()
 for a in c['attributes']:
  photoless=a['preview_method']=='control_only' or a['control']=='swatch'
  attr_count['ready' if a.get('thumbnail_url') else 'intentional' if photoless else 'missing']+=1
  pending=[]
  for v in a['values']:
   status=v.get('thumbnail_status','pending');count[status]+=1
   candidates=[]
   if status=='pending':
    pending.append(v['id']);methods[a['preview_method']]+=1
    for key,alias in aliases.items():
     if alias['disposition'] not in ('keep','move'):continue
     if len(alias['targets'])!=1:continue
     t=alias['targets'][0]
     if t['attribute_id']!=a['id'] or t['value_id']!=v['id']:continue
     la,lv=key.split(':',1);old=next((x for x in legacy.get(la,{}).get('values',[]) if x['id']==lv),None)
     record=photo_records.get(key,{})
     if old and record.get('status')=='completed' and record.get('thumbnail_url','').startswith('/generated/'):
      candidates.append({'legacy_key':key,'url':record['thumbnail_url'],'same_steer':old['steers']==v['steers'],'alias_disposition':alias['disposition'],'publication':'NOT APPROVED; human semantic image review required'})
   items.append({'category':c['id'],'attribute':a['id'],'value':v['id'],'status':status,'method':a['preview_method'],'group':a['comparison_group'],'url':v.get('thumbnail_url'),'legacy_candidates':candidates})
  if not photoless and not a.get('thumbnail_url'):
   ready=[v['id'] for v in a['values'] if v.get('thumbnail_status')=='ready'];sheets.append({'category':c['id'],'attribute':a['id'],'ready_values':ready,'pending_values':pending,'action':'derive locally after semantic validation of representative photographs' if ready else 'wait for first accepted photographs; derive locally','paid_generations':0})
  if not photoless:
   groups.setdefault(a['comparison_group'],{'category':c['id'],'attributes':[]})['attributes'].append({'id':a['id'],'method':a['preview_method'],'pending_values':pending,'baseline_requirements':a.get('preview_contract',{}).get('baseline_requirements',[])})
 cats.append({'category':c['id'],'values':dict(count),'attributes':dict(attr_count),'pending_by_method':dict(methods)})
url_checks={}
for c in lib['categories']:
 for a in c['attributes']:
  for obj in [a]+a['values']:
   for field in ['thumbnail_url','example_url']:
    u=obj.get(field)
    if not u or u in url_checks:continue
    local=ROOT/('generated'+u.split('?')[0] if u.startswith('/preview-atlases/') else u.lstrip('/').split('?')[0])
    try:
     with urllib.request.urlopen('http://localhost:8123'+u) as r:raw=r.read();status=r.status
     with Image.open(io.BytesIO(raw)) as im:im.load();size=list(im.size)
     url_checks[u]={'file_exists':local.is_file(),'http':status,'decoded':True,'size':size,'sha256':hashlib.sha256(raw).hexdigest(),'local_matches_http':local.is_file() and digest(local)==hashlib.sha256(raw).hexdigest()}
    except Exception as e:url_checks[u]={'error':str(e)}
plan={'catalog_sha256':digest(ROOT/'catalog/v2/library.json'),'categories':cats,'pending_items':[i for i in items if i['status']=='pending'],'missing_sheets':sheets,'groups':groups,'reuse_candidate_values':sum(bool(i['legacy_candidates']) for i in items),'ready_values_semantic_review':'Rendering verified, not exhaustive semantic compliance. Hair screenshot has apparent length/label discrepancies; do not certify as controlled examples.'}
(OUT/'inventory-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
(EVIDENCE/'file-http-decode.json').write_text(json.dumps(url_checks,indent=2)+'\n')
(EVIDENCE/'preservation-before.json').write_text(json.dumps(snap,indent=2)+'\n')
print(json.dumps({'categories':cats,'missing_sheets':len(sheets),'groups':len(groups),'reuse_candidate_values':plan['reuse_candidate_values'],'urls':len(url_checks),'url_failures':sum('error'in x for x in url_checks.values()),'original_gallery_jpegs':sum(not p.endswith('-thumb.jpg') for p in snap if p.endswith('.jpg'))},indent=2))
