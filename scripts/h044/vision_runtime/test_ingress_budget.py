"""Source-only ingress request/lease regressions; no sockets or model calls."""
import io
import datetime
from pathlib import Path
import threading
import time
import unittest
from email.message import Message
from unittest import mock
import ingress
import normal_service

class IngressBudgetTests(unittest.TestCase):
 def setUp(self):
  self.now=100.
  self.clock=mock.patch.object(ingress.time,'monotonic',side_effect=lambda:self.now);self.clock.start();self.addCleanup(self.clock.stop)
  self.graph={'runtime':{'ingress':{'healthClientIp':'10.156.100.60'}}}
  self.proof={'identityOrigin':'REVIEWED_SIGNED_ROOT_PROOF','component':'ingress','actualUid':1000,'graph':self.graph}
 def server(self,lease=None):
  with mock.patch.object(ingress.HTTPServer,'__init__',return_value=None):
   return ingress.Server('source-only-key-0000','10.156.100.61','PASS_ROOT_REVIEWED_AUTHENTICATED_PRIVATE_LINK',600,proof=self.proof,normal_lease=lease)
 def lease(self):
  lease=normal_service.ActiveLease(self.graph,'ingress',600,clock=lambda:self.now)
  # This test substitutes only the authenticated lease deadline result. Actual
  # signature/graph/birth/handshake failures are covered by normal handoff tests.
  lease.deadline=mock.Mock(return_value=600)
  lease.adopted=True;lease.lastState={'state':'NORMAL'}
  return lease
 def request(self,s,*,auth='Bearer source-only-key-0000',host='10.156.100.60:18193',ip='10.156.100.61',path='/v1/technical-vision/jobs/job1/status',method='POST',extras=()):
  h=ingress.Handler.__new__(ingress.Handler);h.server=s;h.client_address=(ip,123);h.command=method;h.path=path
  h.headers=Message();h.headers['Authorization']=auth;h.headers['Host']=host;h.headers['Content-Length']='0'
  for k,v in extras:h.headers[k]=v
  h.rfile=io.BytesIO();h.wfile=io.BytesIO();h.send_error=mock.Mock();h.send_response=mock.Mock();h.send_header=mock.Mock();h.end_headers=mock.Mock()
  connection=mock.Mock();response=connection.getresponse.return_value;response.status=200;response.read.return_value=b'{}';response.getheader.return_value='application/json'
  with mock.patch.object(ingress.http.client,'HTTPConnection',return_value=connection):h.forward()
  return h.send_error.call_args.args[0] if h.send_error.called else h.send_response.call_args.args[0]
 def test_finite_exactly_64_even_with_elapsed_time(self):
  s=self.server()
  for _ in range(64):self.assertEqual(self.request(s),200);self.now+=.25
  self.now+=100;self.assertEqual(self.request(s),503);self.assertEqual(s.request_count,64)
 def test_normal_4hz_plus_health_beyond_64(self):
  lease=self.lease();s=self.server(lease)
  for i in range(200):
   self.assertEqual(self.request(s),200)
   if i%4==0:self.assertEqual(self.request(s,path='/v1/technical-vision/capabilities',method='GET'),200)
   self.now+=.25
  self.assertEqual(s.request_count,250);self.assertEqual(lease.deadline.call_count,250)
 def test_burst_replenishes_but_caps_at_16(self):
  s=self.server(self.lease())
  for _ in range(16):self.assertTrue(s.admit_request())
  self.assertFalse(s.admit_request());self.now+=.125;self.assertTrue(s.admit_request());self.assertFalse(s.admit_request())
  self.now+=50
  self.assertEqual(sum(s.admit_request() for _ in range(40)),16)
 def test_adoption_after_finite_exhaustion(self):
  lease=self.lease();lease.adopted=False;lease.lastState={'state':'PREPARED'};s=self.server(lease)
  self.assertEqual(sum(s.admit_request() for _ in range(65)),64)
  lease.adopted=True;lease.lastState={'state':'NORMAL'}
  self.assertEqual(sum(s.admit_request() for _ in range(17)),16)
 def test_expired_revoked_and_invalid_lease_fail_closed(self):
  for end in (0,100):
   lease=self.lease();lease.deadline.return_value=end;s=self.server(lease)
   self.assertEqual(self.request(s),503);self.assertEqual(s.request_count,0)
  s=self.server(self.lease());self.now=600;self.assertFalse(s.admit_request())
 def test_no_normal_mode_for_uncommitted_phase(self):
  lease=self.lease();lease.lastState={'state':'ACK_PENDING_RELINQUISH'};s=self.server(lease)
  self.assertEqual(sum(s.admit_request() for _ in range(70)),64)
 def test_exact_lease_type_role_and_graph(self):
  for lease in (object(),normal_service.ActiveLease(self.graph,'service',600),normal_service.ActiveLease({},'ingress',600)):
   with self.assertRaises(ingress.control.Refused):self.server(lease)
 def test_auth_route_and_body_guards_unchanged(self):
  cases=[({'auth':'wrong'},401),({'host':'localhost:18193'},401),({'ip':'127.0.0.1'},401),({'extras':[('Authorization','again')]},401),({'path':'/v1/models'},404),({'method':'GET'},404),({'path':'/v1/technical-vision/jobs/../status'},404),({'extras':[('Transfer-Encoding','chunked')]},400),({'extras':[('Content-Length','1')]},400)]
  for options,code in cases:
   with self.subTest(options=options):self.assertEqual(self.request(self.server(self.lease()),**options),code)
 def test_real_active_lease_validation_and_revocation(self):
  # Only public metadata reads, signature cryptography and boot identity are
  # synthetic; the complete ActiveLease/component_capability path executes.
  c=ingress.control
  self.graph['runtime']['normalHandoff']={'status':normal_service.STATUS,'statePath':'state','capabilityPath':'cap','signaturePath':'sig'}
  iso=lambda t:datetime.datetime.fromtimestamp(t,datetime.timezone.utc).isoformat()
  cap={'schema':'h044-normal-adoption-v1','issuer':'ROOT_AUTHENTIC_SIGNER','sourceGraphSHA256':c.sha(c.canonical(self.graph)),'bootId':'fixture-boot','notBefore':iso(99),'normalLeaseExpires':iso(500),'resources':[{'role':'ingress','birth':{'pid':42}}],'newOwner':{'nonce':'fixture'}}
  state={'state':'NORMAL','bootId':'fixture-boot','resources':cap['resources'],'capabilitySHA256':c.sha(c.canonical(cap)),'owner':cap['newOwner'],'newOwnerAck':True,'oldOwnerRelinquish':True}
  data={'state':c.canonical(state),'cap':c.canonical(cap),'sig':b'fixture-valid'}
  lease=normal_service.ActiveLease(self.graph,'ingress',110,read=lambda p:data[p],clock=lambda:self.now,verify=lambda raw,sig:sig==b'fixture-valid',birth=lambda:{'pid':42})
  s=self.server(lease)
  with mock.patch.object(Path,'read_text',return_value='fixture-boot'):
   for i in range(100):self.assertEqual(self.request(s),200);self.now+=.25
   self.assertTrue(lease.adopted)
   data['sig']=b'fixture-invalid'
   self.assertEqual(self.request(s),503)
   self.assertIn('signature',lease.failure)
 def test_connection_capacity_stays_eight(self):
  s=self.server(self.lease());self.assertEqual(sum(s.slots.acquire(False) for _ in range(9)),8)

if __name__=='__main__':unittest.main()
