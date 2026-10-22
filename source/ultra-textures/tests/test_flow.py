"""Single-entry consent and placement tests. No publisher requests or installed game writes."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

PACKAGE=pathlib.Path(os.environ.get('MW4_ADDON_TEST_PACKAGE',pathlib.Path(__file__).parent/'MW4-Ultra-Textures'))
sys.path.insert(0,str(PACKAGE))
import interaction


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name).resolve()
        self.game=self.root/'Game with spaces';sp=self.game/'sp26';sp.mkdir(parents=True)
        (sp/'sp26-cod.exe').write_bytes(b'fixture only')
        self.catalogue=sp/'sp26_cdn.xpak'
        self.catalogue.write_bytes(b'\0'*0x8000+struct.pack('<QIII',17,64<<1,0,0xffffffff)+b'\0'*20)
        (sp/'boot_cdn.xpak').write_bytes(b'\0'*0x8000+b'\0'*20)
        self.package=sp/'MW4-Ultra-Textures'
        shutil.copytree(PACKAGE,self.package,ignore=shutil.ignore_patterns('Data','__pycache__'))
        spec=importlib.util.spec_from_file_location('flow_controller',self.package/'addon.py')
        self.addon=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.addon)
        self.before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in sp.iterdir() if p.is_file()}

    def tearDown(self):
        for path,old in self.before.items():
            if path != self.catalogue: self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),old)
        self.temp.cleanup()

    def cli(self,action,answer='Cancel\n',*args):
        return subprocess.run([sys.executable,str(self.package/'addon.py'),action,'--terminal',*args],
                              input=answer,text=True,capture_output=True,timeout=15)

    def test_placement_in_sp26_autodetects_game_and_external_default_storage(self):
        r=self.cli('plan','','--json');self.assertEqual(r.returncode,0,r.stderr)
        cfg=json.loads((self.package/'Data/settings.json').read_text())
        self.assertEqual(pathlib.Path(cfg['game_root']),self.game)
        self.assertFalse(pathlib.Path(cfg['mirror']).is_relative_to(self.game))
        self.assertEqual(json.loads(r.stdout)['total']['chunks'],1)

    def test_download_decline_creates_no_mirror_or_transfer_state(self):
        r=self.cli('download');self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('highest-quality campaign textures',r.stdout)
        self.assertIn('cancelled',r.stdout)
        cfg=json.loads((self.package/'Data/settings.json').read_text())
        self.assertFalse(pathlib.Path(cfg['mirror']).exists())
        self.assertFalse((self.package/'Data/download-progress.json').exists())

    def test_single_entry_cancel_and_eof_never_authorize_download(self):
        for answer in ('Cancel\n',''):
            r=self.cli('open',answer);self.assertEqual(r.returncode,0,r.stderr)
            self.assertIn('cancelled',r.stdout)
        cfg=json.loads((self.package/'Data/settings.json').read_text())
        self.assertFalse(pathlib.Path(cfg['mirror']).exists())

    def test_plan_changed_during_confirmation_is_not_downloaded(self):
        cfg=self.addon.configure()
        def consent(*args,**kwargs):
            self.catalogue.write_bytes(self.catalogue.read_bytes()+b'changed while dialog open')
            return 'Download'
        with patch.object(interaction,'choose',side_effect=consent),patch.object(self.addon,'vendor_command') as vendor:
            with self.assertRaisesRegex(ValueError,'plan changed'):
                self.addon.download(cfg)
            vendor.assert_not_called()

    def test_no_space_path_offers_location_and_cancel_does_not_download(self):
        cfg=self.addon.configure();cfg['min_free_gib']=1000000;self.addon.save_json(self.addon.CONFIG,cfg)
        r=self.cli('open');self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('Choose Location',r.stdout)
        self.assertFalse(pathlib.Path(cfg['mirror']).exists())

    def test_permission_to_download_does_not_activate_texture_routing(self):
        cfg=self.addon.configure()
        with patch.object(interaction,'choose',return_value='Download'), patch.object(self.addon,'vendor_command',return_value=(0,True)) as vendor, patch.object(self.addon,'start') as start:
            self.assertEqual(self.addon.download(cfg),0)
            self.assertEqual(vendor.call_count,2)
            start.assert_not_called()
        self.assertFalse((self.package/'Data/session.json').exists())


class StorageTests(FlowTests):
    # Reuse placement only; the six existing flow cases run in FlowTests.
    test_placement_in_sp26_autodetects_game_and_external_default_storage = None
    test_download_decline_creates_no_mirror_or_transfer_state = None
    test_single_entry_cancel_and_eof_never_authorize_download = None
    test_plan_changed_during_confirmation_is_not_downloaded = None
    test_no_space_path_offers_location_and_cancel_does_not_download = None
    test_permission_to_download_does_not_activate_texture_routing = None

    def snapshot(self, free=107.2, pending=81.62109428364784):
        return dict(missing=[],free_gib=free,need_gib=round(pending*1.02,2),
                    total=dict(chunks=103631,gib=81.62109428364784,pending_gib=pending,
                               stored_gib=81.62109428364784-pending,stored=0))

    def test_fresh_settings_keep_ten_gib_free(self):
        cfg=self.addon.configure()
        self.assertEqual(cfg['min_free_gib'],10)
        self.assertEqual(cfg['version'],'0.2.2')

    def test_legacy_generated_reserve_migrates_once_and_keeps_storage(self):
        for version in ('0.1','0.2'):
            mirror=self.root/('chosen storage '+version)
            mirror.mkdir()
            (mirror/'existing-object').write_bytes(b'downloaded fixture')
            ready=self.package/'Data/ready.json'
            self.addon.save_json(ready,dict(complete=False,fixture='keep'))
            old=dict(version=version,game_root=str(self.game),mirror=str(mirror),min_free_gib=40)
            self.addon.save_json(self.addon.CONFIG,old)
            cfg=self.addon.configure()
            self.assertEqual(cfg['min_free_gib'],10)
            self.assertEqual(cfg['mirror'],str(mirror))
            self.assertEqual(self.addon.configure(),cfg)
            self.assertEqual((mirror/'existing-object').read_bytes(),b'downloaded fixture')
            self.assertEqual(json.loads(ready.read_text()),dict(complete=False,fixture='keep'))

    def test_custom_reserves_and_current_version_values_are_preserved(self):
        for version,reserve in (('0.2',20),('0.2',75),('0.2.1',40),('0.2.1',0)):
            self.addon.save_json(self.addon.CONFIG,dict(version=version,game_root=str(self.game),
                                mirror=str(self.root/'storage'),min_free_gib=reserve))
            self.assertEqual(self.addon.configure()['min_free_gib'],reserve)

    def test_reported_disk_space_reaches_truthful_confirmation_without_transfer(self):
        cfg=self.addon.configure();seen=[]
        vendor=SimpleNamespace(plan=lambda *a,**k:self.snapshot(),list_files=lambda package:[f'sp26/{package}_cdn.xpak'])
        def cancel(message,*args,**kwargs):
            seen.append(message);return 'Cancel'
        with patch.object(self.addon,'load_vendor',return_value=vendor), \
             patch.object(interaction,'choose',side_effect=cancel), \
             patch.object(self.addon,'vendor_command') as transfer:
            p=self.addon.plan(cfg)
            self.assertTrue(p['fits_with_reserve'])
            self.assertAlmostEqual(p['estimated_free_after_download_gib'],25.5789057164)
            self.assertEqual(self.addon.download(cfg),0)
            transfer.assert_not_called()
        self.assertIn('87.6 GB',seen[0]);self.assertIn('25.6 GiB',seen[0])
        self.assertIn('Minimum space kept free: 10 GiB',seen[0])
        self.assertIn("separate from the game's own texture cache",seen[0])
        self.assertFalse(pathlib.Path(cfg['mirror']).exists())

    def test_insufficient_space_still_blocks_before_consent_and_transfer(self):
        cfg=self.addon.configure()
        vendor=SimpleNamespace(plan=lambda *a,**k:self.snapshot(free=93.2))
        with patch.object(self.addon,'load_vendor',return_value=vendor), \
             patch.object(interaction,'choose') as consent, \
             patch.object(self.addon,'vendor_command') as transfer:
            self.assertFalse(self.addon.plan(cfg)['fits_with_reserve'])
            self.assertEqual(self.addon.download(cfg),2)
            consent.assert_not_called();transfer.assert_not_called()

    def test_resume_estimate_subtracts_only_remaining_bytes(self):
        cfg=self.addon.configure()
        vendor=SimpleNamespace(plan=lambda *a,**k:self.snapshot(free=50,pending=20))
        with patch.object(self.addon,'load_vendor',return_value=vendor):
            self.assertEqual(self.addon.plan(cfg)['estimated_free_after_download_gib'],30)

    def test_ten_gib_reserve_is_passed_to_runtime_downloader(self):
        cfg=self.addon.configure()
        with patch.object(interaction,'choose',return_value='Download'), \
             patch.object(self.addon,'vendor_command',return_value=(0,True)) as vendor:
            self.assertEqual(self.addon.download(cfg),0)
        args=vendor.call_args_list[1].args[1]
        self.assertEqual(args[args.index('--min-free-gib')+1],'10')


class ProgressTests(unittest.TestCase):
    def test_resume_includes_previous_bytes_and_wait_state_is_named(self):
        line=interaction.progress_line(dict(bytes=10*2**30,mibps_now=2,state='offline-wait'),
             dict(kind='download',total_bytes=100*2**30,stored_bytes=40*2**30))
        self.assertIn('50.0%',line);self.assertIn('50.00 / 100.00',line);self.assertIn('Waiting for connection',line)

    def test_stale_progress_from_another_process_is_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td)/'progress.json';p.write_text(json.dumps(dict(pid=123,total=10,done=8)))
            display=interaction.ProgressDisplay(p,dict(kind='verify'),124)
            output=io.StringIO()
            with contextlib.redirect_stdout(output):display.update()
            self.assertEqual(output.getvalue(),'')


from test_addon import MirrorTests


class LiveProgressTests(MirrorTests):
    # Reuse the synthetic HTTP/CDN fixture; inherited transport cases are not repeated here.
    test_download_resume_and_checksums_are_real = None
    test_pause_finishes_current_piece_and_resumes = None
    test_disk_reserve_stops_before_any_transfer = None

    def test_real_download_and_verification_render_progress_and_keep_logs_private(self):
        self.mode='good'
        spec=importlib.util.spec_from_file_location('progress_controller',PACKAGE/'addon.py')
        addon=importlib.util.module_from_spec(spec);spec.loader.exec_module(addon)
        addon.DATA=self.root/'UIData';addon.DATA.mkdir()
        cfg=dict(game_root=str(self.game),mirror=str(self.mirror))
        self.assertEqual(self.run_cmd('init','--scope','sp').returncode,0)
        progress=addon.DATA/'progress.json'
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            code,paused=addon.vendor_command(cfg,['run','--scope','sp','--level','ultra','--upstream-ip','127.0.0.1',
                '--upstream-port',str(self.port),'--workers','1','--retries','0','--min-free-gib','0','--accept-notice',
                '--progress-json',str(progress)],progress_context=dict(kind='download',total_bytes=sum(map(len,self.bodies.values())),stored_bytes=0))
        self.assertEqual((code,paused),(0,False));self.assertIn('100.0%',output.getvalue())
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            code,_=addon.vendor_command(cfg,['verify','--all','--progress-json',str(progress)],progress_context=dict(kind='verify'))
        self.assertEqual(code,0);self.assertIn('Checking files',output.getvalue());self.assertIn('5 / 5',output.getvalue())
        for logfile in (addon.DATA/'Logs').glob('*.txt'):
            self.assertEqual(logfile.stat().st_mode & 0o777,0o600)


if __name__=='__main__':
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in (FlowTests,StorageTests,ProgressTests,LiveProgressTests))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
