# ============================= IMPORTS =============================
import sys
import grpc
import time
import argparse
import matplotlib.pyplot as plt
import signal
from pathlib import Path

client_folder_abs_path = Path(__file__).parent.resolve()

sys.path.append(str(client_folder_abs_path / "../generated"))
import lb_pb2
import lb_pb2_grpc as lb_grpc
import worker_pb2
import worker_pb2_grpc as worker_grpc

sys.path.append(str(client_folder_abs_path / "../utils"))
from utils import clear_screen, wait_for_enter, get_lb_port, ComputeType


# ============================= FUNCTIONS =============================
def ask_lb_for_worker_info():
    lb_port = get_lb_port()
    lb_channel = grpc.insecure_channel(f"localhost:{lb_port}")
    lb_stub = lb_grpc.LBStub(lb_channel)
    request_obj = lb_pb2.GetServerRequest()
    response = lb_stub.GetServer(request_obj)
    if response.err_code == 1:
        print("No servers available. Please try again later.")
        return None
    return f"{response.ip}:{response.port}"


def sum_to_n(n):
    server_address = ask_lb_for_worker_info()
    if server_address is None:
        return
    request_obj = worker_pb2.ComputeRequest()
    request_obj.type = ComputeType.SUM_TO_N.value
    request_obj.n = n
    channel = grpc.insecure_channel(server_address)
    stub = worker_grpc.WorkerStub(channel)
    response = stub.Compute(request_obj)
    if response.err_code == 1:
        print("Error: ", response.msg)
        return
    print(f"Sum of numbers from 1 to {n} is {response.result}")


def sleep_for_seconds(seconds):
    server_address = ask_lb_for_worker_info()
    if server_address is None:
        return
    request_obj = worker_pb2.ComputeRequest()
    request_obj.type = ComputeType.SLEEP_FOR_SECONDS.value
    request_obj.n = seconds
    channel = grpc.insecure_channel(server_address)
    stub = worker_grpc.WorkerStub(channel)
    response = stub.Compute(request_obj)
    if response.err_code == 1:
        print("Error: ", response.msg)
        return
    print(f"Slept for {seconds} seconds")


def menu():
    while True:
        clear_screen()

        # Print the menu
        print("Please select an option: (Enter 'exit' to EXIT)")
        print("  1. Sum to N")
        print("  2. Sleep")
        print()
        opt = input("Enter your choice: ").strip()
        print()

        if opt == "1":
            try:
                n = int(input("Enter the value of N: "))
            except:
                print("Invalid input. Please enter a valid integer.")
                wait_for_enter()
                continue
            start_time = time.time()
            sum_to_n(n)
            end_time = time.time()
            print(f"Time taken: {end_time - start_time} seconds")
            wait_for_enter()
        elif opt == "2":
            try:
                seconds = int(input("Enter the number of seconds to sleep: "))
                start_time = time.time()
                sleep_for_seconds(seconds)
                end_time = time.time()
                print(f"Time taken: {end_time - start_time} seconds")
                wait_for_enter()
            except:
                print("Invalid input. Please enter a valid integer.")
                wait_for_enter()
                continue
        elif opt.lower() == "exit":
            print("Exiting the client...")
            break
        else:
            print("Invalid option.")
            wait_for_enter()
            continue

# ============================= SIGNAL HANDLER =============================
time_arr = list()
start_time = None
end_time = None
req_idx = 0
id = None

def shutdown_handler(signum, frame):
    print()
    th = req_idx / (end_time - start_time)
    print("Throughput:", th, "req/s")
    print("Total time taken:", end_time - start_time, "s")
    print("Average response time:", sum(time_arr) / len(time_arr), "s")

    # Plotting
    plt.plot(time_arr)
    plt.xlabel("Request Index")
    plt.ylabel("Response Time (s)")
    plt.title("Response Times")
    plt.savefig(f"./test_files/response_times_client_{id}.png")
    plt.close()

    sys.exit(0)

# Register signal handlers for graceful shutdown
signal.signal(signal.SIGINT, shutdown_handler)  # Handle Ctrl+C
signal.signal(signal.SIGTERM, shutdown_handler)  # Handle termination signals

# ============================= MAIN =============================
if __name__ == "__main__":
    argparser = argparse.ArgumentParser()
    argparser.add_argument("--mode", type=str, default="i", help="Interactive (i) or Script (s) mode")
    argparser.add_argument("--load", type=str, default="high", help="Amount of load to simulate")
    argparser.add_argument("--reqs", type=int, default=10, help="Number of requests to run for")
    argparser.add_argument("--id", type=int, help="Client ID", required=True)

    args = argparser.parse_args()
    mode = args.mode

    if mode.lower() == "i":
        menu()
        
    elif mode.lower() == "s":
        load = args.load.lower()
        id = args.id
        n_requests = args.reqs

        if load is None:
            print("Please provide the amount of load to simulate.")
            sys.exit(1)
        if load == "low":
            n = 1000
        elif load == "med":
            n = 1000000
        elif load == "high":
            n = 50000000
        else:
            print("Invalid load. Please provide either 'low', 'med', or 'high'.")
            sys.exit(1)
        
        # Simulating load
        start_time = time.time()
        req_idx = 0
        # time_arr = list()
        while True:
            print("Sending request", req_idx)
            req_idx += 1
            s_time = time.time()
            sum_to_n(n)
            e_time = time.time()
            time_arr.append(e_time - s_time)
            if req_idx == n_requests:
                break
        end_time = time.time()

        # Calculating Metrics
        # print()
        # th = req_idx / (end_time - start_time)
        # print("Throughput:", th, "req/s")
        # print("Total time taken:", end_time - start_time, "s")
        # print("Average response time:", sum(time_arr) / len(time_arr), "s")

        # # Plotting
        # plt.plot(time_arr)
        # plt.xlabel("Request Index")
        # plt.ylabel("Response Time (s)")
        # plt.title("Response Times")
        # plt.savefig(f"./test_files/response_times_client_{id}.png")
        # plt.close()
    else:
        print("Invalid mode. Please provide either 'i' or 's'.")
        sys.exit(1)