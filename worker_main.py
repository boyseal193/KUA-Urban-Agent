#!/usr/bin/env python3
"""Railway worker entrypoint: python worker_main.py"""

from jobs.worker import worker_loop

if __name__ == "__main__":
    worker_loop()
