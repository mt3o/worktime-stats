import json
import threading
from time import sleep

import sqlite3

import win32gui
import win32con
import win32process
import psutil

from ctypes import windll, Structure, c_uint, sizeof, byref

import signal
import sys


class LASTINPUTINFO(Structure):
    _fields_ = [("cbSize", c_uint), ("dwTime", c_uint)]


def main():
    stop_working = threading.Event()
    monitor_sleep = 1

    def monitor():
        nonlocal stop_working
        nonlocal monitor_sleep

        IDLE_THRESHOLD = 10
        SQLITE_NAME = 'store.sqlite'

        db = sqlite3.connect(SQLITE_NAME)
        db.execute("""
        CREATE TABLE IF NOT EXISTS data_samples (
            id integer PRIMARY KEY AUTOINCREMENT,        
            timestamp DATE default (datetime('now','localtime')),
            window_title text,
            process_name text,
            mouse_x integer,
            mouse_y integer,
            is_idle integer,
            idle_delta real,
            details json    
        )
        """)

        try:
            db_cursor = db.cursor()

            last_input_info = LASTINPUTINFO()
            last_input_info.cbSize = sizeof(last_input_info)
            windll.user32.GetLastInputInfo(byref(last_input_info))  # update the struct

            while not stop_working.is_set():
                window = win32gui.GetForegroundWindow()
                win_title = win32gui.GetWindowText(window)
                window_long = win32gui.GetWindowLong(window, win32con.GWL_STYLE)
                application_instance = win32gui.GetWindowLong(window, win32con.GWL_HINSTANCE)
                window_parent_instance = win32gui.GetWindowLong(window, win32con.GWL_HWNDPARENT)
                win_is_child = window_long & win32con.WS_CHILD
                win_is_popup = window_long & win32con.WS_POPUP
                pids = win32process.GetWindowThreadProcessId(window)

                windll.user32.GetLastInputInfo(byref(last_input_info))  # update the struct
                idle_delta = float(windll.kernel32.GetTickCount() - last_input_info.dwTime) / 1000

                mouse_flags, mouse_hcursor, (mouse_x, mouse_y) = win32gui.GetCursorInfo()

                process_names = []
                for pid in pids:
                    try:
                        process_name = psutil.Process(pid).name()
                        process_names.append((pid, process_name))
                    except psutil.NoSuchProcess:
                        pass
                details = {

                }
                data = {
                    'window_title': win_title,
                    'process_name': " ".join([proc_name for pid, proc_name in process_names]),
                    'mouse_x': mouse_x,
                    'mouse_y': mouse_y,
                    'details': json.dumps(details),
                    'is_idle': idle_delta > IDLE_THRESHOLD,
                    'idle_delta': idle_delta,
                }
                fields = data.keys()

                field_list = ",".join([_ for _ in fields])
                placeholders = ",".join(['?' for _ in fields])

                sql = f" insert into data_samples ({field_list}) values ({placeholders})"
                values = data.values()
                db_cursor.execute(sql,list(values))
                db.commit()

                sleep(monitor_sleep)
        finally:
            db.commit()
            db.close()



    monitor_thread = threading.Thread(target=monitor)
    monitor_thread.start()
    

    def signal_int_handler():
        nonlocal stop_working
        stop_working.set()
        monitor_thread.join()
        sys.exit(0)

    print("Exit with Ctrl+C")

    # signal.signal(signal.SIGINT, signal_int_handler) # linux
    # signal.pause() # linux, not working on windows

    signal.signal(signal.SIGBREAK, signal_int_handler)  # windows
    signal.signal(signal.SIGINT, signal_int_handler)  # windows
    signal.signal(signal.SIGTERM, signal_int_handler)  # windows
    try:  # windows is hacky
        while True:
            sleep(1)
    except KeyboardInterrupt:
        signal_int_handler()

    pass


if __name__ == '__main__':
    main()
