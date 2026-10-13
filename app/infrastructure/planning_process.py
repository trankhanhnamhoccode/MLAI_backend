"""Local OS process incarnation checks. No timeout, heartbeat or worker daemon."""
import os
from pathlib import Path
import socket
import sys
from app.application.contracts.planning_run import ProcessIdentity


def _birth(pid: int):
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD,wintypes.BOOL,wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = (wintypes.HANDLE,*(ctypes.POINTER(wintypes.FILETIME),)*4)
        kernel.GetProcessTimes.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE,wintypes.DWORD)
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        handle = kernel.OpenProcess(0x1000 | 0x100000,False,pid)
        if not handle:
            return ('DEAD',None) if ctypes.get_last_error()==87 else ('UNKNOWN',None)
        try:
            signal = kernel.WaitForSingleObject(handle,0)
            if signal==0:
                return 'DEAD',None  # Exited process can still have an open OS handle.
            if signal!=258:
                return 'UNKNOWN',None
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle,*(ctypes.byref(t) for t in times)):
                return 'UNKNOWN',None
            return 'ALIVE',str((times[0].dwHighDateTime<<32)|times[0].dwLowDateTime)
        finally:
            kernel.CloseHandle(handle)
    if not sys.platform.startswith('linux') or not Path('/proc/self/stat').exists():
        return 'UNKNOWN',None
    try:
        stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        if stat[0] == 'Z':
            return 'DEAD',None
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        return 'ALIVE',boot+':'+stat[19]
    except FileNotFoundError:
        return 'DEAD',None
    except (OSError,IndexError):
        return 'UNKNOWN',None


def current_process() -> ProcessIdentity:
    state,birth = _birth(os.getpid())
    if state!='ALIVE' or not birth:
        raise RuntimeError('Cannot establish local process incarnation')
    return ProcessIdentity(host=socket.gethostname(),pid=os.getpid(),birth=birth)


def liveness(identity: ProcessIdentity) -> str:
    identity = ProcessIdentity.model_validate(identity)
    if identity.host != socket.gethostname():
        return 'UNKNOWN'
    state,birth = _birth(identity.pid)
    if state=='ALIVE' and birth!=identity.birth:
        return 'DEAD'  # PID reused; the original process has exited.
    return state
