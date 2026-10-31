import sys,threading,types
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from owner_thread_adapter import OwnerInlineExecutor,construct_on_owner,adapt_facade

def test_future_identity_exception_and_no_retry():
    e=OwnerInlineExecutor(1);sentinel=object();err=ValueError('native');calls=[]
    assert e.submit(lambda:sentinel).result() is sentinel
    def fail():calls.append(1);raise err
    with pytest.raises(ValueError) as caught:e.submit(fail).result()
    assert caught.value is err and calls==[1]
    with ThreadPoolExecutor(1) as pool:
        with pytest.raises(RuntimeError):pool.submit(e.submit,lambda:sentinel).result()
    e.shutdown()
    with pytest.raises(RuntimeError):e.submit(lambda:sentinel)
    with pytest.raises(ValueError):OwnerInlineExecutor(2)

def test_scoped_factory_restores_on_error():
    module=types.SimpleNamespace(ThreadPoolExecutor=ThreadPoolExecutor)
    def factory():
        assert module.ThreadPoolExecutor is OwnerInlineExecutor
        raise ValueError('construction')
    with pytest.raises(ValueError):construct_on_owner(factory,module)
    assert module.ThreadPoolExecutor is ThreadPoolExecutor

def test_actual_upstream_mixin_routes_and_tears_down_on_owner():
    from rpent.utils.rpc.main_thread_serve import MainThreadServeMixin
    from rpent.utils.rpc.rpc_facade import RpcFacade
    owner=threading.get_ident();seen=[];ready=threading.Event();proxy={}
    class Base(RpcFacade):
        def __init__(self):
            super().__init__();self._rpc={'echo':self.echo,'fail':self.fail}
        def echo(self,value):seen.append(threading.get_ident());return value
        def fail(self):raise ValueError('native failure')
        def _dispatch(self,method,args,kwargs):return super()._dispatch(method,args,kwargs)
        def _bind_and_announce(self,transport,host,port,dispatch):
            proxy['call']=dispatch;ready.set()
            return types.SimpleNamespace(serve_forever=lambda:None,shutdown=lambda:None,server_close=lambda:None)
        def close(self):seen.append(threading.get_ident())
    facade=adapt_facade(Base,MainThreadServeMixin)();errors=[]
    def remote():
        try:
            assert ready.wait(3)
            value=object();assert proxy['call']('echo',(value,),{}) is value
            with pytest.raises(RuntimeError,match='native failure'):proxy['call']('fail',(),{})
            assert proxy['call']('echo',(5,),{})==5
        except BaseException as exc:errors.append(exc)
        finally:proxy['call']('shutdown',(),{})
    thread=threading.Thread(target=remote,daemon=True);thread.start()
    facade.serve(transport='http',host='127.0.0.1',port=0)
    thread.join(3);assert not thread.is_alive() and not errors
    assert seen==[owner,owner,owner]
