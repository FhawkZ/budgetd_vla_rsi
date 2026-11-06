"""Linux CPU skill child; pure JSON API channel, no simulator objects or candidate perception.
Versioned prototype: not wired into any frozen robot runner.
"""
import ctypes,errno,hashlib,json,os,resource,sys
from pathlib import Path
# Trusted dependencies read before the filesystem-denying filter is installed.
sys.path.insert(0,str(Path(__file__).resolve().parent))
from skill_rsi_caller_bridge import checked
from skill_rsi_owner_accounting import CodeLineBudget

SYSCALLS=('read','write','close','fstat','lseek','brk','mmap','munmap','mremap','mprotect','madvise',
 'futex','clock_gettime','gettimeofday','getrusage','nanosleep','clock_nanosleep','rt_sigaction',
 'rt_sigprocmask','rt_sigreturn','sigaltstack','getpid','gettid','getuid','geteuid','getgid','getegid',
 'getrandom','sched_yield','poll','ppoll','select','pselect6','restart_syscall','exit','exit_group')

def restrict_cpu():
    # libseccomp resolves syscalls for the running architecture; no numeric x86 assumptions.
    lib=ctypes.CDLL('libseccomp.so.2',use_errno=True)
    lib.seccomp_init.argtypes=[ctypes.c_uint32];lib.seccomp_init.restype=ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
    lib.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint];lib.seccomp_rule_add.restype=ctypes.c_int
    lib.seccomp_load.argtypes=[ctypes.c_void_p];lib.seccomp_load.restype=ctypes.c_int
    lib.seccomp_release.argtypes=[ctypes.c_void_p]
    libc=ctypes.CDLL(None,use_errno=True);libc.prctl.argtypes=[ctypes.c_int,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong]
    if libc.prctl(38,1,0,0,0)!=0:raise OSError(ctypes.get_errno(),'no_new_privs')
    ctx=lib.seccomp_init(0x00050000|errno.EPERM)
    if not ctx:raise RuntimeError('seccomp init')
    try:
        for name in SYSCALLS:
            number=lib.seccomp_syscall_resolve_name(name.encode())
            if number<0:raise RuntimeError('unsupported required syscall '+name)
            if lib.seccomp_rule_add(ctx,0x7fff0000,number,0)!=0:raise RuntimeError('seccomp rule '+name)
        if lib.seccomp_load(ctx)!=0:raise RuntimeError('seccomp load')
    finally:lib.seccomp_release(ctx)

def send(obj):
    text=json.dumps(obj,allow_nan=False,separators=(',',':'))
    if len(text.encode())>65536:raise ValueError('outgoing message cap')
    sys.stdout.write(text+'\n');sys.stdout.flush()

class RemoteAPI:
    def _rpc(self,method,args):
        send({'type':'api','method':method,'args':args})
        text=sys.stdin.readline(65537)
        if not text.endswith('\n') or len(text.encode())>65536:raise ValueError('response framing')
        row=json.loads(text)
        if set(row)!={'ok','value'} or row['ok'] is not True:raise RuntimeError('API boundary refused')
        return row['value']
    def task_spec(self):return self._rpc('task_spec',{})
    def observe(self):return self._rpc('observe',{})
    def ee_pose(self,arm):return self._rpc('ee_pose',{'arm':arm})
    def gripper_state(self,arm):return self._rpc('gripper_state',{'arm':arm})
    def move_pose(self,arm,pose):return self._rpc('move_pose',{'arm':arm,'pose':pose})
    def gripper(self,arm,value):return self._rpc('gripper',{'arm':arm,'value':value})
    def wait(self,seconds):return self._rpc('wait',{'seconds':seconds})

def main():
    row=json.loads(sys.stdin.readline(100001));source=row['source']
    limit=row['code_lines'];cpu=row['cpu_seconds']
    if type(limit) is not int or not 1<=limit<=30000 or type(cpu) is not int or not 1<=cpu<=240:raise ValueError('execution budget')
    lines=CodeLineBudget(limit)
    if len(source.encode())>60000:raise ValueError('source cap')
    ns={};validator=checked(Path(sys.argv[1]),'validate.py');exec(compile(validator,'<pinned-validator>','exec'),ns)
    errors,atoms=ns['validate_skills'](source)
    if errors:send({'type':'rejected','errors':errors});return
    if row['entry'] not in atoms+['fallback']:raise ValueError('undeclared entry')
    # Limits apply only to this fresh child. No GPU/device or other project process touched.
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(256*2**20,256*2**20))
    resource.setrlimit(resource.RLIMIT_CPU,(cpu,cpu+1));resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
    restrict_cpu()
    send({'type':'ready','source_sha256':hashlib.sha256(source.encode()).hexdigest(),'seccomp_allowlist':True})
    scope,atoms=ns['load_skills'](source)
    api=RemoteAPI();entry=scope[row['entry']]
    result=lines.run(entry,api) if row['entry']=='fallback' else lines.run(entry,api,row['args'])
    if lines.n>limit:raise RuntimeError('line budget swallowed')
    if not isinstance(result,dict) or 'status' not in result or 'failure_code' not in result:raise ValueError('native fallback result contract')
    send({'type':'result','value':result,'code_lines':lines.n})
if __name__=='__main__':
    try:main()
    except BaseException as error:
        try:send({'type':'error','error_class':type(error).__name__})
        except BaseException:pass
        sys.exit(1)
