"""Hash-pinned versioned persona reference packs; no live comparison approvals."""
import hashlib,io,json,mimetypes,pathlib,re,stat,warnings
from PIL import Image
MAX_BYTES=32*1024*1024

def _read(root,relative,limit=MAX_BYTES):
    parts=relative.split('/')
    if not relative or any(not p or p.startswith('.') or p in ('.','..') for p in parts):raise ValueError('invalid persona path')
    target=root
    for part in parts:
        target=target/part
        if target.is_symlink():raise ValueError('symlink persona asset forbidden')
    if not target.is_file() or not stat.S_ISREG(target.stat().st_mode) or not 0<target.stat().st_size<=limit:raise ValueError('persona asset unavailable')
    raw=target.read_bytes()
    if len(raw)>limit:raise ValueError('persona asset too large')
    return raw

def _pack(root):
    base=pathlib.Path(root)/'base-personas';pointer=base/'current.json'
    if not pointer.exists():return None
    selected=json.loads(_read(base,'current.json',65536));pid=selected.get('id');revision=selected.get('revision')
    if not isinstance(pid,str) or not re.fullmatch('[a-z0-9][a-z0-9-]*',pid) or not isinstance(revision,int) or isinstance(revision,bool) or revision<1:raise ValueError('invalid persona identity')
    expected=pid+'/v'+str(revision)+'/persona.json'
    if selected.get('manifest')!=expected:raise ValueError('invalid persona manifest pointer')
    sha=selected.get('manifest_sha256')
    if not isinstance(sha,str) or not re.fullmatch('[a-f0-9]{64}',sha):raise ValueError('invalid persona manifest hash')
    raw=_read(base,expected,2*1024*1024)
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('persona manifest integrity failed')
    pack=json.loads(raw)
    if pack.get('id')!=pid or pack.get('revision')!=revision or not isinstance(pack.get('assets'),dict):raise ValueError('invalid persona pack')
    return base,pid+'/v'+str(revision)+'/',pack

def summary(root):
    found=_pack(root)
    if found is None:return {'available':False}
    _,prefix,pack=found
    url=lambda p:'/base-personas/'+prefix+p
    return {'available':True,'id':pack['id'],'revision':pack['revision'],'title':pack['title'],'status':pack['status'],'selected_at':pack['selected_at'],'identity_reference_selected':pack['identity_reference_selected'],'controlled_masks_approved':False,'comparison_publication_approved':False,'future_image_model':pack['future_image_model'],'keywords':pack['keywords'],'canonical_face_url':url(pack['canonical_face']),'canonical_face_sha256':pack['canonical_face_sha256'],'canonical_body_url':url(pack['canonical_body']),'canonical_body_sha256':pack['canonical_body_sha256'],'overview_url':url(pack['overview']),'pdf_url':url(pack['pdf']),'caveats':pack['caveats'],'iteration_rule':pack['iteration_rule'],'selected_views':{k:url(v) for k,v in pack['selected_views'].items()},'assets':{url(p):data for p,data in pack['assets'].items()}}

def asset(root,relative):
    found=_pack(root)
    if found is None:raise ValueError('no saved persona')
    base,prefix,pack=found
    if not relative.startswith(prefix):raise ValueError('persona version not selected')
    name=relative[len(prefix):]
    if name not in pack['assets']:raise ValueError('persona asset not allowlisted')
    raw=_read(base,relative);metadata=pack['assets'][name]
    if hashlib.sha256(raw).hexdigest()!=metadata['sha256']:raise ValueError('persona asset integrity failed')
    suffix=pathlib.Path(name).suffix.lower()
    if suffix in ('.jpg','.jpeg','.png'):
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
                if image.width*image.height>25_000_000 or image.format not in ('JPEG','PNG'):raise ValueError('invalid persona image')
        return raw,'image/png' if suffix=='.png' else 'image/jpeg'
    if suffix=='.pdf' and raw.startswith(b'%PDF-'):return raw,'application/pdf'
    if suffix=='.json':json.loads(raw);return raw,'application/json; charset=utf-8'
    raise ValueError('unsupported persona asset type')
