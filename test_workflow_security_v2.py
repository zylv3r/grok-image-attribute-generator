"""Isolated workflow/security regressions; provider calls are mocks only."""
import base64
import copy
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from PIL import Image
import server
from comparisons import ComparisonStore
from gallery import Gallery, save_image
from test_comparisons import library, png


class WorkflowSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.lib = library()
        for cat in self.lib['categories']:
            for attr in cat['attributes']:
                attr['comparison_group'] = 'photography:same_scene' if cat['id'] == 'photography' else cat['id'] + ':' + attr['id']
        self.lib['categories'][1]['attributes'].append({'id': 'warm', 'preview_method': 'white_balance', 'preview_scope': 'global', 'comparison_group': 'photography:same_scene', 'values': [{'id': 'warm', 'preview_params': {'temperature': .3}}]})
        self.lib['categories'][2]['attributes'].append({'id': 'drape', 'preview_method': 'reference_edit', 'preview_scope': 'localized', 'comparison_group': 'wardrobe:drape', 'values': [{'id': 'flow', 'steers': 'flowing drape'}]})
        self.store = ComparisonStore(self.root)
        self.store.list_categories(self.lib)
        self.source = self.root / 'generated' / 'owned.png'
        image = Image.new('RGB', (32,40)); image.putdata([(60+x*3,70+y*2,80) for y in range(40) for x in range(32)]); image.save(self.source)
        self.poly = [[.1,.1],[.5,.1],[.5,.7],[.1,.7]]
        self.provider = Mock(return_value=(base64.b64encode(png(Image.new('RGB', (32,40), 'red'))).decode(), 'image/png'))

    def tearDown(self): self.tmp.cleanup()

    def prepare(self, attr='hair_color', cap=0, grouped=False):
        opts = {'attribute_id': attr} if grouped else {}
        self.store.set_base('hair', self.source, 'owned', **opts)
        r = self.store.set_mask('hair', attr, self.poly)
        return self.store.approve('hair', 'contract', r['contract_hash'], provider_attempt_cap=cap, **opts)

    def render(self, attr='hair_color', key='one', params=None):
        return self.store.render('hair', attr, 'red' if attr=='hair_color' else 'bob', 'masked_recolor' if attr=='hair_color' else 'reference_edit', params or {}, key, self.lib, self.provider)

    def accept(self, r, a, grouped=False):
        opts = {'attribute_id': a['attribute_id']} if grouped else {}
        return self.store.approve('hair','pilot',r['contract_hash'],[a['id']], **opts)

    def test_reopen_requires_note_and_expected_hash_retains_history_assets_attempts(self):
        r=self.prepare('hair_cut',1); a=self.render('hair_cut')
        for fn in (lambda:self.store.set_base('hair',self.source,'owned'),lambda:self.store.set_mask('hair','hair_cut',[])):
            with self.assertRaisesRegex(ValueError,'[Rr]eopen|draft'): fn()
        for digest,note in ((r['contract_hash'],''),('0'*64,'Revise')):
            with self.assertRaises(ValueError): self.store.reopen('hair',digest,note)
        changed=self.store.reopen('hair',r['contract_hash'],'Revise haircut footprint')
        self.assertEqual(changed['state'],'draft');self.assertEqual(changed['budget']['used'],1)
        self.assertTrue(self.store.asset(a['id']));self.assertTrue(any(h['event']=='operator_reopen' and h['data']['previous']['artifacts'] for h in changed['history']))
        self.assertEqual(len(changed['attempts']),1)
        changed=self.store.set_mask('hair','hair_cut',[]);self.assertNotIn('hair_cut',changed['masks'])

    def test_expansion_cycle_preserves_total_and_cross_cycle_idempotency(self):
        r=self.prepare('hair_cut',1);a=self.render('hair_cut');r=self.accept(r,a)
        with self.assertRaises(ValueError):self.store.approve('hair','contract',r['contract_hash'],provider_attempt_cap=3)
        r=self.store.approve('hair','expansion',r['contract_hash'],provider_attempt_cap=1,approval_note='Approve one further edit')
        self.assertEqual(r['budget']['used'],1);self.assertEqual(r['cycle']['used'],0);self.assertEqual(r['cycle']['id'],2)
        self.assertEqual(a,self.render('hair_cut'));self.provider.assert_called_once()
        b=self.render('hair_cut','two');self.assertNotEqual(a['id'],b['id']);self.assertEqual(self.store.review('hair')['budget']['used'],2)
        with self.assertRaises(ValueError):self.render('hair_cut','three')
        self.assertEqual(len(self.store.review('hair')['attempts']),2)

    def test_failed_and_concurrent_reservations_stay_consumed(self):
        r=self.prepare('hair_cut',1);entered,release=Event(),Event()
        def fail(*args):entered.set();release.wait(4);raise RuntimeError('mock ambiguous failure')
        self.provider.side_effect=fail
        with ThreadPoolExecutor(max_workers=2) as pool:
            task=pool.submit(self.render,'hair_cut');self.assertTrue(entered.wait(4))
            for key in ('one','two'):
                with self.assertRaises(ValueError):self.render('hair_cut',key)
            release.set();a=task.result(4)
        self.assertEqual(a['receipt']['status'],'failed');self.assertEqual(self.store.review('hair')['budget']['used'],1)
        self.assertEqual(a,self.render('hair_cut'));self.provider.assert_called_once()
        with self.assertRaises(ValueError):self.store.approve('hair','expansion',r['contract_hash'],provider_attempt_cap=1,approval_note='Premature')

    def test_ambiguous_reservation_survives_store_restart_without_retry_or_unspending(self):
        self.prepare('hair_cut',1)
        self.provider.side_effect=SystemExit('simulated worker interruption')
        with self.assertRaises(SystemExit):self.render('hair_cut')
        self.store=ComparisonStore(self.root)
        current=self.store.review('hair')
        self.assertEqual(current['budget']['used'],1);self.assertEqual(current['cycle']['used'],1)
        self.assertEqual(current['attempts'][0]['status'],'reserved')
        for key in ('one','two'):
            with self.assertRaises(ValueError):self.render('hair_cut',key)
        self.provider.assert_called_once()
        reopened=self.store.reopen('hair',current['contract_hash'],'Explicitly revise after interrupted attempt')
        self.assertEqual(reopened['budget']['used'],1);self.assertEqual(reopened['attempts'][0]['status'],'reserved')

    def test_group_bases_masks_crops_and_same_original_forks_are_independent(self):
        r=self.prepare(grouped=True);a=self.render();b=self.render(key='two')
        self.assertEqual(a['receipt']['base_sha256'],b['receipt']['base_sha256'])
        self.store.set_base('hair',self.source,'owned',crop=[0,0,.5,.5],attribute_id='hair_cut')
        color=self.store.review('hair',attribute_id='hair_color');cut=self.store.review('hair',attribute_id='hair_cut')
        self.assertEqual(color['contract_hash'],r['contract_hash']);self.assertEqual(color['baseline']['sha256'],a['receipt']['base_sha256'])
        self.assertEqual(len(color['artifacts']),2);self.assertEqual(cut['baseline']['width'],16);self.assertEqual(cut['masks'],{})
        p=self.store.set_base('photography',self.source,'owned',attribute_id='grain')
        self.assertEqual(p['baseline'],self.store.review('photography',attribute_id='warm')['baseline'])
        with self.assertRaises(ValueError):self.store.review('hair',attribute_id='hair_color',group='hair:hair_cut')

    def test_photography_same_scene_forks_keep_the_same_contract_and_candidates(self):
        self.store.set_base('photography',self.source,'owned',attribute_id='grain')
        a=self.store.render('photography','grain','fine','simulated_optics',{'effect':'grain'},'grain',self.lib)
        b=self.store.render('photography','warm','warm','white_balance',{},'warm',self.lib)
        self.assertEqual(a['receipt']['base_sha256'],b['receipt']['base_sha256'])
        self.assertEqual(a['receipt']['contract_hash'],b['receipt']['contract_hash'])
        self.assertEqual(len(self.store.review('photography',attribute_id='grain')['artifacts']),2)

    def test_custom_rgb_aliases_are_explicit_and_cannot_publish_as_catalog(self):
        r=self.prepare()
        for index,params in enumerate(({'colour':{'hex':'#ff0000'}},{'color':'#ff0000'},{'hex':'#ff0000'})):
            a=self.render(key=str(index),params=params);receipt=a['receipt']
            self.assertEqual(receipt['effective_params']['colour']['hex'],'#ff0000');self.assertTrue(receipt['custom_override'])
            self.assertEqual(receipt['supplied_overrides'],params);self.assertEqual(receipt['catalog_params']['colour']['hex'],'#a63d21')
            self.assertTrue(a['custom']);r=self.accept(r,a)
            with self.assertRaisesRegex(ValueError,'[Cc]ustom|catalog'):self.store.approve('hair','publish',r['contract_hash'],[a['id']])
        with self.assertRaises(ValueError):self.render(key='conflict',params={'color':'#ff0000','hex':'#ffffff'})

    def test_no_person_reference_edit_rejected_before_reservation(self):
        for attr in self.lib['categories'][2]['attributes']: attr['comparison_group']='wardrobe:same'
        self.store.list_categories(self.lib)
        self.store.render('wardrobe','garment_color','red','fabric_swatch',{},'swatch',self.lib)
        r=self.store.set_mask('wardrobe','drape',self.poly)
        r=self.store.approve('wardrobe','contract',r['contract_hash'],provider_attempt_cap=1,attribute_id='drape')
        with self.assertRaisesRegex(ValueError,'adult woman|person'):
            self.store.render('wardrobe','drape','flow','reference_edit',{},'native',self.lib,self.provider)
        self.provider.assert_not_called();self.assertEqual(self.store.review('wardrobe')['budget']['used'],0)
        self.assertEqual(len(self.store.review('wardrobe',attribute_id='drape')['attempts']),1) # local swatch only

    def test_published_provenance_checks_reference_mask_overlay_output_and_receipt(self):
        r=self.prepare();a=self.render();r=self.accept(r,a);r=self.store.approve('hair','publish',r['contract_hash'],[a['id']])
        self.assertTrue(self.store.publication_valid('hair',a['id']))
        entries=[r['baseline']['asset_id'],r['masks']['hair_color']['asset_id'],r['masks']['hair_color']['overlay_asset_id'],a['id']]
        for ident in entries:
            path=self.store.asset(ident);raw=path.read_bytes();path.write_bytes(b'corrupt')
            self.assertFalse(self.store.publication_valid('hair',a['id']));path.write_bytes(raw)
        with self.store._transaction() as db:
            record=self.store._get(db,'hair');record['artifacts'][0]['receipt']['mask_overlay_sha256']='0'*64;self.store._save(db,record)
        self.assertFalse(self.store.publication_valid('hair',a['id']));self.assertTrue(self.store.review('hair')['history'])

    def test_reopen_during_inflight_edit_withholds_output_and_preserves_reservation(self):
        r=self.prepare('hair_cut',1)
        def reopen(*args):
            self.store.reopen('hair',r['contract_hash'],'Stop this contract and revise')
            return base64.b64encode(png(Image.new('RGB',(32,40),'red'))).decode(),'image/png'
        self.provider.side_effect=reopen
        result=self.render('hair_cut')
        self.assertEqual(result['receipt']['status'],'failed')
        current=self.store.review('hair');self.assertEqual(current['state'],'draft')
        self.assertNotEqual(current['contract_hash'],r['contract_hash']);self.assertEqual(current['budget']['used'],1)
        self.assertEqual(current['artifacts'],[])
        with self.assertRaises(ValueError):self.render('hair_cut') # tombstone from former revision

    def test_published_state_guards_and_explicit_reopen_preserve_assets(self):
        r=self.prepare(grouped=True);a=self.render();r=self.accept(r,a,grouped=True)
        r=self.store.approve('hair','publish',r['contract_hash'],[a['id']],attribute_id='hair_color')
        for action in (lambda:self.store.set_base('hair',self.source,'owned',attribute_id='hair_color'),
                       lambda:self.store.set_mask('hair','hair_color',[]),lambda:self.render(key='new'),
                       lambda:self.store.approve('hair','pilot',r['contract_hash'],[a['id']],attribute_id='hair_color')):
            with self.assertRaisesRegex(ValueError,'Reopen'):action()
        reopened=self.store.reopen('hair',r['contract_hash'],'Revise published colour mask',attribute_id='hair_color')
        self.assertTrue(self.store.asset(a['id']));self.assertEqual(reopened['published_artifact_ids'],[])
        self.assertNotEqual(reopened['contract_hash'],r['contract_hash'])

    def test_expansion_concurrency_and_request_tombstone_are_shared_across_cycles(self):
        r=self.prepare('hair_cut',1);a=self.render('hair_cut');r=self.accept(r,a)
        r=self.store.approve('hair','expansion',r['contract_hash'],provider_attempt_cap=1,approval_note='One additional edit')
        entered,release=Event(),Event()
        def provider(*args):
            entered.set();release.wait(4)
            return base64.b64encode(png(Image.new('RGB',(32,40),'blue'))).decode(),'image/png'
        self.provider.side_effect=provider
        with ThreadPoolExecutor(max_workers=2) as pool:
            task=pool.submit(self.render,'hair_cut','two');self.assertTrue(entered.wait(4))
            self.assertEqual(a,self.render('hair_cut','one'))
            for key in ('two','three'):
                with self.assertRaises(ValueError):self.render('hair_cut',key)
            release.set();result=task.result(4)
        self.assertEqual(result,self.render('hair_cut','two'));self.assertEqual(self.provider.call_count,2)
        current=self.store.review('hair');self.assertEqual(current['budget']['used'],2);self.assertEqual(current['cycle']['used'],1)

    def test_requested_snapshot_precedes_defaults(self):
        lib=library();lib['categories'].append({'id':'defaults','attributes':[{'id':'gender','name':'Gender','type':'exclusive','default':'woman','values':[{'id':'woman','name':'Woman','steers':'adult woman'}]}]})
        result=server.Catalog(lib).preview({'selections':{'hair_color':['red']}});plan=result['plans'][0]
        self.assertNotIn('gender',plan['requested_selection_snapshot']['selections'])
        self.assertEqual(plan['requested_selection_snapshot']['defaulted'],['gender']);self.assertEqual(plan['selections']['gender'],['woman'])
        self.assertEqual(plan['requested_selection_snapshot']['requested_maps'],{'selections':{'hair_color':['red']},'whitelist':{}})
        empty=server.Catalog(lib).preview({'selections':{'gender':[]}})['plans'][0]
        self.assertEqual(empty['requested_selection_snapshot']['requested_maps']['selections'],{'gender':[]})
        self.assertEqual(empty['requested_selection_snapshot']['defaulted'],['gender'])

    def test_moved_gallery_filters_expand_only_one_to_one_moves(self):
        g=Gallery(self.root/'gallery.sqlite3',self.root/'generated')
        g.set_filter_aliases({'old:red':{'disposition':'move','targets':[{'attribute_id':'new','value_id':'red'}]},'old:recipe':{'disposition':'disclosed_recipe','targets':[{'attribute_id':'new','value_id':'other'}]}})
        image=save_image(base64.b64encode(png(Image.new('RGB',(8,8),'red'))).decode(),g.output_dir)
        g.add_image(image,'archived fixture',{'old':['red','recipe']})
        self.assertEqual(g.query(filters={'new':['red']})['total'],1);self.assertEqual(g.query(filters={'old':['red']})['total'],1)
        self.assertEqual(g.query(filters={'new':['other']})['total'],0);self.assertEqual(g.query()['items'][0]['selections'],{'old':['red','recipe']})


