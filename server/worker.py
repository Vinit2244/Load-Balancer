# ============================= IMPORTS =============================
import argparse
import requests
import json
import subprocess
import sys
from concurrent import futures
import grpc
import logging
import threading
import time
import psutil

sys.path.append("generated")
import lb_pb2
import lb_pb2_grpc as lb_grpc
import worker_pb2
import worker_pb2_grpc as worker_grpc
sys.path.remove("generated")

sys.path.append("utils")
from utils import get_lb_port, get_ll_port, ComputeType
sys.path.remove("utils")

# ============================= GLOBALS =============================
my_port = None
my_id = None
my_interval = None

# ============================= CLASSES =============================
class WorkerServicer(worker_grpc.WorkerServicer):
    def Compute(self, request, context):
        logging.info(f"Received Compute request of type {request.type} with n = {request.n}")
        response_obj = worker_pb2.ComputeResponse()
        if request.type == ComputeType.SUM_TO_N.value:
            result = 0
            i = 1
            while i <= request.n:
                # result += i (Had removed this as it was giving out of bound error)
                result = result + 1
                i += 1
            response_obj.err_code = 0
            response_obj.msg = "Success"
            response_obj.result = result
        elif request.type == ComputeType.SLEEP_FOR_SECONDS.value:
            time.sleep(request.n)
            response_obj.err_code = 0
            response_obj.msg = "Success"
            response_obj.result = 0
        else:
            response_obj.err_code = 1
            response_obj.msg = "Invalid request type"
            response_obj.result = -1
        return response_obj


# ============================= THREADS =============================
def report_load():
    while True:
        ll_port = get_ll_port()
        ll_channel = grpc.insecure_channel(f"localhost:{ll_port}")
        ll_stub = lb_grpc.LoadListenerStub(ll_channel)
        request_obj = lb_pb2.ReportLoadRequest()

        request_obj.id = my_id
        cpu_usage = psutil.Process().cpu_percent(interval=1)
        request_obj.load = cpu_usage

        response = ll_stub.ReportLoad(request_obj)
        if response.err_code == 0:
            logging.info(f"Load reported to Load Balancer")
        else:
            logging.error(response.msg)
        ll_channel.close()
        time.sleep(my_interval)

# ============================= MAIN =============================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Worker')
    parser.add_argument("--port", type=int, help="Port Number for Worker")
    parser.add_argument("--id", type=int, help="Worker ID")
    parser.add_argument("--interval", type=int, default=10, help="Interval for Health Check")
    args = parser.parse_args()

    my_port = args.port
    my_id = args.id
    my_interval = args.interval

    logging.basicConfig(
        filename=f"./server/logs/worker_{my_id}.log",
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    data = {
        "service": {
            "name": "worker",
            "id": f"w-{my_id}",
            "port": my_port,
            "check": {
                "http": f"http://localhost:{my_port}/health",
                "interval": f"{my_interval}s"
            }
        }
    }

    # Creating a consul service definition file
    with open(f"./server/worker_{my_id}.json", "w") as json_file:
        json.dump(data, json_file)
    logging.info("Worker service definition file created")

    # Registering the service with consul
    command = ["consul", "services", "register", f"./server/worker_{my_id}.json"]
    try:
        result = subprocess.run(command, check=True)
        logging.info("Worker service registered with consul")
    except subprocess.CalledProcessError as e:
        logging.error("Error registering worker service")
        sys.exit(1)

    # Starting the worker server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    worker_grpc.add_WorkerServicer_to_server(WorkerServicer(), server)
    server.add_insecure_port(f"localhost:{my_port}")
    server.start()
    logging.info(f"Worker {my_id} server started")

    # Registering myself with the load balancing server
    lb_port = get_lb_port()
    lb_channel = grpc.insecure_channel(f"localhost:{lb_port}")
    lb_stub = lb_grpc.LBStub(lb_channel)
    request_obj = lb_pb2.RegisterWorkerRequest()
    
    request_obj.id = my_id
    request_obj.ip = "localhost"
    request_obj.port = my_port

    response = lb_stub.RegisterWorker(request_obj)
    if response.err_code == 0:
        logging.info(f"Woker {my_id} registered with Load Balancer")
    else:
        logging.error(response.msg)
    lb_channel.close()

    # Start the load notifier thread
    health_thread = threading.Thread(target=report_load, daemon=True)
    health_thread.start()
    logging.info("Load Reporting thread started")

    # Waiting for termination
    server.wait_for_termination()