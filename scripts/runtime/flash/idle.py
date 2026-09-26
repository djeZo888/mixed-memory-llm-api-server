"""H008 exact KT scheduler, TP1/non-overlap only; no Qwen overlay reuse."""
import time

class FlashIdle:
    def __init__(self, scheduler, *, clock=time.monotonic, poller=None):
        import zmq
        self.scheduler, self.clock = scheduler, clock
        self.last_work = clock()
        self.poller = poller or zmq.Poller()
        if poller is None:
            for sock in (scheduler.recv_from_tokenizer, scheduler.recv_from_rpc):
                if sock is None:
                    raise RuntimeError('flash_idle_missing_ingress')
                self.poller.register(sock, zmq.POLLIN)

    def work(self):
        self.last_work = self.clock()

    def wait(self):
        s = self.scheduler
        # Native self_check has already checked chunk/running/waiting queues.
        # Grammar completion is asynchronous and has no ingress notification.
        if (s.chunked_req is not None or not s.running_batch.is_empty()
                or s.waiting_queue or len(s.grammar_manager)
                or getattr(s, 'result_queue', None)):
            self.work()
            self.poller.poll(1)
            return
        # Warm resident grace uses a bounded event wait, never a busy-spin.
        # Both native sockets are level-triggered: a request arriving between
        # predicate and poll is retained and wakes the persistent model.
        self.poller.poll(1 if self.clock() - self.last_work < 600 else None)


def install(scheduler_module):
    cls = scheduler_module.Scheduler
    original_init, original_run = cls.__init__, cls.run_batch
    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        expected = {'tp_size':1, 'pp_size':1, 'dp_size':1,
                    'disable_overlap_schedule':True, 'disaggregation_mode':'null'}
        if any(getattr(self.server_args, k, None) != v for k,v in expected.items()):
            raise RuntimeError('flash_idle_unsupported_mode')
        if (self.input_blocker is not None or self.recv_skipper is not None
                or self.enable_hisparse or self.enable_hierarchical_cache):
            raise RuntimeError('flash_idle_uncovered_producer')
        import json
        import torch
        native={'context':self.model_config.context_len,'pool':self.max_total_num_tokens,
                'max_req_len':self.max_req_len,'max_req_input_len':self.max_req_input_len}
        if native != {'context':480000,'pool':480000,'max_req_len':479999,'max_req_input_len':479994}:
            raise RuntimeError('flash_native_allocation_mismatch')
        if torch.cuda.get_device_capability() != (12,0):
            raise RuntimeError('flash_sm120_device_required')
        x=torch.ones((128,128),device='cuda'); y=x@x; torch.cuda.synchronize()
        if y[0,0].item()!=128: raise RuntimeError('flash_sm120_execution_failed')
        print('FLASH_NATIVE_ALLOCATION '+json.dumps({**native,
            'resolved_cache_dtype':str(self.tp_worker.model_runner.kv_cache_dtype),
            'sm120_execution':'PASS'}),flush=True)
        self._flash_idle = FlashIdle(self)
    def run(self, *args, **kwargs):
        self._flash_idle.work()
        result = original_run(self, *args, **kwargs)
        self._flash_idle.work()
        return result
    cls.__init__, cls.run_batch = init, run
    cls.maybe_sleep_on_idle = lambda self: self._flash_idle.wait()
