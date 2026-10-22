"""Offline integration tests: temporary mirrors/hosts, synthetic HTTP; no installed-game writes."""
import hashlib
import http.client
import http.server
import json
import os
import pathlib
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest

PACKAGE = pathlib.Path(os.environ.get('MW4_ADDON_TEST_PACKAGE', pathlib.Path(__file__).parent / "MW4-Ultra-Textures"))
sys.path.insert(0, str(PACKAGE))
import texture_bridge as bridge

TOKEN = "ab" * 24


def object_path(cid, body, flag=0):
    return f"/pc/iw9_3/23/{cid & 255:02x}/{cid:016x}_{len(body):08x}_{flag}"


class HostsTests(unittest.TestCase):
    def test_transaction_exact_roundtrip_both_newlines(self):
        for nl in (b"\n", b"\r\n"):
            original = nl.join((b"# existing host", b"127.0.0.1 localhost", b""))
            with tempfile.TemporaryDirectory() as td:
                p = pathlib.Path(td) / 'hosts'; p.write_bytes(original); p.chmod(0o640)
                self.assertTrue(bridge.change_hosts(p, TOKEN, True, hashlib.sha256(original).hexdigest()))
                self.assertIn(b'::1 cod-assets.cdn.callofduty.com', p.read_bytes())
                self.assertEqual(p.stat().st_mode & 0o777, 0o640)
                self.assertTrue(bridge.change_hosts(p, TOKEN, False))
                self.assertEqual(p.read_bytes(), original)

    def test_restore_keeps_unrelated_later_edits(self):
        old = b"127.0.0.1 localhost\n"
        active = bridge.edit_hosts(old, TOKEN, True) + b"192.0.2.1 unrelated.example\n"
        self.assertEqual(bridge.edit_hosts(active, TOKEN, False), old + b"192.0.2.1 unrelated.example\n")

    def test_existing_mapping_and_changed_block_rejected(self):
        for old in (b"::1 cod-assets.cdn.callofduty.com\n", b"192.0.2.1 cod-assets.cdn.callofduty.com\n"):
            with self.assertRaises(ValueError): bridge.edit_hosts(old, TOKEN, True)
        active = bridge.edit_hosts(b"# old\n", TOKEN, True).replace(b"127.0.0.1 cod-assets", b"127.0.0.2 cod-assets")
        with self.assertRaises(ValueError): bridge.edit_hosts(active, TOKEN, False)
        with self.assertRaises(ValueError): bridge.edit_hosts(b"# missing newline", TOKEN, True)

    def test_stale_preparation_cannot_overwrite_hosts(self):
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / 'hosts'; original = b"# changed\n"; p.write_bytes(original)
            with self.assertRaises(ValueError): bridge.change_hosts(p, TOKEN, True, '0' * 64)
            self.assertEqual(p.read_bytes(), original)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = pathlib.Path(self.temp.name)
        self.body = bytes(range(256)) * 40
        self.path = object_path(0x8000000000000011, self.body)
        obj = self.root / 'objects' / '11' / self.path.rsplit('/', 1)[1]
        obj.parent.mkdir(parents=True); obj.write_bytes(self.body); self.obj = obj
        c = sqlite3.connect(self.root / 'index.sqlite')
        c.execute('create table chunks(id integer,wire integer,flag integer,etag text,cod_key text,status integer,raw integer)')
        c.execute('insert into chunks values(?,?,?,?,?,?,?)', (-2**63 + 0x11,len(self.body),0,hashlib.md5(self.body).hexdigest(),'fixture-metadata',1,64*2**20))
        c.commit(); c.close()
        self.service = bridge.Service(self.root, TOKEN)
        self.servers = bridge.listeners(0, bridge.handler(self.service)); self.port = self.servers[0].server_address[1]
        self.thread = threading.Thread(target=bridge.run_servers, args=(self.servers,self.service)); self.thread.start()

    def tearDown(self):
        self.service.stop.set(); self.thread.join(timeout=5); self.temp.cleanup()

    def req(self, method='GET', path=None, headers=None, host='127.0.0.1'):
        c = http.client.HTTPConnection(host,self.port,timeout=3)
        try:
            c.request(method,path or self.path,headers=headers or {})
            r=c.getresponse(); return r.status,dict(r.getheaders()),r.read()
        finally: c.close()

    def test_full_object_metadata_and_both_address_families(self):
        for host in ('127.0.0.1','::1'):
            status,headers,body=self.req(host=host)
            self.assertEqual((status,body),(200,self.body))
            self.assertEqual(headers['ETag'],'"'+hashlib.md5(self.body).hexdigest()+'"')
            self.assertEqual(headers['x-amz-meta-cod-key'],'fixture-metadata')
        self.assertEqual(self.service.snapshot()['serving_uid'],os.geteuid())
        self.assertEqual(self.service.snapshot()['indexed'],1) # 64 MiB raw item is not quality-filtered.

    def test_head_and_ranges(self):
        status,headers,body=self.req('HEAD');self.assertEqual((status,body),(200,b''));self.assertEqual(int(headers['Content-Length']),len(self.body))
        for value,expected in (('bytes=7-31',self.body[7:32]),('bytes=10200-',self.body[10200:]),('bytes=-20',self.body[-20:])):
            status,headers,body=self.req(headers={'Range':value})
            self.assertEqual((status,body),(206,expected));self.assertIn('Content-Range',headers)
        status,_,body=self.req(headers={'Range':'bytes=7-31','If-Range':'"changed"'})
        self.assertEqual((status,body),(200,self.body))

    def test_invalid_ranges_and_unindexed_paths(self):
        for value in ('bytes=999999-','bytes=3-1','bytes=0-1,3-4','bytes=-0'):
            status,headers,_=self.req(headers={'Range':value});self.assertEqual(status,416);self.assertEqual(headers['Content-Range'],f'bytes */{len(self.body)}')
        for path in ('/arbitrary','/../index.sqlite',self.path.replace('/11/','/12/')):
            self.assertEqual(self.req(path=path)[0],404)

    def test_modified_same_length_object_is_not_served(self):
        self.assertEqual(self.req()[0],200)
        self.obj.write_bytes(b'X'*len(self.body))
        self.assertEqual(self.req()[0],404)
        self.assertEqual(self.service.snapshot()['corrupt'],1)

    def test_stop_requires_private_token(self):
        self.assertEqual(self.req('POST','/__mw4/stop',{'Authorization':'Bearer wrong'})[0],403)
        self.assertFalse(self.service.stop.is_set())
        self.assertEqual(self.req('POST','/__mw4/stop',{'Authorization':'Bearer '+TOKEN})[0],200)
        self.assertTrue(self.service.stop.wait(1))


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name)
        self.game=self.root/'game';(self.game/'sp26').mkdir(parents=True)
        self.mirror=self.root/'mirror';self.work=self.root/'work'
        self.bodies={i: bytes([i])* (8192+i) for i in range(1,6)}
        self.requests={i:0 for i in self.bodies};self.mode='errors';self.delay=0;self.first=threading.Event()
        records=b''.join(struct.pack('<QIII',2**63+i,len(b)<<1,0,64*2**20 if i==5 else len(b)) for i,b in self.bodies.items())
        (self.game/'sp26/sp26_cdn.xpak').write_bytes(b'\0'*0x8000+records+b'\0'*20)
        (self.game/'sp26/boot_cdn.xpak').write_bytes(b'\0'*0x8000+b'\0'*20)
        owner=self
        class CDN(http.server.BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*args):pass
            def do_HEAD(self):self.send_response(200);self.send_header('Content-Length','0');self.end_headers()
            def do_GET(self):
                m=bridge.PATTERN.fullmatch(self.path)
                if not m:self.send_error(404);return
                i=int(m[2],16)-2**63;owner.requests[i]+=1;owner.first.set()
                if owner.delay:time.sleep(owner.delay)
                body=owner.bodies[i]
                if owner.mode=='errors' and i==4:self.send_response(404);self.send_header('Content-Length','0');self.end_headers();return
                self.send_response(200);self.send_header('Content-Length',str(len(body)))
                if owner.mode!='errors' or i!=3:self.send_header('ETag','"'+('0'*32 if owner.mode=='errors' and i==2 else hashlib.md5(body).hexdigest())+'"')
                self.send_header('x-amz-meta-cod-key','fixture-metadata');self.end_headers();self.wfile.write(body)
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),CDN);self.port=self.server.server_address[1]
        self.thread=threading.Thread(target=self.server.serve_forever);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def cmd(self,*args):
        env=dict(os.environ,CCS_GAME_ROOT=str(self.game),CCS_MIRROR_DIR=str(self.mirror),CCS_WORK=str(self.work),PYTHONDONTWRITEBYTECODE='1')
        return [sys.executable,str(PACKAGE/'vendor/ccsmirror.py'),*args],env

    def run_cmd(self,*args):
        cmd,env=self.cmd(*args);r=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=30)
        return r

    def run_download(self,*extra):
        return self.run_cmd('run','--scope','sp','--level','ultra','--upstream-ip','127.0.0.1','--upstream-port',str(self.port),
            '--workers','1','--retries','0','--min-free-gib','0','--accept-notice',*extra)

    def rows(self):
        c=sqlite3.connect(self.mirror/'index.sqlite');r=c.execute('select id,status,etag from chunks order by id').fetchall();c.close();return r

    def test_download_resume_and_checksums_are_real(self):
        p=self.mirror/'objects'/'01'/object_path(2**63+1,self.bodies[1]).rsplit('/',1)[1]
        p.parent.mkdir(parents=True);p.write_bytes(b'X'*len(self.bodies[1]))
        self.assertEqual(self.run_cmd('init','--scope','sp').returncode,0)
        self.assertTrue(all(r[1]==0 for r in self.rows())) # same-sized orphan was not adopted.
        r=self.run_download();self.assertEqual(r.returncode,0,r.stderr)
        states={sid+2**63:status for sid,status,_ in self.rows()}
        self.assertEqual(states,{1:1,2:2,3:2,4:3,5:1})
        self.assertEqual(p.read_bytes(),self.bodies[1])
        self.mode='good'
        r=self.run_download();self.assertEqual(r.returncode,0,r.stderr)
        self.assertTrue(all(status==1 for _,status,_ in self.rows()))
        self.assertEqual(self.requests[1],1) # already-verified pieces were not downloaded again.
        self.assertEqual(self.requests[5],1) # 64 MiB raw class included by Ultra.
        self.assertEqual(self.run_cmd('verify','--all').returncode,0)
        p.write_bytes(b'Y'*len(self.bodies[1]))
        self.assertEqual(self.run_cmd('verify','--all').returncode,1)
        self.assertEqual(self.run_cmd('verify','--all','--fix').returncode,0)
        self.assertEqual(self.rows()[0][1],0)
        self.assertEqual(self.run_download().returncode,0)
        self.assertEqual(self.run_cmd('verify','--all').returncode,0)

    def test_pause_finishes_current_piece_and_resumes(self):
        self.mode='good';self.delay=1.3
        self.assertEqual(self.run_cmd('init','--scope','sp').returncode,0)
        stop=self.root/'PAUSE';progress=self.root/'progress.json'
        cmd,env=self.cmd('run','--scope','sp','--level','ultra','--upstream-ip','127.0.0.1','--upstream-port',str(self.port),
             '--workers','1','--retries','0','--min-free-gib','0','--accept-notice','--stop-file',str(stop),'--progress-json',str(progress))
        p=subprocess.Popen(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            self.assertTrue(self.first.wait(5));stop.touch();out,err=p.communicate(timeout=12)
            self.assertEqual(p.returncode,0,err)
        finally:
            if p.poll() is None:p.terminate();p.wait(timeout=5)
        self.assertEqual(json.loads(progress.read_text())['state'],'paused')
        self.assertGreater(sum(r[1]==0 for r in self.rows()),0)
        self.delay=0
        self.assertEqual(self.run_download().returncode,0)
        self.assertTrue(all(status==1 for _,status,_ in self.rows()))

    def test_disk_reserve_stops_before_any_transfer(self):
        self.mode='good';self.assertEqual(self.run_cmd('init','--scope','sp').returncode,0)
        r=self.run_download('--min-free-gib','1000000')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(sum(self.requests.values()),0)
        self.assertTrue(all(status==0 for _,status,_ in self.rows()))


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name)
        self.package=self.root/'add-on with spaces'
        shutil.copytree(PACKAGE,self.package,ignore=shutil.ignore_patterns('Data','__pycache__'))
        self.game=self.root/'game';(self.game/'sp26').mkdir(parents=True)
        (self.game/'sp26/sp26-cod.exe').write_bytes(b'fixture only')
        self.body=b'largest-raw-class-fixture';self.mirror=self.root/'mirror'
        self.catalogue=self.game/'sp26/sp26_cdn.xpak'
        self.catalogue.write_bytes(b'\0'*0x8000+struct.pack('<QIII',17,len(self.body)<<1,0,0xffffffff)+b'\0'*20)
        (self.game/'sp26/boot_cdn.xpak').write_bytes(b'\0'*0x8000+b'\0'*20)
        self.executable_before=(self.game/'sp26/sp26-cod.exe').read_bytes()

    def tearDown(self):
        self.assertEqual((self.game/'sp26/sp26-cod.exe').read_bytes(),self.executable_before)
        self.temp.cleanup()

    def cli(self,action,*extra):
        return subprocess.run([sys.executable,str(self.package/'addon.py'),action,'--game-root',str(self.game),'--mirror',str(self.mirror),*extra],capture_output=True,text=True,timeout=15)

    def test_ultra_includes_uint32_max_raw_and_start_refuses_incomplete_set(self):
        r=self.cli('plan','--json');self.assertEqual(r.returncode,0,r.stderr)
        plan=json.loads(r.stdout);self.assertEqual(plan['total']['chunks'],1);self.assertEqual(plan['levels']['standard']['chunks'],0)
        r=self.cli('start');self.assertEqual(r.returncode,1);self.assertIn('complete Ultra',r.stderr)

    def test_controller_disk_check_precedes_network_or_index_creation(self):
        self.assertEqual(self.cli('plan').returncode,0)
        p=self.package/'Data/settings.json';cfg=json.loads(p.read_text());cfg['min_free_gib']=1000000;p.write_text(json.dumps(cfg))
        r=self.cli('download');self.assertEqual(r.returncode,2,r.stderr)
        self.assertFalse((self.mirror/'index.sqlite').exists())
        self.assertFalse((self.package/'Data/download-progress.json').exists())

    def test_mirror_cannot_be_placed_inside_the_installed_game(self):
        self.mirror=self.game/'my-mirror'
        r=self.cli('plan');self.assertEqual(r.returncode,1);self.assertIn('outside the game folder',r.stderr)
        self.assertFalse(self.mirror.exists())

    def test_verify_uses_the_real_files_and_catalogue_changes_require_refresh(self):
        self.assertEqual(self.cli('plan').returncode,0)
        self.mirror.mkdir();c=sqlite3.connect(self.mirror/'index.sqlite')
        c.execute('create table chunks(id integer primary key,wire integer,raw integer,flag integer,prio integer,status integer,etag text,cod_key text,ts real,pkgs integer)')
        c.execute('insert into chunks values(?,?,?,?,?,?,?,?,?,?)',(17,len(self.body),0xffffffff,0,2,1,hashlib.md5(self.body).hexdigest(),'fixture',0,1));c.commit();c.close()
        p=self.mirror/'objects/11'/object_path(17,self.body).rsplit('/',1)[1];p.parent.mkdir(parents=True);p.write_bytes(self.body)
        r=self.cli('verify');self.assertEqual(r.returncode,0,r.stderr)
        self.assertTrue(json.loads((self.package/'Data/ready.json').read_text())['complete'])
        self.catalogue.write_bytes(self.catalogue.read_bytes()+b'changed trailer')
        r=self.cli('start');self.assertEqual(r.returncode,1);self.assertIn('catalogue changed',r.stderr)
        p.write_bytes(b'X'*len(self.body))
        r=self.cli('verify');self.assertEqual(r.returncode,2,r.stderr)
        self.assertFalse(json.loads((self.package/'Data/ready.json').read_text())['complete'])


if __name__=='__main__':
    unittest.main(verbosity=2)
