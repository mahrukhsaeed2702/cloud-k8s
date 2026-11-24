"""
plot_combined_test.py
Plots all metrics from the single combined_test.sh experiment.
All graphs share the same time axis (minutes from experiment start).

Graphs produced:
  G1: Time vs Per-Pod CPU          (combined_pod_cpu.csv)
  G2: Time vs Active Replica Count (combined_pod_cpu.csv — count unique pods)
  G3: Time vs HPA Replica Count    (combined_hpa.csv)
  G4: Time vs HPA Aggregate CPU    (combined_hpa.csv)
  G5: Time vs Response Time        (combined_phase1/2/3.txt — mean, p50, p95, p99)
  G6: Time vs Concurrency          (phase boundaries)

  BONUS: B1 — Request Rate vs Response Time (original load dist benchmark)

All saved as individual PNGs + one combined PDF.
"""

import os, re, csv, math
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.image as mpimg

os.makedirs("results", exist_ok=True)

INTERVAL = 15 / 60   # 15s in minutes
pod_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']

def setup(ax, title, xlabel, ylabel):
    ax.set_title(title, fontsize=11, fontweight='bold')
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.grid(True, alpha=0.3, linestyle='--')

def add_phase_shading(ax):
    """Shade the 3 phases on any time axis."""
    ax.axvspan(0,          2,  alpha=0.06, color='green')
    ax.axvspan(2,          7,  alpha=0.06, color='red')
    ax.axvspan(7,         10,  alpha=0.06, color='green')
    ymax = ax.get_ylim()[1]
    for x, label in [(1, 'Baseline'), (4.5, 'High Load'), (8.5, 'Cooldown')]:
        ax.text(x, ymax * 0.97, label, ha='center', va='top', fontsize=7.5,
                color='gray', style='italic')

