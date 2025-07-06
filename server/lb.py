# ============================= IMPORTS =============================
import argparse
import json
import subprocess
import requests
import sys
import grpc
import logging
from concurrent import futures
import time
import threading
import signal
from pathlib import Path

lb_folder_path = Path(__file__).parent.resolve()

sys.path.append(str(lb_folder_path / "../generated"))
import lb_pb2
import lb_pb2_grpc as lb_grpc
import worker_pb2
import worker_pb2_grpc as worker_grpc

sys.path.append(str(lb_folder_path / "../utils"))
from utils import clear_screen, CONSUL_URL_WORKER

# ============================= GLOBALS =============================
WAIT_TIME_SEC = 5

my_port = None
my_interval = None
my_policy = None

workers = []
workers_lock = threading.Lock()

rr_last_used_index = -1

loads = {}

# ============================= CLASSES =============================
class LBServicer(lb_grpc.LBServicer):
    def RegisterWorker(self, request, context):
        logging.info(f"Register Worker request received from worker {request.id}")
        with workers_lock:
            workers.append({
                "id": request.id,
                "ip": request.ip,
                "port": request.port,
                "status": "active",
                "load": 0
            })

        response_obj = lb_pb2.RegisterWorkerResponse()
        response_obj.err_code = 0
        response_obj.msg = "Worker Registered Successfully"
        logging.info(f"Worker {request.id} registered successfully")
        return response_obj

    def GetServer(self, request, context):
        logging.info("Get Server request received")
        response_obj = lb_pb2.GetServerResponse()
        with workers_lock:
            if len(workers) == 0:
                response_obj.err_code = 1
                response_obj.msg = "No servers available"
                logging.error("No servers available")
                return response_obj
            
            if my_policy == "rr":
                servers_checked = 0 # To prevent infinite loop
                while True:
                    global rr_last_used_index
                    rr_last_used_index = (rr_last_used_index + 1) % len(workers)
                    # We increment the last index used by 1 and consider the new index as 
                    # the server to send (Take modulus to prevent index out of range)
                    # If the server is active, we send the server details
                    if workers[rr_last_used_index]["status"] == "active":
                        response_obj.ip = workers[rr_last_used_index]["ip"]
                        response_obj.port = workers[rr_last_used_index]["port"]
                        response_obj.id = workers[rr_last_used_index]["id"]
                        response_obj.err_code = 0
                        response_obj.msg = "Server found"
                        logging.info(f"Server found with id {response_obj.id}: {response_obj.ip}:{response_obj.port}")
                        break
                    # Else we check the next server and increment the number of servers checked
                    # When the number of servers checked is equal to the number of servers, we 
                    # break the loop as we have checked all the servers and none are active at the moment
                    servers_checked += 1
                    if servers_checked == len(workers):
                        response_obj.err_code = 1
                        response_obj.msg = "No servers available"
                        logging.error("No servers available")
                        break
            elif my_policy == "ll":
                min_load = 100 # We assume the maximum load to be 100% (If all the servers are at 100% we return no servers available)
                min_load_worker_idx = -1

                # Finding the worker with minimum load
                for idx, worker in enumerate(workers):
                    if worker["status"] == "active" and worker["load"] < min_load:
                        min_load = worker["load"]
                        min_load_worker_idx = idx
                # If a worker with minimum load is found, we send the server details
                if min_load_worker_idx != -1:
                    response_obj.ip = workers[min_load_worker_idx]["ip"]
                    response_obj.port = workers[min_load_worker_idx]["port"]
                    response_obj.id = workers[min_load_worker_idx]["id"]
                    response_obj.err_code = 0
                    response_obj.msg = "Server found"
                    logging.info(f"Server found with id {response_obj.id}: {response_obj.ip}:{response_obj.port}")
                else:
                    response_obj.err_code = 1
                    response_obj.msg = "No servers available"
                    logging.error("No servers available")
            elif my_policy == "pf":
                for worker in workers:
                    if worker["status"] == "active":
                        response_obj.ip = worker["ip"]
                        response_obj.port = worker["port"]
                        response_obj.id = worker["id"]
                        response_obj.err_code = 0
                        response_obj.msg = "Server found"
                        logging.info(f"Server found with id {response_obj.id}: {response_obj.ip}:{response_obj.port}")
                        break
                else:
                    response_obj.err_code = 1
                    response_obj.msg = "No servers available"
                    logging.error("No servers available")
            return response_obj

    
class LoadListenerServicer(lb_grpc.LoadListenerServicer):
    def ReportLoad(self, request, context):
        logging.info(f"Load reported from worker {request.id} = {request.load}%")
        with workers_lock:
            for worker in workers:
                if worker["id"] == request.id:
                    worker["load"] = request.load
                    try:
                        loads[request.id].append(request.load)
                    except KeyError:
                        loads[request.id] = [request.load]
                    break
        
        response_obj = lb_pb2.ReportLoadResponse()
        response_obj.err_code = 0
        response_obj.msg = "Load reported successfully"
        return response_obj


