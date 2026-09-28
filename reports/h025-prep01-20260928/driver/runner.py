"""Finite threaded H025 phase runner. Adapter is fixed NativeAdapter or offline fake."""
import contextlib
import json
import threading
import time
import uuid
from contract import TEXT, Refusal, image_body, text_body
from primitives import capture_text, capture_image

class Runner:
    def __init__(self, phase, adapter, sleep=time.sleep):
        self.p, self.a, self.sleep = phase, adapter, sleep
        self.finished = threading.Event()
        self.stop_attempted = set()
        self.stop_threads=[]

    def once(self, lane, content):
        prefix = uuid.uuid4().hex+' '+uuid.uuid4().hex
        body = text_body(self.p.m,lane,prefix,content) if lane in TEXT else image_body(self.p.m,prefix)
        proof = self.a.preflight(lane)
        with self.a.intent() if hasattr(self.a,'intent') else contextlib.nullcontext():
            row, raw = self.p.prepare(lane,body,prefix,proof)
        connection = None
        capture = None
        try:
            if lane in TEXT:
                counted = self.a.count(lane,raw,row)
                self.p.counted(lane,counted)
            # Adapter must open at most one connection and never retry request().
            connection = self.a.connect(lane)
            self.p.begin_send(lane,raw,self.a.preflight(lane))
            # A closed gate between intent and send keeps possible submission owned.
            with self.p.lock:
                self.p.monitoring_tick()
                if self.p.admission_closed:
                    raise Refusal('admission closed before exact send')
                connection.send(raw,row['request_id'])
                capture = self.p.body_sent(lane)
            response = connection.response()
            if lane in TEXT:
                capture_text(response,capture,self.p.active[lane]['input_tokens'],body['max_tokens'],self.p.clock)
            else:
                capture_image(response,capture,self.p.clock)
            self.p.http_finished(lane,capture)
            # Existing owner may need to publish final release after HTTP EOF.
            while self.p.clock()['monotonic'] < self.p.settlement_deadline:
                settled = self.a.settlement(lane,capture)
                if settled is not None:
                    self.p.settled(lane,settled)
                    return True
                self.sleep(.2)
            raise Refusal('native settlement deadline')
        except Exception as exc:
            if lane in self.p.active:self.p.ambiguous(lane,type(exc).__name__+': request or native proof failed',capture)
            return False
        finally:
            if connection is not None:
                connection.close()  # never presented as cancellation/settlement

    def lane(self,lane):
        # Files are bounded, reviewed prompt corpora, not token estimates. Each body
        # is independently native-counted after its fresh varied prefix is added.
        try:
            content=self.a.corpus(lane) if lane in TEXT else ''
            while True:
                with self.p.lock:
                    try:self.p.admission(lane)
                    except Refusal:
                        if self.p.first_failure is None and not self.p.admission_closed and self.p.clock()['monotonic'] < self.p.admission_deadline:
                            self.p.fail('finite_lane_cap_before_campaign_end',lane)
                        return
                if not self.once(lane,content):return
        except Exception as exc:
            self.p.fail('lane_preparation_failed:'+type(exc).__name__,lane)

    def stop_lane(self,lane,intent):
        try:
            proof=self.a.stop_exact(lane,intent)
            if proof is not None:self.p.physical_stopped(lane,proof)
        except Exception as exc:
            self.p.fail('exact_stop_unproven:'+type(exc).__name__,lane)

    def dispatch_stops(self):
        with self.p.lock:
            for lane,intent in list(self.p.stop_intents.items()):
                if lane not in self.stop_attempted:
                    self.stop_attempted.add(lane)
                    thread=threading.Thread(target=self.stop_lane,args=(lane,dict(intent)),daemon=True)
                    self.stop_threads.append(thread);thread.start()

    def monitor(self):
        due=self.p.clock()['monotonic']
        while not self.finished.is_set():
            try:
                self.p.observe(self.a.sample(due))
                self.p.monitoring_tick()
            except Exception as exc:
                self.p.fail('monitor_or_owner_read_failed:'+type(exc).__name__)
            finally:
                # Persistence/sample failure cannot skip exact owned settlement.
                self.dispatch_stops()
            if self.p.clock()['monotonic'] >= self.p.settlement_deadline:return
            due=self.p.clock()['monotonic']+1
            self.finished.wait(1)

    def run(self):
        monitor=None;lanes=[]
        try:
            self.p.observe(self.a.sample(self.p.clock()['monotonic']))
            self.p.release_barrier({l:self.a.preflight(l) for l in self.p.lanes})
            monitor=threading.Thread(target=self.monitor,daemon=True);monitor.start()
            lanes=[threading.Thread(target=self.lane,args=(l,),daemon=True) for l in self.p.lanes]
            for thread in lanes:thread.start()
            for thread in lanes:
                thread.join(max(0,self.p.settlement_deadline-self.p.clock()['monotonic']-60))
            while self.p.active and self.p.clock()['monotonic'] < self.p.settlement_deadline-60:
                for lane,row in list(self.p.active.items()):
                    try:
                        proof=self.a.settlement(lane,row)
                        if proof is not None and lane in self.p.active:self.p.settled(lane,proof)
                    except Exception as exc:
                        self.p.fail('native_settlement_read_failed:'+type(exc).__name__,lane)
                self.sleep(.2)
            self.p.monitoring_tick()
        except Exception as exc:
            self.p.fail('runner_boundary_failed:'+type(exc).__name__)
        finally:
            self.p.admission_closed=True
            if self.p.active:self.p.fail('runner_exit_with_accepted_work')
            self.dispatch_stops()
            # Keep monitoring alive during exact owner physical settlement. The
            # configured full request budget already reserves60s for this path.
            for thread in self.stop_threads:
                thread.join(max(0,self.p.settlement_deadline-self.p.clock()['monotonic']))
            self.finished.set()
            if monitor:monitor.join(10)
            if any(t.is_alive() for t in self.stop_threads):self.p.fail('stop_thread_unproven_still_owned')
        report=self.p.report()
        report['stop_threads_settled']=not any(t.is_alive() for t in self.stop_threads)
        try:self.p.journal.write('FINAL',report)
        except Exception as exc:
            self.p.persistence_error('FINAL',exc)
            report=self.p.report();report['final_persistence_failed']=True
        return report