def save(fig, name):
    fig.tight_layout()
    fig.savefig(f"results/{name}.png", dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved results/{name}.png")

# ── Phase boundaries (minutes) ────────────────────────────────────────────────
PHASE_BOUNDS = [(0, 2, 20), (2, 7, 100), (7, 10, 20)]  # (start, end, concurrency)

# ═══════════════════════════════════════════════════════════════════════════════
# LOAD DATA
# ═══════════════════════════════════════════════════════════════════════════════

# Per-pod CPU
pod_data  = {}   # short -> [cpu_val, ...]
pod_times = {}   # short -> [time_min, ...]
pod_counters = {}

try:
    with open("results/combined_pod_cpu.csv") as f:
        raw_rows = list(csv.DictReader(f))

    # Find the earliest timestamp in the file (t=0 of this run)
    from datetime import datetime
    timestamps = []
    for row in raw_rows:
        ts = row.get('timestamp', '').strip()
        if ts:
            try:
                timestamps.append(datetime.fromisoformat(ts))
            except ValueError:
                pass
    t0 = min(timestamps) if timestamps else None

    # First pass: collect first-seen time for each pod
    pod_first_seen = {}
    for row in raw_rows:
        pod = row.get('pod', '').strip()
        if not pod or pod == 'pod':
            continue
        short = '-'.join(pod.split('-')[-2:])
        ts = row.get('timestamp', '').strip()
        if ts and t0:
            try:
                elapsed = (datetime.fromisoformat(ts) - t0).total_seconds() / 60
                if short not in pod_first_seen:
                    pod_first_seen[short] = elapsed
            except ValueError:
                pass

    # Only keep pods first seen within first 8 minutes (exclude stale pods from prev run
    # that show up with high CPU at t=0 — they were already running before this test)
    # A pod from THIS run either starts at t=0 with 0% CPU (the original pod)
    # or appears later when HPA scales up. We detect stale pods as those with
    # CPU > 20% in their very first sample.
    pod_first_cpu = {}
    for row in raw_rows:
        pod = row.get('pod', '').strip()
        if not pod or pod == 'pod':
            continue
        short = '-'.join(pod.split('-')[-2:])
        if short in pod_first_cpu:
            continue
        cpu_raw = row.get('cpu_millicores', '0m').strip()
        try:
            cpu_val = float(cpu_raw[:-1]) / 250 * 100 if cpu_raw.endswith('m') else float(cpu_raw)
        except ValueError:
            cpu_val = 0
        pod_first_cpu[short] = cpu_val

    # Stale pods: first seen at t=0 AND first CPU > 20%
    stale_pods = {p for p, t in pod_first_seen.items()
                  if t < 0.1 and pod_first_cpu.get(p, 0) > 20}
    if stale_pods:
        print(f"Filtering stale pods from previous run: {stale_pods}")

    for row in raw_rows:
        pod = row.get('pod', '').strip()
        if not pod or pod == 'pod':
            continue
        short = '-'.join(pod.split('-')[-2:])
        if short in stale_pods:
            continue
        cpu_raw = row.get('cpu_millicores', '0m').strip()
        try:
            cpu_val = float(cpu_raw[:-1]) / 250 * 100 if cpu_raw.endswith('m') else float(cpu_raw)
        except ValueError:
            cpu_val = 0
        ts = row.get('timestamp', '').strip()
        if ts and t0:
            try:
                elapsed = (datetime.fromisoformat(ts) - t0).total_seconds() / 60
            except ValueError:
                elapsed = pod_counters.get(short, 0) * INTERVAL
        else:
            elapsed = pod_counters.get(short, 0) * INTERVAL
        pod_data.setdefault(short, []).append(cpu_val)
        pod_times.setdefault(short, []).append(elapsed)
        pod_counters[short] = pod_counters.get(short, 0) + 1
    print(f"Pod CPU: {len(pod_data)} pods (after filtering stale)")
except FileNotFoundError:
    print("Warning: combined_pod_cpu.csv not found")

# HPA data
hpa_time, hpa_replicas, hpa_cpu = [], [], []
try:
    with open("results/combined_hpa.csv") as f:
        for idx, row in enumerate(csv.DictReader(f)):
            hpa_time.append(idx * INTERVAL)
            try:
                hpa_replicas.append(int(row['replicas']))
            except (ValueError, KeyError):
                hpa_replicas.append(hpa_replicas[-1] if hpa_replicas else 1)
            try:
                hpa_cpu.append(float(row['hpa_cpu_percent']))
            except (ValueError, KeyError):
                hpa_cpu.append(0)
    print(f"HPA: {len(hpa_time)} samples")
except FileNotFoundError:
    print("Warning: combined_hpa.csv not found")

# Phase response times
def parse_ab(filepath):
    mean = p50 = p95 = p99 = None
    try:
        with open(filepath) as f:
            for line in f:
                m = re.search(r'Time per request:\s+([\d.]+)\s+\[ms\]\s+\(mean\)', line)
                if m: mean = float(m.group(1))
                m = re.search(r'\s+50%\s+(\d+)', line)
                if m: p50 = float(m.group(1))
                m = re.search(r'\s+95%\s+(\d+)', line)
                if m: p95 = float(m.group(1))
                m = re.search(r'\s+99%\s+(\d+)', line)
                if m: p99 = float(m.group(1))
    except FileNotFoundError:
        pass
    return mean, p50, p95, p99

phase_rt = []
for i, (t_start, t_end, conc) in enumerate(PHASE_BOUNDS, 1):
    mean, p50, p95, p99 = parse_ab(f"results/combined_phase{i}.txt")
    if mean is not None:
        phase_rt.append({
            'mid': (t_start + t_end) / 2,
            'start': t_start, 'end': t_end,
            'conc': conc,
            'mean': mean, 'p50': p50, 'p95': p95, 'p99': p99
        })
        print(f"Phase {i} (c={conc}): mean={mean}ms p50={p50} p95={p95} p99={p99}")

# Benchmark Graph 1 data
def parse_ab_mean(path):
    mean, *_ = parse_ab(path)
    return mean

rates = [10, 25, 50, 100, 200]
g1_data = {}
for r in [1, 2, 3]:
    tms, vr = [], []
    for rate in rates:
        m = parse_ab_mean(f"results/run_r{r}_rps{rate}.txt")
        if m: tms.append(m); vr.append(rate)
    if tms: g1_data[r] = (vr, tms)

# ═══════════════════════════════════════════════════════════════════════════════
# GRAPHS
# ═══════════════════════════════════════════════════════════════════════════════

generated = []

# G1: Time vs Per-Pod CPU
if pod_data:
    fig, ax = plt.subplots(figsize=(13, 5))
    for i, (short, vals) in enumerate(sorted(pod_data.items())):
        ax.plot(pod_times[short], vals, marker='o', markersize=3,
                linewidth=1.8, color=pod_colors[i % len(pod_colors)],
                label=f'pod-{short}')
    ax.axhline(50, color='orange', linestyle='--', linewidth=1.5, label='HPA target (50%)')
    setup(ax, "Per-Pod CPU Utilization over Time", "Time (minutes)", "CPU (%)")
    ax.set_ylim(0)
    add_phase_shading(ax)
    ax.legend(fontsize=8, loc='upper right')
    save(fig, "G1_pod_cpu_vs_time"); generated.append("G1_pod_cpu_vs_time")

# G2: Time vs Active Pod Count (from pod_cpu data)
if pod_data:
    max_idx = max(max(range(len(v))) for v in pod_data.values())
    t_rep, v_rep = [], []
    for idx in range(max_idx + 1):
        t_rep.append(idx * INTERVAL)
        v_rep.append(sum(1 for v in pod_data.values() if idx < len(v)))

    fig, ax = plt.subplots(figsize=(13, 4))
    ax.step(t_rep, v_rep, where='post', color='#2ca02c', linewidth=2.5)
    ax.fill_between(t_rep, v_rep, step='post', alpha=0.15, color='#2ca02c')
    ax.set_ylim(0, max(v_rep) + 2)
    ax.set_yticks(range(0, max(v_rep) + 2))
    setup(ax, "Active Pod Count over Time ", "Time (minutes)", "Active Pods")
    add_phase_shading(ax)
    save(fig, "G2_active_pods_vs_time"); generated.append("G2_active_pods_vs_time")

# G3: Time vs HPA Replica Count
if hpa_time:
    fig, ax = plt.subplots(figsize=(13, 4))
    ax.step(hpa_time, hpa_replicas, where='post', color='#2ca02c', linewidth=2.5)
    ax.fill_between(hpa_time, hpa_replicas, step='post', alpha=0.15, color='#2ca02c')
    ax.axhline(5, color='red',  linestyle='--', alpha=0.6, label='Max (5)')
    ax.axhline(1, color='gray', linestyle='--', alpha=0.5, label='Min (1)')
    ax.set_ylim(0, 7); ax.set_yticks(range(0, 7))
    setup(ax, "HPA Replica Count over Time", "Time (minutes)", "Replicas")
    add_phase_shading(ax)
    ax.legend(fontsize=9)
    save(fig, "G3_hpa_replicas_vs_time"); generated.append("G3_hpa_replicas_vs_time")

# G4: Time vs HPA Aggregate CPU
if hpa_time:
    fig, ax = plt.subplots(figsize=(13, 4))
    ax.plot(hpa_time, hpa_cpu, color='#d62728', linewidth=2)
    ax.fill_between(hpa_time, hpa_cpu, alpha=0.1, color='#d62728')
    ax.axhline(50, color='orange', linestyle='--', linewidth=1.5, label='HPA target (50%)')
    setup(ax, "HPA Aggregate CPU Utilization over Time", "Time (minutes)", "Avg CPU %")
    ax.set_ylim(0)
    add_phase_shading(ax)
    ax.legend(fontsize=9)
    save(fig, "G4_hpa_cpu_vs_time"); generated.append("G4_hpa_cpu_vs_time")

# G5: Time vs Response Time (per phase)
if phase_rt:
    fig, ax = plt.subplots(figsize=(13, 5))
    mids  = [p['mid']  for p in phase_rt]
    means = [p['mean'] for p in phase_rt]
    p50s  = [p['p50']  for p in phase_rt if p['p50']]
    p95s  = [p['p95']  for p in phase_rt if p['p95']]
    p99s  = [p['p99']  for p in phase_rt if p['p99']]

    ax.plot(mids, means, 'o-',  color='#1f77b4', linewidth=2, markersize=9, label='Mean')
    if p50s: ax.plot(mids[:len(p50s)], p50s, 's--', color='#2ca02c', linewidth=1.8, markersize=7, label='p50')
    if p95s: ax.plot(mids[:len(p95s)], p95s, '^--', color='#ff7f0e', linewidth=1.8, markersize=7, label='p95')
    if p99s: ax.plot(mids[:len(p99s)], p99s, 'D--', color='#d62728', linewidth=1.8, markersize=7, label='p99')

    for p in phase_rt:
        ax.axvspan(p['start'], p['end'], alpha=0.06,
                   color='green' if p['conc'] == 20 else 'red')
        ax.annotate(f"c={p['conc']}\n{p['mean']:.0f}ms",
                    xy=(p['mid'], p['mean']),
                    xytext=(p['mid'], p['mean'] + max(means)*0.1),
                    ha='center', fontsize=9, color='#333333')

    setup(ax, "Response Time per Phase ",
          "Time (minutes)", "Response Time (ms)")
    ax.set_ylim(0); ax.set_xlim(0, 10)
    ax.legend(fontsize=9)
    save(fig, "G5_response_time_vs_time"); generated.append("G5_response_time_vs_time")

# G6: Time vs Concurrency
if hpa_time:
    conc_vals = []
    for t in hpa_time:
        for t_start, t_end, c in PHASE_BOUNDS:
            if t_start <= t < t_end:
                conc_vals.append(c); break
        else:
            conc_vals.append(20)

    fig, ax = plt.subplots(figsize=(13, 3.5))
    ax.step(hpa_time, conc_vals, where='post', color='#5b6abf', linewidth=2.5)
    ax.fill_between(hpa_time, conc_vals, step='post', alpha=0.15, color='#5b6abf')
    ax.set_yticks([20, 100]); ax.set_yticklabels(['20\n(low)', '100\n(high)'])
    setup(ax, "Concurrent Connections over Time (Test Phases)",
          "Time (minutes)", "Concurrency")
    add_phase_shading(ax)
    save(fig, "G6_concurrency_vs_time"); generated.append("G6_concurrency_vs_time")

# B1: Benchmark — Request Rate vs Response Time
if g1_data:
    clrs = ['#1f77b4', '#ff7f0e', '#2ca02c']
    fig, ax = plt.subplots(figsize=(13, 5))
    for i, r in enumerate([1, 2, 3]):
        if r in g1_data:
            vr, tm = g1_data[r]
            ax.plot(vr, tm, 'o-', linewidth=2, color=clrs[i], label=f'{r} replica(s)')
    setup(ax, "B1: Avg Response Time vs Request Rate (Load Distribution Benchmark)",
          "Request Rate (req/s)", "Avg Response Time (ms)")
    ax.legend(fontsize=9)
    save(fig, "B1_response_time_vs_rate"); generated.append("B1_response_time_vs_rate")

# ═══════════════════════════════════════════════════════════════════════════════
# COMBINED PDF
# ═══════════════════════════════════════════════════════════════════════════════
with PdfPages("results/all_graphs.pdf") as pdf:
    for name in generated:
        path = f"results/{name}.png"
        if os.path.exists(path):
            img = mpimg.imread(path)
            fig, ax = plt.subplots(figsize=(14, 5))
            ax.imshow(img); ax.axis('off')
            pdf.savefig(fig, bbox_inches='tight')
            plt.close(fig)

print(f"\nSaved results/all_graphs.pdf ({len(generated)} graphs)")
print("\nSummary of files:")
for name in generated:
    print(f"  {name}.png")
