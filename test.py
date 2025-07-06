import subprocess
import time
import signal
import argparse

def start_testing(args):
    processes = []

    try:
        # Start Consul
        print("Starting Consul...")
        processes.append(subprocess.Popen(["consul", "agent", "-dev"], stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        time.sleep(2)

        # Start Load Balancer
        print("Starting Load Balancer...")
        processes.append(subprocess.Popen(["python3", "server/lb.py", f"--port={args.lb_port}", f"--interval={args.interval}", f"--policy={args.policy}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT))
        time.sleep(2)

        # Start worker processes
        print(f"Starting {args.n_workers} Worker processes...")
        for i in range(1, args.n_workers + 1):
            print(f"Starting Worker {i}...")
            processes.append(subprocess.Popen(["python3", "server/worker.py", f"--port={args.lb_port + 1 + i}", f"--id={i}", f"--interval={args.interval}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT))
        # processes.append(subprocess.Popen(["make", "workers", f"WORKERS={args.n_workers}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        time.sleep(2)

        # Start client processes
        print(f"Starting Client processes...")
        client_processes = []
        for i in range(1, args.n_clients + 1):
            print(f"Starting Client {i}...")
            proc = subprocess.Popen(["python3", "client/client.py", "--mode=s", f"--load={args.load}", f"--reqs={args.n_requests}", f"--id={i}"], 
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            client_processes.append(proc)

        # Wait for all client processes to finish
        print("Waiting for all clients to finish...")
        for proc in client_processes:
            proc.wait()

    finally:
        # Kill all other processes once all clients are done
        print("Terminating all processes...")
        for process in processes:
            process.send_signal(signal.SIGTERM)  # Graceful termination

        print("All processes terminated.")

        # Visualising
        print("Visualising the load...")
        processes.append(subprocess.Popen(["python3", "./test_files/visualise_load.py", f"--policy={args.policy}", f"--workers={args.n_workers}", f"--load={args.load}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE))

if __name__ == "__main__":
    argparser = argparse.ArgumentParser()
    argparser.add_argument("--lb_port",     default=50051,  type=int, help="Port number for Load Balancer")
    argparser.add_argument("--n_workers",   default=15,      type=int, help="Number of workers to start")
    argparser.add_argument("--n_clients",   default=100,      type=int, help="Number of client processes to start")
    argparser.add_argument("--interval",    default=1,      type=int, help="Interval for health check and load reporting")
    argparser.add_argument("--policy",      default="rr",   type=str, help="Policy to use for load balancing")
    argparser.add_argument("--load",        default="high",  type=str, help="Amount of load to simulate")
    argparser.add_argument("--n_requests",  default=1,    type=int, help="Number of requests to run for each client")

    args = argparser.parse_args()
    start_testing(args)