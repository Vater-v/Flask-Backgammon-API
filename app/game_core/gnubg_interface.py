# app/game_core/gnubg_interface.py

import subprocess
import os
import sys

def run_gnubg_process(command_input: str) -> str:

    process = subprocess.Popen(
        ['gnubg'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        cwd=os.path.dirname(os.path.abspath(__file__)) 
    )

    try:
        stdout_data, _ = process.communicate(input=command_input)
        return stdout_data

    except Exception as e:
        print(f"[GnuBGInterface] Ошибка во время run_gnubg_process: {e}", file=sys.stderr)
        process.kill()
        return ""