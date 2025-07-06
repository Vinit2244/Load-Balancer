import json
import matplotlib.pyplot as plt
import argparse

def visualise_load(policy, n_workers, load):
    # Load the JSON data
    with open("./test_files/load.json", "r") as f:
        data = json.load(f)

    plt.figure(figsize=(10, 6))  # Adjust the figure size

    # Iterate over each worker ID and plot its load over time
    for worker_id, loads in data.items():
        x = list(range(1, len(loads) + 1))  # X-axis: Time (assuming sequential timestamps)
        y = loads  # Y-axis: Load percentages
        
        plt.plot(x, y, marker="o", linestyle="-", label=f"Worker {worker_id}")  # Line with markers

    # Labels and title
    plt.xlabel("Time")
    plt.ylabel("Load (%)")
    plt.title("Worker Load Over Time")

    # Add legend and grid
    plt.legend(title="Workers", loc="upper right")
    plt.grid(True)

    # Save and show the plot
    plt.savefig(f"./test_files/{policy}_{n_workers}workers_{load}_load.png")
    plt.close()

if __name__ == "__main__":
    argparser = argparse.ArgumentParser()
    argparser.add_argument("--policy", type=str, help="Specify the policy for which the graph is being plotted")
    argparser.add_argument("--workers", type=int, help="Number of workers used for testing")
    argparser.add_argument("--load", type=str, help="Load amount for testing")

    args = argparser.parse_args()
    policy = args.policy
    n_workers = args.workers
    load = args.load

    # Call the function to generate the plot
    visualise_load(policy, n_workers, load)
