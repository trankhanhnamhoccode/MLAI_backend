"""Owned suspended launch and kill-on-close Windows job for profiling only."""
import ctypes
from ctypes import wintypes as W
import subprocess
from time import monotonic, sleep


class BasicLimits(ctypes.Structure):
    _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),
        ('flags',W.DWORD),('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),
        ('active_limit',W.DWORD),('affinity',ctypes.c_size_t),('priority',W.DWORD),('scheduling',W.DWORD)]


class IO(ctypes.Structure):
    _fields_=[(n,ctypes.c_ulonglong) for n in ('reads','writes','others','read_bytes','write_bytes','other_bytes')]


class ExtendedLimits(ctypes.Structure):
    _fields_=[('basic',BasicLimits),('io',IO),('process_memory',ctypes.c_size_t),
        ('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]


class Accounting(ctypes.Structure):
    _fields_=[('user',ctypes.c_longlong),('kernel',ctypes.c_longlong),
        ('period_user',ctypes.c_longlong),('period_kernel',ctypes.c_longlong),
        ('faults',W.DWORD),('total',W.DWORD),('active',W.DWORD),('terminated',W.DWORD)]


class OwnedJob:
    def __init__(self):
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        declarations={
            'CreateJobObjectW':([ctypes.c_void_p,W.LPCWSTR],W.HANDLE),
            'SetInformationJobObject':([W.HANDLE,ctypes.c_int,ctypes.c_void_p,W.DWORD],W.BOOL),
            'AssignProcessToJobObject':([W.HANDLE,W.HANDLE],W.BOOL),
            'TerminateJobObject':([W.HANDLE,W.UINT],W.BOOL),
            'QueryInformationJobObject':([W.HANDLE,ctypes.c_int,ctypes.c_void_p,W.DWORD,ctypes.c_void_p],W.BOOL),
            'CloseHandle':([W.HANDLE],W.BOOL)}
        for name,(args,result) in declarations.items():
            fn=getattr(self.kernel,name);fn.argtypes=args;fn.restype=result
        self.handle=self.kernel.CreateJobObjectW(None,None)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        limits=ExtendedLimits();limits.basic.flags=0x2000  # KILL_ON_JOB_CLOSE, no breakaway.
        self.check(self.kernel.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits)))

    def check(self,result):
        if not result:raise ctypes.WinError(ctypes.get_last_error())

    def launch(self,command,cwd):
        process=subprocess.Popen(command,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            creationflags=0x4)  # CREATE_SUSPENDED: no descendant before job assignment.
        try:
            self.check(self.kernel.AssignProcessToJobObject(self.handle,W.HANDLE(int(process._handle))))
            resume=ctypes.WinDLL('ntdll').NtResumeProcess
            resume.argtypes=[W.HANDLE];resume.restype=ctypes.c_long
            if resume(W.HANDLE(int(process._handle)))!=0:raise RuntimeError('RESUME_OWNED_PROCESS_FAILED')
        except BaseException:
            process.kill();process.communicate();raise
        return process

    def active(self):
        info=Accounting()
        self.check(self.kernel.QueryInformationJobObject(self.handle,1,ctypes.byref(info),ctypes.sizeof(info),None))
        return info.active

    def terminate(self):
        self.check(self.kernel.TerminateJobObject(self.handle,1))
        deadline=monotonic()+5
        while self.active() and monotonic()<deadline:sleep(.01)
        if self.active():raise RuntimeError('OWNED_JOB_STILL_ACTIVE')

    def close(self):
        if self.handle:
            self.check(self.kernel.CloseHandle(self.handle));self.handle=None
