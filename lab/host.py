import ctypes
import os
import signal
import subprocess
import sys
import time

WINDOWS = sys.platform == "win32"


def parse_proc_stat(text):
    fields = [int(value) for value in text.splitlines()[0].split()[1:]]
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
    return sum(fields) - idle, sum(fields)


def percent(before, after):
    total = after[1] - before[1]
    return 0.0 if total <= 0 else 100.0 * (after[0] - before[0]) / total


def cpu_sample():
    if WINDOWS:
        idle, kernel, user = ctypes.c_ulonglong(), ctypes.c_ulonglong(), ctypes.c_ulonglong()
        ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
        total = kernel.value + user.value
        return total - idle.value, total
    with open("/proc/stat") as handle:
        return parse_proc_stat(handle.read())


def cpu_load(interval=1.0):
    before = cpu_sample()
    time.sleep(interval)
    return percent(before, cpu_sample())


def parse_nvidia(text):
    values = [line.strip() for line in text.splitlines() if line.strip()]
    return max(int(value) for value in values) if values else None


def _nvidia(query):
    try:
        return subprocess.run(["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
                              capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def gpu_load():
    try:
        return parse_nvidia(_nvidia("utilization.gpu"))
    except ValueError:
        return None


def gpu_name():
    return _nvidia("name,driver_version").strip()


class _LastInput(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


class _Rect(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("rcMonitor", _Rect), ("rcWork", _Rect), ("dwFlags", ctypes.c_uint)]


class _ProcessEntry(ctypes.Structure):
    _fields_ = [("dwSize", ctypes.c_uint), ("cntUsage", ctypes.c_uint), ("th32ProcessID", ctypes.c_uint),
                ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", ctypes.c_uint),
                ("cntThreads", ctypes.c_uint), ("th32ParentProcessID", ctypes.c_uint),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", ctypes.c_uint), ("szExeFile", ctypes.c_wchar * 260)]


SHELL_WINDOWS = {"Progman", "WorkerW", "Shell_TrayWnd"}


def seconds_since_input():
    info = _LastInput(ctypes.sizeof(_LastInput), 0)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
    return ((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0


def fullscreen_app():
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Rect)]
    user32.MonitorFromWindow.restype = ctypes.c_void_p
    user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MonitorInfo)]
    window = user32.GetForegroundWindow()
    if not window:
        return False
    name = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(window, name, 256)
    if name.value in SHELL_WINDOWS:
        return False
    rect = _Rect()
    user32.GetWindowRect(window, ctypes.byref(rect))
    info = _MonitorInfo(ctypes.sizeof(_MonitorInfo))
    user32.GetMonitorInfoW(user32.MonitorFromWindow(window, 2), ctypes.byref(info))
    screen = info.rcMonitor
    return (rect.left <= screen.left and rect.top <= screen.top
            and rect.right >= screen.right and rect.bottom >= screen.bottom)


def owner_present(idle_after):
    if not WINDOWS:
        return False
    return seconds_since_input() < idle_after or fullscreen_app()


def descendants(processes, root):
    created = {pid: moment for pid, _, moment in processes}
    children = {}
    for pid, parent, moment in processes:
        if pid != parent and moment >= created.get(parent, 0):
            children.setdefault(parent, []).append(pid)
    found, stack = [], [root]
    while stack:
        pid = stack.pop()
        if pid in found:
            continue
        found.append(pid)
        stack.extend(children.get(pid, []))
    return found


def _created(kernel32, pid):
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return 0
    creation, exited, kernel, user = (ctypes.c_ulonglong() for _ in range(4))
    ok = kernel32.GetProcessTimes(ctypes.c_void_p(handle), ctypes.byref(creation), ctypes.byref(exited),
                                  ctypes.byref(kernel), ctypes.byref(user))
    kernel32.CloseHandle(ctypes.c_void_p(handle))
    return creation.value if ok else 0


def _processes():
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel32.OpenProcess.restype = ctypes.c_void_p
    snapshot = ctypes.c_void_p(kernel32.CreateToolhelp32Snapshot(2, 0))
    entry = _ProcessEntry()
    entry.dwSize = ctypes.sizeof(_ProcessEntry)
    found = []
    more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
    while more:
        found.append((entry.th32ProcessID, entry.th32ParentProcessID, _created(kernel32, entry.th32ProcessID)))
        more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    kernel32.CloseHandle(snapshot)
    return found


def _each_windows_process(root, call):
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = ctypes.c_void_p
    for pid in descendants(_processes(), root):
        handle = kernel32.OpenProcess(0x0800, False, pid)
        if handle:
            call(ctypes.c_void_p(handle))
            kernel32.CloseHandle(ctypes.c_void_p(handle))


def start(args, cwd, env):
    if WINDOWS:
        return subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    return subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            start_new_session=True)


def suspend(process):
    if WINDOWS:
        _each_windows_process(process.pid, ctypes.windll.ntdll.NtSuspendProcess)
    else:
        os.killpg(os.getpgid(process.pid), signal.SIGSTOP)


def resume(process):
    if WINDOWS:
        _each_windows_process(process.pid, ctypes.windll.ntdll.NtResumeProcess)
    else:
        os.killpg(os.getpgid(process.pid), signal.SIGCONT)


def kill(process):
    if WINDOWS:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    else:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