class ApplicationWorkflowTests(unittest.TestCase):
    def test_api_no_person_native_denial_makes_zero_calls_and_uses_zero_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);lib=library()
            cat=lib['categories'][2]
            cat['attributes'].append({'id':'drape','name':'Drape','type':'exclusive','preview_method':'reference_edit',
                                     'preview_scope':'localized','values':[{'id':'flow','name':'Flow','steers':'flowing drape'}]})
            for attr in cat['attributes']:attr['comparison_group']='wardrobe:same'
            bundle={'library':lib,'legacy_library':copy.deepcopy(lib),'aliases':{},'retired':{},'coverage':{}}
            provider=Mock(side_effect=AssertionError('No paid calls'))
            app=server.Application(root,catalog=server.Catalog(lib,bundle),provider=provider,edit_provider=provider)
            try:
                app.comparison_post('wardrobe','preview',{'attribute_id':'garment_color','value_id':'red','method':'fabric_swatch','request_key':'swatch'})
                r=app.comparison_post('wardrobe','mask',{'attribute_id':'drape','polygon':[[.1,.1],[.5,.1],[.5,.7],[.1,.7]]})
                app.comparison_post('wardrobe','approve',{'attribute_id':'drape','stage':'contract','expected_contract_hash':r['contract_hash'],'provider_attempt_cap':1})
                with self.assertRaisesRegex(ValueError,'adult woman|person'):
                    app.comparison_post('wardrobe','preview',{'attribute_id':'drape','value_id':'flow','method':'reference_edit','request_key':'native'})
                current=app.comparisons.review('wardrobe',attribute_id='drape')
                self.assertEqual(current['budget']['used'],0);self.assertEqual(current['cycle']['used'],0)
                self.assertFalse(any(a['receipt']['provider_attempt_reserved'] for a in current['attempts']))
                provider.assert_not_called()
            finally:app.close()

    def test_api_red_override_cannot_publish_as_platinum(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);shutil.copytree(server.ROOT/'catalog',root/'catalog');shutil.copyfile(server.ROOT/'library.json',root/'library.json')
            provider=Mock(side_effect=AssertionError('No paid calls'))
            app=server.Application(root,provider=provider,edit_provider=provider)
            try:
                owned=app.store.add_image(save_image(base64.b64encode(png(Image.new('RGB',(32,40),(100,110,120)))).decode(),app.store.output_dir),'isolated fixture',{})
                review=app.comparisons.review('hair',attribute_id='hair_color',group='hair:hair_color')
                requirements=list(review['baseline_requirements']);self.assertTrue(requirements)
                base={'image_id':owned['id'],'attribute_id':'hair_color','group':'hair:hair_color'}
                with self.assertRaisesRegex(ValueError,'Exact operator baseline confirmations are required'):
                    app.comparison_post('hair','base',base)
                self.assertEqual(app.comparisons.review('hair',attribute_id='hair_color',group='hair:hair_color'),review)
                provider.assert_not_called()
                # Isolated simulated-human assertions; no live operator approval.
                r=app.comparison_post('hair','base',{**base,'baseline_confirmations':requirements})
                self.assertEqual(r['baseline']['baseline_confirmations'],requirements)
                r=app.comparison_post('hair','mask',{'attribute_id':'hair_color','polygon':[[.1,.1],[.5,.1],[.5,.7],[.1,.7]]})
                common={'attribute_id':'hair_color','expected_contract_hash':r['contract_hash']}
                app.comparison_post('hair','approve',{**common,'stage':'contract'})
                a=app.comparison_post('hair','preview',{'attribute_id':'hair_color','value_id':'platinum','method':'masked_recolor','request_key':'custom','params':{'hex':'#ff0000'}})
                self.assertEqual(a['receipt']['catalog_params']['colour']['hex'],'#e8e1ce');self.assertEqual(a['receipt']['effective_params']['colour']['hex'],'#ff0000')
                app.comparison_post('hair','approve',{**common,'stage':'pilot','artifact_ids':[a['id']]})
                with self.assertRaisesRegex(ValueError,'Custom'):
                    app.comparison_post('hair','approve',{**common,'stage':'publish','artifact_ids':[a['id']]})
                self.assertEqual(app.comparisons.review('hair',attribute_id='hair_color')['state'],'pilot_accepted');provider.assert_not_called()
            finally:app.close()

    def test_group_publication_projection_restart_and_tamper_withholding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);shutil.copytree(server.ROOT/'catalog',root/'catalog');shutil.copyfile(server.ROOT/'library.json',root/'library.json')
            provider=Mock(side_effect=AssertionError('No paid calls'))
            app=server.Application(root,provider=provider,edit_provider=provider)
            try:
                record=save_image(base64.b64encode(png(Image.new('RGB',(32,40),(100,110,120)))).decode(),app.store.output_dir)
                owned=app.store.add_image(record,'isolated reference',{})
                review=app.comparisons.review('hair',attribute_id='hair_color',group='hair:hair_color')
                requirements=list(review['baseline_requirements']);self.assertTrue(requirements)
                base={'image_id':owned['id'],'attribute_id':'hair_color','group':'hair:hair_color'}
                with self.assertRaisesRegex(ValueError,'Exact operator baseline confirmations are required'):
                    app.comparison_post('hair','base',base)
                self.assertEqual(app.comparisons.review('hair',attribute_id='hair_color',group='hair:hair_color'),review)
                provider.assert_not_called()
                # Isolated simulated-human assertions; no live operator approval.
                r=app.comparison_post('hair','base',{**base,'baseline_confirmations':requirements})
                self.assertEqual(r['baseline']['baseline_confirmations'],requirements)
                r=app.comparison_post('hair','mask',{'attribute_id':'hair_color','polygon':[[.1,.1],[.5,.1],[.5,.7],[.1,.7]]})
                common={'attribute_id':'hair_color','expected_contract_hash':r['contract_hash']}
                app.comparison_post('hair','approve',{**common,'stage':'contract'})
                a=app.comparison_post('hair','preview',{'attribute_id':'hair_color','value_id':'platinum','method':'masked_recolor','request_key':'publish','params':{}})
                app.comparison_post('hair','approve',{**common,'stage':'pilot','artifact_ids':[a['id']]})
                r=app.comparison_post('hair','approve',{**common,'stage':'publish','artifact_ids':[a['id']]})
                self.assertNotEqual(app.comparisons.review('hair')['state'],'published')
            finally:app.close()
            app=server.Application(root,provider=provider,edit_provider=provider)
            try:
                after=app.comparisons.review('hair',attribute_id='hair_color');self.assertEqual(after['contract_hash'],r['contract_hash']);self.assertEqual(after['state'],'published')
                def value():return next(v for c in app.thumbnail_library()[0]['categories'] for at in c['attributes'] if at['id']=='hair_color' for v in at['values'] if v['id']=='platinum')
                self.assertEqual(value()['thumbnail_source'],'approved_comparison')
                for ident in (after['baseline']['asset_id'],after['masks']['hair_color']['asset_id'],after['masks']['hair_color']['overlay_asset_id'],a['id']):
                    path=app.comparisons.asset(ident);raw=path.read_bytes();path.write_bytes(b'tampered')
                    self.assertEqual(value()['thumbnail_status'],'review_required');self.assertEqual(value()['thumbnail_url'],'')
                    path.write_bytes(raw);self.assertEqual(value()['thumbnail_source'],'approved_comparison')
                self.assertEqual(app.comparisons.review('hair',attribute_id='hair_color')['state'],'published');provider.assert_not_called()
            finally:app.close()

