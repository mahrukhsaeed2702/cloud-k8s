"""
Combined dashboard: all metrics over time in one tall figure.
Saves results/graph_combined.png and results/graph_combined.pdf
"""

import os, re, csv
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np

os.makedirs("results", exist_ok=True)

# ── Load Graph 2 data: per-pod CPU over time ──────────────────────────────────
pod_data = {}  # short_name -> list of cpu values
csv_path = "results/pod_cpu.csv"
try:
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        pod_counters = {}
        for row in reader:
            pod = row.get('pod', '').strip()
            if not pod or pod == 'pod':
                continue
            short = '-'.join(pod.split('-')[-2:])
            cpu_raw = row.get('cpu', '0m').strip()
            try:
                cpu_val = float(cpu_raw[:-1]) / 250 * 100 if cpu_raw.endswith('m') else float(cpu_raw)
            except ValueError:
                cpu_val = 0
            pod_data.setdefault(short, []).append(cpu_val)
except FileNotFoundError:
    print(f"Warning: {csv_path} not found")

# ── Load Graph 3 data: replicas, CPU, request rate over time ─────────────────
hpa_path = "results/hpa_autoscale.csv"
hpa_samples, replicas_list, hpa_cpu_list, phase_rates = [], [], [], []
try:
    with open(hpa_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    for idx, row in enumerate(rows):
        hpa_samples.append(idx * 15 / 60)   # convert to minutes
        try:
            replicas_list.append(int(row['replicas']))
        except (ValueError, KeyError):
            replicas_list.append(replicas_list[-1] if replicas_list else 1)
        try:
            raw = row.get('cpu_target', '0').strip()
            m = re.search(r'(\d+)', raw)
            hpa_cpu_list.append(float(m.group(1)) if m else 0)
        except (ValueError, AttributeError):
            hpa_cpu_list.append(0)
        # phase: 2min baseline (8 samples), 5min high (20), 3min cooldown (12)
        if idx < 8:
            phase_rates.append(20)
        elif idx < 28:
            phase_rates.append(100)
        else:
            phase_rates.append(20)
except FileNotFoundError:
    print(f"Warning: {hpa_path} not found")

# ── Load Graph 1 data: response time vs request rate ─────────────────────────
rates = [10, 25, 50, 100, 200]
replica_configs = [1, 2, 3]

def parse_ab(filepath):
    mean_ms = None
    try:
        with open(filepath) as f:
            for line in f:
                m = re.search(r'Time per request:\s+([\d.]+)\s+\[ms\]\s+\(mean\)', line)
                if m:
                    mean_ms = float(m.group(1))
    except FileNotFoundError:
        pass
    return mean_ms

g1_data = {}
for r in replica_configs:
    times, valid_rates = [], []
    for rate in rates:
        path = f"results/run_r{r}_rps{rate}.txt"
        mean_ms = parse_ab(path)
        if mean_ms is not None:
            times.append(mean_ms)
            valid_rates.append(rate)
    if times:
        g1_data[r] = (valid_rates, times)

# ── Build combined figure ─────────────────────────────────────────────────────
pod_colors  = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
replica_clr = ['#1f77b4', '#ff7f0e', '#2ca02c']

n_rows = 4  # request rate | replicas | HPA CPU | per-pod CPU
has_g1 = bool(g1_data)
if has_g1:
    n_rows = 5  # add response-time row at top

fig = plt.figure(figsize=(14, n_rows * 3.2))
fig.suptitle("DS584 Assignment 04 — Performance Dashboard", fontsize=15, fontweight='bold', y=0.995)

gs = gridspec.GridSpec(n_rows, 1, hspace=0.55)
row = 0

# ── Subplot A: Response Time vs Request Rate (Graph 1 — bar + line) ──────────
if has_g1:
    ax_rt = fig.add_subplot(gs[row]); row += 1
    for i, r in enumerate(replica_configs):
        if r in g1_data:
            vr, tm = g1_data[r]
            ax_rt.plot(vr, tm, marker='o', linewidth=2, color=replica_clr[i], label=f'{r} replica(s)')
    ax_rt.set_title("(a) Avg Response Time vs Request Rate", fontsize=11, fontweight='bold')
    ax_rt.set_xlabel("Request Rate (req/s)")
    ax_rt.set_ylabel("Avg Response Time (ms)")
    ax_rt.legend(fontsize=9)
    ax_rt.grid(True, alpha=0.3)

# ── Subplot B: Concurrency / Request Rate over time (Graph 3 phase) ──────────
if hpa_samples:
    ax_rr = fig.add_subplot(gs[row]); row += 1
    ax_rr.step(hpa_samples, phase_rates, where='post', color='#5b6abf', linewidth=2)
    ax_rr.fill_between(hpa_samples, phase_rates, step='post', alpha=0.15, color='#5b6abf')
    ax_rr.set_title("(b) Concurrent Connections over Time (Autoscale Test)", fontsize=11, fontweight='bold')
    ax_rr.set_xlabel("Time (minutes)")
    ax_rr.set_ylabel("Concurrency")
    ax_rr.set_yticks([20, 100])
    ax_rr.set_yticklabels(['20\n(baseline)', '100\n(high load)'])
    # shade phases
    ax_rr.axvspan(0,         8*15/60,  alpha=0.05, color='green',  label='Baseline')
    ax_rr.axvspan(8*15/60,  28*15/60,  alpha=0.05, color='red',    label='High Load')
    ax_rr.axvspan(28*15/60, 41*15/60,  alpha=0.05, color='green',  label='Cooldown')
    ax_rr.legend(fontsize=8, loc='upper right')
    ax_rr.grid(True, alpha=0.3)

# ── Subplot C: Replica Count over time ───────────────────────────────────────
if replicas_list:
    ax_rep = fig.add_subplot(gs[row]); row += 1
    ax_rep.step(hpa_samples, replicas_list, where='post', color='#2ca02c', linewidth=2.5)
    ax_rep.fill_between(hpa_samples, replicas_list, step='post', alpha=0.15, color='#2ca02c')
    ax_rep.set_title("(c) HPA Replica Count over Time", fontsize=11, fontweight='bold')
    ax_rep.set_xlabel("Time (minutes)")
    ax_rep.set_ylabel("Replicas")
    ax_rep.set_ylim(0, 6)
    ax_rep.set_yticks([1, 2, 3, 4, 5])
    ax_rep.axhline(y=5, color='red', linestyle='--', alpha=0.5, label='Max replicas (5)')
    ax_rep.axhline(y=1, color='gray', linestyle='--', alpha=0.4, label='Min replicas (1)')
    ax_rep.legend(fontsize=8, loc='center right')
    ax_rep.grid(True, alpha=0.3)

# ── Subplot D: HPA avg CPU over time ─────────────────────────────────────────
if hpa_cpu_list:
    ax_hcpu = fig.add_subplot(gs[row]); row += 1
    ax_hcpu.plot(hpa_samples, hpa_cpu_list, color='#d62728', linewidth=2)
    ax_hcpu.fill_between(hpa_samples, hpa_cpu_list, alpha=0.1, color='#d62728')
    ax_hcpu.axhline(y=50, color='orange', linestyle='--', linewidth=1.5, label='HPA target (50%)')
    ax_hcpu.set_title("(d) Average CPU Utilization over Time (Autoscale Test)", fontsize=11, fontweight='bold')
    ax_hcpu.set_xlabel("Time (minutes)")
    ax_hcpu.set_ylabel("Avg CPU %")
    ax_hcpu.legend(fontsize=8)
    ax_hcpu.grid(True, alpha=0.3)

# ── Subplot E: Per-pod CPU over time (Graph 2) ───────────────────────────────
if pod_data:
    ax_pod = fig.add_subplot(gs[row]); row += 1
    max_samples = max(len(v) for v in pod_data.values())
    xs = [i * 15 / 60 for i in range(max_samples)]   # minutes
    for i, (pod_short, vals) in enumerate(sorted(pod_data.items())):
        px = xs[:len(vals)]
        ax_pod.plot(px, vals, marker='o', markersize=3, linewidth=1.8,
                    color=pod_colors[i % len(pod_colors)], label=f'pod-{pod_short}')
    ax_pod.axhline(y=50, color='orange', linestyle='--', linewidth=1.2, label='HPA target (50%)')
    ax_pod.set_title("(e) Per-Pod CPU Utilization over Time (100 concurrent, 3→5 replicas)", fontsize=11, fontweight='bold')
    ax_pod.set_xlabel("Time (minutes)")
    ax_pod.set_ylabel("CPU Utilization (%)")
    ax_pod.set_ylim(0)
    ax_pod.legend(fontsize=8, loc='upper right')
    ax_pod.grid(True, alpha=0.3)

plt.savefig("results/graph_combined.png", dpi=150, bbox_inches='tight')
plt.savefig("results/graph_combined.pdf", bbox_inches='tight')
plt.close()
print("Saved results/graph_combined.png and results/graph_combined.pdf")
