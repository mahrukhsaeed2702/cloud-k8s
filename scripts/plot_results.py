import os, re, csv
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

os.makedirs("results", exist_ok=True)

# ── helpers ──────────────────────────────────────────────────────────────────

def parse_ab(filepath):
    """Return (mean_ms, rps) from httperf or ab output file, or (None, None)."""
    mean_ms = rps = None
    try:
        with open(filepath) as f:
            for line in f:
                # httperf: "Reply time [ms]: response 1.4 transfer 0.0"
                m = re.search(r'Reply time \[ms\]: response ([\d.]+)', line)
                if m:
                    mean_ms = float(m.group(1))
                # ab: "Time per request: 10.234 [ms] (mean)"
                m = re.search(r'Time per request:\s+([\d.]+)\s+\[ms\]\s+\(mean\)', line)
                if m:
                    mean_ms = float(m.group(1))
                # httperf: "Request rate: 10.0 req/s"
                m2 = re.search(r'Request rate:\s+([\d.]+)\s+req/s', line)
                if m2:
                    rps = float(m2.group(1))
                # ab: "Requests per second: 95.23"
                m2 = re.search(r'Requests per second:\s+([\d.]+)', line)
                if m2:
                    rps = float(m2.group(1))
    except FileNotFoundError:
        pass
    return mean_ms, rps

# ── Graph 1: response time vs request rate ───────────────────────────────────

rates = [10, 25, 50, 100, 200]
replica_configs = [1, 2, 3]
colors = ['#1f77b4', '#ff7f0e', '#2ca02c']

fig, ax = plt.subplots(figsize=(10, 6))
for i, r in enumerate(replica_configs):
    times = []
    valid_rates = []
    for rate in rates:
        path = f"results/run_r{r}_rps{rate}.txt"
        mean_ms, _ = parse_ab(path)
        if mean_ms is not None:
            times.append(mean_ms)
            valid_rates.append(rate)
    if times:
        ax.plot(valid_rates, times, marker='o', label=f'{r} replica(s)', color=colors[i])

ax.set_title("Graph 1: Avg Response Time vs Request Rate")
ax.set_xlabel("Request Rate (req/s)")
ax.set_ylabel("Avg Response Time (ms)")
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("results/graph1_response_time.png", dpi=150)
plt.close()
print("Saved graph1_response_time.png")

# ── Graph 2: CPU per pod ──────────────────────────────────────────────────────

csv_path = "results/pod_cpu.csv"
pod_data = {}  # short_name -> list of (sample_idx, cpu_val)
try:
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        pod_counters = {}  # track sample index per pod
        for row in reader:
            pod = row.get('pod', '').strip()
            if not pod or pod == 'pod':
                continue
            short = '-'.join(pod.split('-')[-2:])  # last 2 parts e.g. "9c6f5"
            cpu_raw = row.get('cpu', '0m').strip()
            try:
                if cpu_raw.endswith('m'):
                    cpu_val = float(cpu_raw[:-1]) / 250 * 100  # millicores → %
                else:
                    cpu_val = float(cpu_raw)
            except ValueError:
                cpu_val = 0
            pod_counters[short] = pod_counters.get(short, 0)
            pod_data.setdefault(short, []).append((pod_counters[short], cpu_val))
            pod_counters[short] += 1
except FileNotFoundError:
    print(f"Warning: {csv_path} not found, skipping graph 2")
    pod_data = {}

if pod_data:
    pod_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    fig, ax = plt.subplots(figsize=(12, 6))

    for i, (pod_short, samples) in enumerate(sorted(pod_data.items())):
        xs = [s[0] for s in samples]
        ys = [s[1] for s in samples]
        color = pod_colors[i % len(pod_colors)]
        ax.plot(xs, ys, marker='o', markersize=3, linewidth=1.5,
                color=color, label=f'pod-{pod_short}')

    ax.set_title("Graph 2: CPU Utilization per Pod (100 req/s, 3 replicas)")
    ax.set_xlabel("Sample (every 15s)")
    ax.set_ylabel("CPU Utilization (%)")
    ax.set_ylim(0)
    ax.legend(loc='upper right', fontsize=9)
    ax.grid(True, alpha=0.3, linestyle='--')
    plt.tight_layout()
    plt.savefig("results/graph2_cpu_per_pod.png", dpi=150)
    plt.close()
    print("Saved graph2_cpu_per_pod.png")

# ── Graph 3: autoscale ────────────────────────────────────────────────────────

hpa_path = "results/hpa_autoscale.csv"
timestamps, replicas_list, cpu_list = [], [], []

# infer request rate from phase boundaries
phase_rates = []  # will be filled per sample

try:
    with open(hpa_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if rows:
        n = len(rows)

        for idx, row in enumerate(rows):
            timestamps.append(idx)
            try:
                replicas_list.append(int(row['replicas']))
            except (ValueError, KeyError):
                replicas_list.append(replicas_list[-1] if replicas_list else 1)
            try:
                # cpu_target looks like "28%/50%" — extract first number
                raw = row.get('cpu_target', '0').strip()
                cpu_val = float(re.search(r'(\d+)', raw).group(1)) if re.search(r'(\d+)', raw) else 0
                cpu_list.append(cpu_val)
            except (ValueError, AttributeError):
                cpu_list.append(0)
            # phase boundaries: 2min @20c, 5min @100c, 3min @20c = 10min total
            # at 15s per sample: ~8 samples, ~20 samples, ~12 samples
            if idx < 8:
                phase_rates.append(20)
            elif idx < 28:
                phase_rates.append(100)
            else:
                phase_rates.append(20)

        fig, ax1 = plt.subplots(figsize=(12, 6))
        ax2 = ax1.twinx()

        ax1.plot(timestamps, phase_rates, 'b--', label='Request Rate (req/s)', alpha=0.7)
        ax1.plot(timestamps, cpu_list, 'r-', label='Avg CPU %', linewidth=2)
        ax2.plot(timestamps, replicas_list, 'g-', label='Replicas', linewidth=2)

        ax1.set_xlabel("Sample (every 15s)")
        ax1.set_ylabel("Request Rate / CPU %")
        ax2.set_ylabel("Replica Count")

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

        ax1.set_title("Graph 3: Autoscaling Test — Rate, CPU & Replicas over 10 min")
        ax1.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig("results/graph3_autoscale.png", dpi=150)
        plt.close()
        print("Saved graph3_autoscale.png")

except FileNotFoundError:
    print(f"Warning: {hpa_path} not found, skipping graph 3")

print("Done.")