# Exercise the real HTTP guards with the existing isolated mocked-provider fixture.
import test_server_v2

class WorkflowHTTPTests(test_server_v2.ComparisonHTTPTests):
    def test_targeted_group_review_reopen_origin_hash_note_and_raw_edit_guards(self):
        status,r,_=self.post('base',{'image_id':self.image['id'],'attribute_id':'color'})
        self.assertEqual(status,200,r);self.assertEqual(r['group'],'test')
        status,r,_=self.post('mask',{'attribute_id':'color','polygon':[[.1,.1],[.5,.1],[.5,.7],[.1,.7]]})
        self.assertEqual(status,200,r)
        self.assertEqual(self.request('GET','/api/comparisons/test?attribute_id=color')[1]['baseline'],r['baseline'])
        self.assertEqual(self.request('GET','/api/comparisons/test?attribute_id=color&group=other')[0],400)
        self.assertEqual(self.request('GET','/api/comparisons/test?attribute_id=')[0],400)
        self.assertEqual(self.post('base',{'image_id':self.image['id'],'attribute_id':None})[0],400)
        common={'attribute_id':'color','expected_contract_hash':r['contract_hash']}
        self.assertEqual(self.post('approve',{**common,'stage':'contract'})[0],200)
        status,a,_=self.post('preview',{'attribute_id':'color','value_id':'blue','method':'masked_recolor','request_key':'group-blue'})
        self.assertEqual(status,200,a)
        for stage in ('pilot','publish'):
            self.assertEqual(self.post('approve',{**common,'stage':stage,'artifact_ids':[a['id']]})[0],200)
        self.assertEqual(self.post('base',{'image_id':self.image['id'],'attribute_id':'color'})[0],400)
        self.assertEqual(self.post('mask',{'attribute_id':'color','polygon':[]})[0],400)
        body={**common,'approval_note':'Revise published mask'}
        self.assertEqual(self.request('POST','/api/comparisons/test/reopen',body)[0],403)
        self.assertEqual(self.post('reopen',{**body,'expected_contract_hash':'0'*64})[0],400)
        self.assertEqual(self.post('reopen',{**body,'approval_note':''})[0],400)
        status,current,_=self.post('reopen',body)
        self.assertEqual(status,200,current);self.assertEqual(current['state'],'draft')
        self.assertNotEqual(current['contract_hash'],r['contract_hash'])
        self.assertTrue(any(h['event']=='operator_reopen' for h in current['history']))
        self.assertEqual(self.request('GET',a['url'])[0],200)
        self.edits.assert_not_called();self.provider.assert_not_called()

for _name in dir(test_server_v2.ComparisonHTTPTests):
    if _name.startswith('test_') and _name not in WorkflowHTTPTests.__dict__:
        setattr(WorkflowHTTPTests,_name,None)

if __name__=='__main__':unittest.main()
