"""App lifetimes share a lock; offline maintenance needs exclusive ownership."""
import os
from pathlib import Path


class DataDirectoryBusy(RuntimeError):
    pass


class DataDirectoryLock:
    def __init__(self, directory: Path, *, exclusive=False):
        self.directory, self.exclusive = Path(directory), exclusive
        self.file = None

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / '.workspace.lock'
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise DataDirectoryBusy('The data lock must be a regular local file.')
        # Append-mode opening can touch a locked byte on Windows. Open without
        # reading/writing the lock region, and let the OS lock own the handle.
        self.file = os.fdopen(os.open(path, os.O_RDWR | os.O_CREAT, 0o600), 'r+b')
        try:
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes
                import msvcrt

                class Overlapped(ctypes.Structure):
                    _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                        ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD), ('hEvent', wintypes.HANDLE)]

                lock = ctypes.WinDLL('kernel32', use_last_error=True).LockFileEx
                lock.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                    wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped)]
                lock.restype = wintypes.BOOL
                self.overlapped = Overlapped()
                if not lock(msvcrt.get_osfhandle(self.file.fileno()), 1 | (2 if self.exclusive else 0), 0, 1, 0, ctypes.byref(self.overlapped)):
                    raise OSError(ctypes.get_last_error(), 'Data directory locked')
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), (fcntl.LOCK_EX if self.exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            self.file = None
            raise DataDirectoryBusy('Stop all backend processes and other maintenance commands for this data directory, then retry.') from None
        return self

    def __exit__(self, *args):
        # Closing the owning handle releases the OS lock, also after a crash.
        if self.file:
            self.file.close()
            self.file = None
