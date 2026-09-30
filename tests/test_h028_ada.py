"""Exact Ada tuple checks are offline and never import serving code."""
import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
ada=load('ada_test_launcher',ROOT/'scripts/h028/ada_launcher.py')
base=load('ada_test_base',ROOT/'scripts/runtime/sglang38_file_auth.py')
class AdaTuple(unittest.TestCase):
    def test_exact_tuple(self):
        argv=ada.backend_argv(base,'ada200k')
        flags=dict(zip(argv[:-2:2],argv[1:-2:2]))
        self.assertEqual(flags['--context-length'],'200000')
        self.assertEqual(flags['--max-total-tokens'],'200000')
        self.assertEqual(flags['--port'],'30014')
        self.assertEqual(flags['--fp8-gemm-backend'],'triton')
        self.assertEqual(flags['--mem-fraction-static'],'0.90')
        self.assertEqual(flags['--kv-cache-dtype'],'bfloat16')
        self.assertEqual(flags['--quantization'],'fp8')
        self.assertEqual(flags['--max-running-requests'],'1')
    def test_old_slot_cannot_enter(self):
        for slot in ['gpu0','gpu1','auto','',None]:
            with self.assertRaises(base.LaunchError):ada.backend_argv(base,slot)
    def test_physical_budget(self):
        kv=16*2*4*256*2
        self.assertEqual(kv,65536)
        total=49140*2**20;gap=628*2**20;reserve=total*.07
        anchor=50400854016;fixed=anchor-262144*kv
        self.assertGreater(total-gap-(fixed+200000*kv),reserve)
        self.assertLess(total-gap-(fixed+250000*kv),reserve)
if __name__=='__main__':unittest.main()

class QualificationIdentity(unittest.TestCase):
    def test_current_start_only(self):
        import sys
        sys.path.insert(0,str(ROOT/'scripts/h028'))
        import ada_supervisor as supervisor
        q={'status':'PASS','container_id':'id','context_tokens':200000,'boot_id':'boot','docker_started_at':'start'}
        self.assertTrue(supervisor.qualification_matches(q,'id','boot','start'))
        self.assertFalse(supervisor.qualification_matches(q,'id','boot','restart'))
        self.assertFalse(supervisor.qualification_matches(q,'id','reboot','start'))
        self.assertFalse(supervisor.qualification_matches(q,'new','boot','start'))
    def test_profile_qualification_survives_boot_but_not_tuple_drift(self):
        import sys
        sys.path.insert(0,str(ROOT/'scripts/h028'))
        import ada_supervisor as supervisor
        c={'source_sha256':{'ada_launcher.py':'abc'},'model_metadata_sha256':{'config.json':'def'}}
        c['profile_qualification']={'status':'PASS','profile':supervisor.immutable_profile(c)}
        self.assertTrue(supervisor.profile_qualified(c))
        c['source_sha256']['ada_launcher.py']='changed'
        self.assertFalse(supervisor.profile_qualified(c))


class RestartPort(unittest.TestCase):
    def test_active_listener_refused(self):
        import socket
        owner=load('ada_port_owner',ROOT/'scripts/h028/ada_owner.py')
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            listener.bind(('127.0.0.1',0));listener.listen()
            with self.assertRaises(OSError):owner.require_port_available(listener.getsockname()[1])

    def test_recently_closed_connection_allows_rebind(self):
        import socket
        owner=load('ada_port_owner',ROOT/'scripts/h028/ada_owner.py')
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            listener.bind(('127.0.0.1',0));listener.listen()
            port=listener.getsockname()[1]
            with socket.create_connection(('127.0.0.1',port)) as client:
                server,_=listener.accept()
                server.close()
                self.assertEqual(client.recv(1),b'')
        owner.require_port_available(port)
