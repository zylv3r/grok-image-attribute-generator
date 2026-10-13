"""Derive unpublished QA sheets and verify retention; no live publication or paid calls."""
import hashlib,json,pathlib,sqlite3
from PIL import Image,ImageDraw,ImageOps
root=pathlib.Path(__file__).resolve().parents[1];out=root/'acceptance-output/preview-coverage'
plan=json.loads((root/'docs/preview-coverage/inventory-plan.json').read_text());lib=json.loads((out/'catalog.json').read_text())
attrs={a['id']:a for c in lib['categories'] for a in c['attributes']};sheets=[]
for item in plan['missing_sheets']:
 if not item['ready_values']:continue
 aid=item['attribute'];a=attrs[aid];values=[v for v in a['values'] if v['id'] in item['ready_values']][:4]
 sheet=Image.new('RGB',(640,80+len(values)*190),'#f4f0e8');draw=ImageDraw.Draw(sheet)
 draw.text((14,12),'UNPUBLISHED QA: '+a['name'],fill='black');draw.text((14,32),'Legacy independent examples; not controlled comparisons',fill='black');draw.text((14,52),'Representative subset. Semantic review and mapping required.',fill='black')
 for i,v in enumerate(values):
  p=root/v['thumbnail_url'].lstrip('/')
  with Image.open(p) as im:tile=ImageOps.contain(im.convert('RGB'),(175,175))
  sheet.paste(tile,(14,80+i*190));draw.text((205,100+i*190),v['name'],fill='black');draw.text((205,125+i*190),v['id'],fill='black')
 target=out/('qa-sheet-'+aid+'.jpg');sheet.save(target,quality=90)
 sheets.append({'attribute':aid,'path':str(target.relative_to(root)),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'values':[v['id'] for v in values],'published':False,'paid_calls':0})
(out/'derived-qa-sheets.json').write_text(json.dumps(sheets,indent=2)+'\n')
before=json.loads((out/'preservation-before.json').read_text());changed=[p for p,h in before.items() if not (root/p).is_file() or hashlib.sha256((root/p).read_bytes()).hexdigest()!=h]
old=json.loads((root/'acceptance-output/delivery/3c7f58642509/data/live-final.json').read_text())
old_hashes={v['sha256'] for v in old['legacy']['generated']['files'].values() if 'sha256'in v and v.get('format')=='JPEG'}
current_hashes={hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'generated').rglob('*.jpg')}
missing=old_hashes-current_hashes
con=sqlite3.connect('file:'+str(root/'gallery.sqlite3')+'?mode=ro',uri=True);gallery=con.execute('select count(*) from images').fetchone()[0];con.close()
report={'snapshot_files':len(before),'changed_snapshot_files':changed,'handoff_jpeg_hashes':len(old_hashes),'missing_handoff_jpeg_hashes':sorted(missing),'gallery_rows':gallery,'unpublished_local_sheets':sheets}
(out/'preservation-and-sheets.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='unpublished_local_sheets'}));print('Derived unpublished QA sheets:',len(sheets))
assert not changed and not missing and gallery==1001
