from enum import Enum
import os
import sys
import requests

CONSUL_URL_LB = "http://localhost:8500/v1/catalog/service/load-balancer"
CONSUL_URL_LL = "http://localhost:8500/v1/catalog/service/load-listener"
CONSUL_URL_WORKER = "http://localhost:8500/v1/health/service/worker"

class ComputeType(Enum):
    SUM_TO_N = 1
    SLEEP_FOR_SECONDS = 2

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def wait_for_enter():
    print()
    print("Press Enter to continue...", end="", flush=True)
    while True:
        char = sys.stdin.read(1)    # Reads one character at a time
        if char == "\n":            # Only proceed if Enter is pressed
            break

def get_lb_port():
    response = requests.get(CONSUL_URL_LB).json()
    if response:
        service = response[0]
        return service['ServicePort']
    return None

def get_ll_port():
    response = requests.get(CONSUL_URL_LL).json()
    if response:
        service = response[0]
        return service['ServicePort']
    return None