# ============================= SIGNAL HANDLER =============================
def shutdown_handler(signum, frame):
    logging.info("Shutting down server... Saving load data.")
    with open("./test_files/load.json", "w") as f:
        json.dump(loads, f)
    logging.info("Load data saved successfully.")
    sys.exit(0)

# Register signal handlers for graceful shutdown
signal.signal(signal.SIGINT, shutdown_handler)  # Handle Ctrl+C
signal.signal(signal.SIGTERM, shutdown_handler)  # Handle termination signals


# ============================= FUNCTIONS =============================
# --------------------------------------------------------------------------------
# Code from ChatGPT (Prompt 1)
# --------------------------------------------------------------------------------
def get_available_workers():
    response = requests.get("http://localhost:8500/v1/catalog/service/worker").json()
    return [(service['ServiceAddress'], service['ServicePort']) for service in response]

def get_alive_workers():
    response = requests.get(CONSUL_URL_WORKER).json()
    
    alive_servers = []
    for service in response:
        status = service["Checks"][0]["Status"]  # Get health check status
        if status == "passing":  # "passing" means the server is alive
            address = service["Service"]["Address"]
            port = service["Service"]["Port"]
            alive_servers.append((address, port))

    return alive_servers
# --------------------------------------------------------------------------------


# ============================= THREADS =============================
def health_check():
    while True:
        time.sleep(WAIT_TIME_SEC)  # Wait for the specified interval

        with workers_lock:  # Lock while accessing shared list
            alive_servers = get_alive_workers()
            addresses = []
            ports = []
            for address, port in alive_servers:
                addresses.append(address)
                ports.append(port)
            
            for worker in workers:
                if worker["port"] in ports:
                    worker["status"] = "active"
                else:
                    worker["status"] = "inactive"


# ============================= MAIN =============================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Load Balancer')
    parser.add_argument("--port", type=int, default=50051, help="Port Number for Load Balancer")
    parser.add_argument("--interval", type=int, default=10, help="Interval for Health Check")
    parser.add_argument("--policy", type=str, default="rr", help="Policy for Load Balancer") # Values = Round-Robin (rr), Least-Loaded (ll), Pick-First (pf)
    args = parser.parse_args()

    my_port = args.port
    my_interval = args.interval
    my_policy = args.policy

    logging.basicConfig(
        filename=f"./server/logs/lb.log",
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # Starting the Load Balancer server
    data = {
        "service": {
            "name": "load-balancer",
            "id": "lb",
            "port": my_port,
            "check": {
                "http": f"http://localhost:{my_port}/health",
                "interval": f"{my_interval}s"
            }
        }
    }

    # Creating a consul service definition file
    with open("./server/lb.json", "w") as json_file:
        json.dump(data, json_file)
    logging.info("Load Balancer service definition file created")

    # Registering the service with consul
    command = ["consul", "services", "register", "./server/lb.json"]
    try:
        result = subprocess.run(command, check=True)
        logging.info("Load Balancer service registered with consul")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error registering service: {e}")
        logging.error("Error registering load balancer service")
        sys.exit(1)

    # Starting load balancing server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    lb_grpc.add_LBServicer_to_server(LBServicer(), server)
    server.add_insecure_port(f"localhost:{my_port}")
    server.start()
    logging.info(f"Load Balancing server started at port {my_port}")

    # Start the health check thread
    health_thread = threading.Thread(target=health_check, daemon=True)
    health_thread.start()
    logging.info("Health check thread started")

    # Starting the Load listener server
    load_listener_data = {
        "service": {
            "name": "load-listener",
            "id": "ll",
            "port": my_port + 1,
            "check": {
                "http": f"http://localhost:{my_port + 1}/health",
                "interval": f"{my_interval}s"
            }
        }
    }

    # Creating a consul service definition file
    with open("./server/ll.json", "w") as json_file:
        json.dump(load_listener_data, json_file)
    logging.info("Load Listener service definition file created")

    # Registering the service with consul
    command = ["consul", "services", "register", "./server/ll.json"]
    try:
        result = subprocess.run(command, check=True)
        logging.info("Load Listener service registered with consul")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error registering service: {e}")
        logging.error("Error registering load listener service")
        sys.exit(1)

    # Starting load listening server
    ll_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    lb_grpc.add_LoadListenerServicer_to_server(LoadListenerServicer(), ll_server)
    ll_server.add_insecure_port(f"localhost:{my_port + 1}")
    ll_server.start()
    logging.info(f"Load Listener server started at port {my_port + 1}")

    clear_screen()

    # Waiting for termination
    server.wait_for_termination()
    ll_server.wait_for_termination()