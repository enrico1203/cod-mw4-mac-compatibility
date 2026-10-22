"""Real temporary files/SQLite + controller tests for redundant-object cleanup."""
import hashlib
import json
import os
import pathlib
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PACKAGE=pathlib.Path(os.environ.get('MW4_ADDON_TEST_PACKAGE',pathlib.Path(__file__).parent/'MW4-Ultra-Textures'))
sys.path.insert(0,str(PACKAGE))
import storage
from test_addon import ControllerTests


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name).resolve()
        self.mirror=self.root/'mirror';self.shard=self.mirror/'objects/11';self.shard.mkdir(parents=True)
        self.body=b'valid full-size fixture';self.cid=0x8000000000000011
        self.current=self.shard/f'{self.cid:016x}_{len(self.body):08x}_0';self.current.write_bytes(self.body)
        self.old=self.shard/f'{self.cid:016x}_00000005_1';self.old.write_bytes(b'older')
        self.part=self.current.with_name(self.current.name+'.part');self.part.write_bytes(b'partial')
        with sqlite3.connect(self.mirror/'index.sqlite') as c:
            c.execute('create table chunks(id integer primary key,wire integer,flag integer,status integer,etag text)')
            c.execute('insert into chunks values(?,?,?,?,?)',(self.cid-2**64,len(self.body),0,1,hashlib.md5(self.body).hexdigest()))

    def tearDown(self):self.temp.cleanup()

    def clean(self):
        with storage.mirror_lock(self.mirror):return storage.remove_redundant(self.mirror)

    def test_verified_current_copy_keeps_all_detail_sizes_and_removes_only_its_old_variants(self):
        unknown=self.shard/'8000000000000022_00000005_0';unknown.write_bytes(b'other')
        user=self.shard/'notes.txt';user.write_bytes(b'keep')
        bad_shard=self.shard/f'{self.cid+1:016x}_00000005_0';bad_shard.write_bytes(b'keep2')
        result=self.clean()
        self.assertEqual(result['deleted'],2);self.assertEqual(result['logical_bytes_removed'],12)
        self.assertFalse(self.old.exists());self.assertFalse(self.part.exists())
        self.assertEqual(self.current.read_bytes(),self.body)
        self.assertTrue(unknown.exists());self.assertTrue(user.exists());self.assertTrue(bad_shard.exists())
        self.assertEqual(self.clean()['deleted'],0)

    def test_corrupt_or_missing_current_copy_never_causes_deletion(self):
        for body in (b'X'*len(self.body),None):
            if body is None:self.current.unlink()
            else:self.current.write_bytes(body)
            self.assertEqual(self.clean()['deleted'],0)
            self.assertTrue(self.old.exists());self.assertTrue(self.part.exists())

    def test_missing_checksum_or_unverified_row_keeps_old_files(self):
        with sqlite3.connect(self.mirror/'index.sqlite') as c:c.execute('update chunks set etag=null')
        self.assertEqual(self.clean()['deleted'],0)
        with sqlite3.connect(self.mirror/'index.sqlite') as c:c.execute('update chunks set status=0')
        self.assertEqual(self.clean()['deleted'],0)
        self.assertTrue(self.old.exists())

    def test_symlink_current_candidate_and_shard_are_not_followed(self):
        outside=self.root/'outside';outside.write_bytes(self.body)
        self.current.unlink();self.current.symlink_to(outside)
        self.assertEqual(self.clean()['deleted'],0)
        self.current.unlink();self.current.write_bytes(self.body)
        self.old.unlink();self.old.symlink_to(outside)
        self.assertEqual(self.clean()['deleted'],1) # Only the regular .part.
        self.assertTrue(self.old.is_symlink());self.assertEqual(outside.read_bytes(),self.body)
        moved=self.root/'moved';self.shard.rename(moved);self.shard.symlink_to(moved,target_is_directory=True)
        self.assertEqual(self.clean()['deleted'],0)

    def test_changed_candidate_is_preserved_after_checksum_pass(self):
        original=storage.verified
        def verify_then_change(*args):
            result=original(*args);self.old.write_bytes(b'changed while checked');return result
        with patch.object(storage,'verified',side_effect=verify_then_change):result=self.clean()
        self.assertEqual(result['deleted'],1);self.assertEqual(result['skipped'],1)
        self.assertEqual(self.old.read_bytes(),b'changed while checked')

    def test_another_addon_copy_cannot_mutate_or_serve_the_same_storage_concurrently(self):
        code='import storage,sys\nwith storage.mirror_lock(sys.argv[1]): pass'
        env=dict(os.environ,PYTHONPATH=str(PACKAGE),PYTHONDONTWRITEBYTECODE='1')
        with storage.mirror_lock(self.mirror):
            result=subprocess.run([sys.executable,'-c',code,str(self.mirror)],env=env,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertIn('already in use',result.stderr)
        result=subprocess.run([sys.executable,'-c',code,str(self.mirror)],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)


class ControllerCleanupTests(ControllerTests):
    test_ultra_includes_uint32_max_raw_and_start_refuses_incomplete_set = None
    test_controller_disk_check_precedes_network_or_index_creation = None
    test_mirror_cannot_be_placed_inside_the_installed_game = None
    test_verify_uses_the_real_files_and_catalogue_changes_require_refresh = None

    def populate(self):
        self.assertEqual(self.cli('plan').returncode,0)
        self.mirror.mkdir()
        with sqlite3.connect(self.mirror/'index.sqlite') as c:
            c.execute('create table chunks(id integer primary key,wire integer,raw integer,flag integer,prio integer,status integer,etag text,cod_key text,ts real,pkgs integer)')
            c.execute('insert into chunks values(?,?,?,?,?,?,?,?,?,?)',(17,len(self.body),0xffffffff,0,2,1,hashlib.md5(self.body).hexdigest(),'fixture',0,1))
        current=self.mirror/'objects/11'/f'{17:016x}_{len(self.body):08x}_0';current.parent.mkdir(parents=True);current.write_bytes(self.body)
        old=current.with_name(f'{17:016x}_00000003_1');old.write_bytes(b'old')
        partial=current.with_name(current.name+'.part');partial.write_bytes(b'part')
        return current,old,partial

    def test_full_verified_uint32_max_raw_controller_cleanup_preserves_current_and_ready_state(self):
        current,old,partial=self.populate()
        result=self.cli('verify')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(old.exists());self.assertFalse(partial.exists());self.assertEqual(current.read_bytes(),self.body)
        self.assertTrue(json.loads((self.package/'Data/ready.json').read_text())['complete'])

    def test_catalogue_metadata_change_refreshes_before_verification_and_old_copy_is_kept_until_replaced(self):
        current,old,partial=self.populate();newbody=b'new version with different wire size'
        self.catalogue.write_bytes(b'\0'*0x8000+struct.pack('<QIII',17,len(newbody)<<1,0,0xffffffff)+b'\0'*20)
        result=self.cli('verify')
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertTrue(current.exists());self.assertTrue(old.exists());self.assertTrue(partial.exists())
        self.assertFalse(json.loads((self.package/'Data/ready.json').read_text())['complete'])
        with sqlite3.connect(self.mirror/'index.sqlite') as c:
            self.assertEqual(c.execute('select wire,status from chunks').fetchone(),(len(newbody),0))
            c.execute('update chunks set status=1,etag=?',(hashlib.md5(newbody).hexdigest(),))
        new=current.with_name(f'{17:016x}_{len(newbody):08x}_0');new.write_bytes(newbody)
        self.assertEqual(self.cli('verify').returncode,0)
        self.assertEqual(new.read_bytes(),newbody)
        self.assertFalse(current.exists());self.assertFalse(old.exists());self.assertFalse(partial.exists())

    def test_upgrade_from_a_ready_older_release_offers_verification_before_service(self):
        current,old,partial=self.populate()
        self.assertEqual(self.cli('verify').returncode,0)
        ready_path=self.package/'Data/ready.json'
        ready=json.loads(ready_path.read_text());ready.pop('storage_revision');ready_path.write_text(json.dumps(ready))
        old.write_bytes(b'old')
        result=subprocess.run([sys.executable,str(self.package/'addon.py'),'open','--terminal',
            '--game-root',str(self.game),'--mirror',str(self.mirror)],input='Verify Files\nClose\n',
            capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(old.exists());self.assertEqual(current.read_bytes(),self.body)
        self.assertEqual(json.loads(ready_path.read_text())['storage_revision'],1)
        self.assertFalse((self.package/'Data/session.json').exists())


if __name__=='__main__':
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in (StorageTests,ControllerCleanupTests))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
