"""
plot_all.py — 7 separate graphs saved as individual PNGs + one combined PDF

Fixed Load Experiment (profile_pods.sh):
  F1: Time vs Per-Pod CPU
  F2: Time vs Active Replicas
  F3: Time vs Avg CPU

HPA Autoscale Experiment (autoscale_test.sh):
  H1: Time vs Concurrency (request rate phases)
  H2: Time vs Replica Count
  H3: Time vs Avg CPU
  H4: Time vs Response Time (from phase ab output files)

Benchmark (load_distribution.sh):
  B1: Request Rate vs Response Time (3 replica configs) — Graph 1
"""

import os, re, csv
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

os.makedirs("results", exist_ok=True)

SAMPLE_INTERVAL = 15 / 60  # 15 seconds → minutes

pod_colors  = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
STYLE = dict(grid=True, grid_alpha=0.3, grid_ls='--')

def setup(ax, title, xlabel, ylabel):
    ax.set_title(title, fontsize=12, fontweight='bold')
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.grid(True, alpha=0.3, linestyle='--')

def save(fig, name):
    fig.tight_layout()
    fig.savefig(f"results/{name}.png", dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved results/{name}.png")

# ═══════════════════════════════════════════════════════════════════════════════
# LOAD DATA
# ═══════════════════════════════════════════════════════════════════════════════

# ── Fixed load: pod_cpu.csv ───────────────────────────────────────────────────
pod_data = {}       # short_name -> [cpu_val, ...]
pod_times = {}      # short_name -> [time_min, ...]
pod_counters = {}

try:
    with open("results/pod_cpu.csv") as f:
        for row in csv.DictReader(f):
            pod = row.get('pod', '').strip()
            if not pod or pod == 'pod':
                continue
            short = '-'.join(pod.split('-')[-2:])
            cpu_raw = row.get('cpu', '0m').strip()
            try:
                cpu_val = float(cpu_raw[:-1]) / 250 * 100 if cpu_raw.endswith('m') else float(cpu_raw)
            except ValueError:
                cpu_val = 0
            idx = pod_counters.get(short, 0)
            pod_data.setdefault(short, []).append(cpu_val)
            pod_times.setdefault(short, []).append(idx * SAMPLE_INTERVAL)
            pod_counters[short] = idx + 1
    print(f"Fixed load: {len(pod_data)} pods loaded")
except FileNotFoundError:
    print("Warning: results/pod_cpu.csv not found")

# ── HPA autoscale: hpa_autoscale.csv ─────────────────────────────────────────
hpa_time, hpa_replicas, hpa_cpu, hpa_rate = [], [], [], []

try:
    with open("results/hpa_autoscale.csv") as f:
        rows = list(csv.DictReader(f))
    for idx, row in enumerate(rows):
        hpa_time.append(idx * SAMPLE_INTERVAL)
        try:
            hpa_replicas.append(int(row['replicas']))
        except (ValueError, KeyError):
            hpa_replicas.append(hpa_replicas[-1] if hpa_replicas else 1)
        try:
            raw = row.get('cpu_target', '0').strip()
            m = re.search(r'(\d+)', raw)
            hpa_cpu.append(float(m.group(1)) if m else 0)
        except (ValueError, AttributeError):
            hpa_cpu.append(0)
        # phases: 2min=8samples @20c, 5min=20samples @100c, 3min=12samples @20c
        if idx < 8:
            hpa_rate.append(20)
        elif idx < 28:
            hpa_rate.append(100)
        else:
            hpa_rate.append(20)
    print(f"HPA data: {len(hpa_time)} samples loaded")
except FileNotFoundError:
    print("Warning: results/hpa_autoscale.csv not found")

# ── HPA phase response times from ab output files ────────────────────────────
# Each phase file has ONE summary → we assign it to the midpoint of that phase
phase_files = {
    1: ("results/autoscale_phase1.txt", 0,          8*SAMPLE_INTERVAL),   # 0–2 min
    2: ("results/autoscale_phase2.txt", 8*SAMPLE_INTERVAL,  28*SAMPLE_INTERVAL),  # 2–7 min
    3: ("results/autoscale_phase3.txt", 28*SAMPLE_INTERVAL, 41*SAMPLE_INTERVAL),  # 7–10 min
}

def parse_ab_full(filepath):
    """Return (mean_ms, p50_ms, p95_ms, p99_ms) or Nones."""
    mean_ms = p50 = p95 = p99 = None
    try:
        with open(filepath) as f:
            lines = f.readlines()
        for line in lines:
            m = re.search(r'Time per request:\s+([\d.]+)\s+\[ms\]\s+\(mean\)', line)
            if m:
                mean_ms = float(m.group(1))
            m = re.search(r'\s+50%\s+(\d+)', line)
            if m:
                p50 = float(m.group(1))
            m = re.search(r'\s+95%\s+(\d+)', line)
            if m:
                p95 = float(m.group(1))
            m = re.search(r'\s+99%\s+(\d+)', line)
            if m:
                p99 = float(m.group(1))
    except FileNotFoundError:
        pass
    return mean_ms, p50, p95, p99

phase_rt = {}  # phase_num -> {time_start, time_mid, time_end, mean, p50, p95, p99}
for ph, (fpath, t_start, t_end) in phase_files.items():
    mean, p50, p95, p99 = parse_ab_full(fpath)
    if mean is not None:
        phase_rt[ph] = {
            'time_start': t_start,
            'time_mid':   (t_start + t_end) / 2,
            'time_end':   t_end,
            'mean': mean, 'p50': p50, 'p95': p95, 'p99': p99
        }
        print(f"Phase {ph}: mean={mean}ms p50={p50}ms p95={p95}ms p99={p99}ms")

# ── Graph 1 benchmark data ────────────────────────────────────────────────────
rates = [10, 25, 50, 100, 200]
replica_configs = [1, 2, 3]
g1_data = {}
for r in replica_configs:
    times, valid_rates = [], []
    for rate in rates:
        path = f"results/run_r{r}_rps{rate}.txt"
        mean, *_ = parse_ab_full(path)
        if mean is not None:
            times.append(mean)
            valid_rates.append(rate)
    if times:
        g1_data[r] = (valid_rates, times)

# ═══════════════════════════════════════════════════════════════════════════════
# FIXED LOAD GRAPHS
# ═══════════════════════════════════════════════════════════════════════════════

# F1: Time vs Per-Pod CPU
if pod_data:
    fig, ax = plt.subplots(figsize=(12, 5))
    for i, (short, vals) in enumerate(sorted(pod_data.items())):
        ax.plot(pod_times[short], vals, marker='o', markersize=4,
                linewidth=1.8, color=pod_colors[i % len(pod_colors)],
                label=f'pod-{short}')
    ax.axhline(y=50, color='orange', linestyle='--', linewidth=1.5, label='HPA target (50%)')
    setup(ax, "F1: Per-Pod CPU Utilization over Time\n(Fixed Load — 100 concurrent, started at 3 replicas)",
          "Time (minutes)", "CPU Utilization (%)")
    ax.set_ylim(0)
    ax.legend(fontsize=9)
    save(fig, "F1_pod_cpu_vs_time")

# F2: Time vs Active Replica Count (count unique pods visible at each sample)
if pod_data:
    # Build timeline: at each sample index, how many pods are visible?
    max_idx = max(max(range(len(v))) for v in pod_data.values())
    replica_at_sample = []
    time_at_sample = []
    for idx in range(max_idx + 1):
        count = sum(1 for v in pod_data.values() if idx < len(v))
        replica_at_sample.append(count)
        time_at_sample.append(idx * SAMPLE_INTERVAL)

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.step(time_at_sample, replica_at_sample, where='post',
            color='#2ca02c', linewidth=2.5)
    ax.fill_between(time_at_sample, replica_at_sample, step='post',
                    alpha=0.15, color='#2ca02c')
    ax.set_ylim(0, max(replica_at_sample) + 1)
    ax.set_yticks(range(1, max(replica_at_sample) + 2))
    setup(ax, "F2: Active Pod Count over Time\n(Fixed Load — HPA scaled during run)",
          "Time (minutes)", "Active Pods")
    save(fig, "F2_replicas_vs_time_fixed")

# F3: Time vs Avg CPU (averaged across all active pods each sample)
if pod_data:
    max_idx = max(max(range(len(v))) for v in pod_data.values())
    avg_cpu_time, avg_cpu_vals = [], []
    for idx in range(max_idx + 1):
        vals_at = [v[idx] for v in pod_data.values() if idx < len(v)]
        if vals_at:
            avg_cpu_time.append(idx * SAMPLE_INTERVAL)
            avg_cpu_vals.append(sum(vals_at) / len(vals_at))

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(avg_cpu_time, avg_cpu_vals, color='#d62728', linewidth=2)
    ax.fill_between(avg_cpu_time, avg_cpu_vals, alpha=0.1, color='#d62728')
    ax.axhline(y=50, color='orange', linestyle='--', linewidth=1.5, label='HPA target (50%)')
    setup(ax, "F3: Average CPU Utilization over Time\n(Fixed Load — averaged across all active pods)",
          "Time (minutes)", "Avg CPU (%)")
    ax.set_ylim(0)
    ax.legend(fontsize=9)
    save(fig, "F3_avg_cpu_vs_time_fixed")

# ═══════════════════════════════════════════════════════════════════════════════
# HPA AUTOSCALE GRAPHS
# ═══════════════════════════════════════════════════════════════════════════════

# H1: Time vs Concurrency (request rate phases)
if hpa_time:
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.step(hpa_time, hpa_rate, where='post', color='#5b6abf', linewidth=2.5)
    ax.fill_between(hpa_time, hpa_rate, step='post', alpha=0.15, color='#5b6abf')
    # shade phases
    ax.axvspan(0,              8*SAMPLE_INTERVAL,  alpha=0.07, color='green', label='Baseline (2 min)')
    ax.axvspan(8*SAMPLE_INTERVAL,  28*SAMPLE_INTERVAL, alpha=0.07, color='red',   label='High Load (5 min)')
    ax.axvspan(28*SAMPLE_INTERVAL, hpa_time[-1],        alpha=0.07, color='green', label='Cooldown (3 min)')
    ax.set_yticks([20, 100])
    ax.set_yticklabels(['20\n(low)', '100\n(high)'])
    setup(ax, "H1: Concurrent Connections over Time\n(HPA Autoscale Test — 10 minutes)",
          "Time (minutes)", "Concurrency")
    ax.legend(fontsize=9)
    save(fig, "H1_concurrency_vs_time_hpa")

# H2: Time vs Replica Count
if hpa_time:
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.step(hpa_time, hpa_replicas, where='post', color='#2ca02c', linewidth=2.5)
    ax.fill_between(hpa_time, hpa_replicas, step='post', alpha=0.15, color='#2ca02c')
    ax.axhline(y=5, color='red',  linestyle='--', alpha=0.6, label='Max replicas (5)')
    ax.axhline(y=1, color='gray', linestyle='--', alpha=0.5, label='Min replicas (1)')
    ax.set_ylim(0, 7)
    ax.set_yticks(range(0, 7))
    setup(ax, "H2: HPA Replica Count over Time\n(HPA Autoscale Test — 10 minutes)",
          "Time (minutes)", "Replicas")
    ax.legend(fontsize=9)
    save(fig, "H2_replicas_vs_time_hpa")

# H3: Time vs Avg CPU
if hpa_time:
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(hpa_time, hpa_cpu, color='#d62728', linewidth=2)
    ax.fill_between(hpa_time, hpa_cpu, alpha=0.1, color='#d62728')
    ax.axhline(y=50, color='orange', linestyle='--', linewidth=1.5, label='HPA target (50%)')
    setup(ax, "H3: Average CPU Utilization over Time\n(HPA Autoscale Test — HPA aggregate metric)",
          "Time (minutes)", "Avg CPU %")
    ax.set_ylim(0)
    ax.legend(fontsize=9)
    save(fig, "H3_cpu_vs_time_hpa")

# H4: Time vs Response Time (from ab phase files — 3 data points)
if phase_rt:
    fig, ax = plt.subplots(figsize=(12, 5))
    phase_labels = {1: 'Baseline\n(c=20)', 2: 'High Load\n(c=100)', 3: 'Cooldown\n(c=20)'}
    phase_colors = {1: '#2ca02c', 2: '#d62728', 3: '#1f77b4'}

    mids   = [phase_rt[ph]['time_mid']   for ph in sorted(phase_rt)]
    means  = [phase_rt[ph]['mean']        for ph in sorted(phase_rt)]
    p50s   = [phase_rt[ph]['p50']         for ph in sorted(phase_rt) if phase_rt[ph]['p50']]
    p95s   = [phase_rt[ph]['p95']         for ph in sorted(phase_rt) if phase_rt[ph]['p95']]
    p99s   = [phase_rt[ph]['p99']         for ph in sorted(phase_rt) if phase_rt[ph]['p99']]

    ax.plot(mids, means, 'o-', color='#1f77b4', linewidth=2, markersize=8, label='Mean')
    if p50s:
        ax.plot(mids[:len(p50s)], p50s, 's--', color='#2ca02c', linewidth=1.5, markersize=7, label='p50 (median)')
    if p95s:
        ax.plot(mids[:len(p95s)], p95s, '^--', color='#ff7f0e', linewidth=1.5, markersize=7, label='p95')
    if p99s:
        ax.plot(mids[:len(p99s)], p99s, 'D--', color='#d62728', linewidth=1.5, markersize=7, label='p99')

    # shade phases
    for ph in sorted(phase_rt):
        d = phase_rt[ph]
        color = list(phase_colors.values())[ph-1]
        ax.axvspan(d['time_start'], d['time_end'], alpha=0.06, color=color)
        ax.text(d['time_mid'], ax.get_ylim()[1] if ax.get_ylim()[1] > 0 else 100,
                phase_labels[ph], ha='center', va='top', fontsize=8, color='gray')

    setup(ax, "H4: Response Time over Time\n(HPA Autoscale Test — per phase: mean, p50, p95, p99)",
          "Time (minutes)", "Response Time (ms)")
    ax.set_ylim(0)
    ax.legend(fontsize=9)
    save(fig, "H4_response_time_vs_time_hpa")

# ═══════════════════════════════════════════════════════════════════════════════
# BENCHMARK: Request Rate vs Response Time  (Graph 1)
# ═══════════════════════════════════════════════════════════════════════════════
if g1_data:
    replica_clr = ['#1f77b4', '#ff7f0e', '#2ca02c']
    fig, ax = plt.subplots(figsize=(12, 5))
    for i, r in enumerate(replica_configs):
        if r in g1_data:
            vr, tm = g1_data[r]
            ax.plot(vr, tm, marker='o', linewidth=2,
                    color=replica_clr[i], label=f'{r} replica(s)')
    setup(ax, "B1: Avg Response Time vs Request Rate\n(Load Distribution Benchmark — 1/2/3 replicas)",
          "Request Rate (req/s)", "Avg Response Time (ms)")
    ax.legend(fontsize=9)
    save(fig, "B1_response_time_vs_rate")

# ═══════════════════════════════════════════════════════════════════════════════
# COMBINED PDF — all graphs stacked
# ═══════════════════════════════════════════════════════════════════════════════
sections = []
if g1_data:       sections.append("B1_response_time_vs_rate")
if pod_data:      sections += ["F1_pod_cpu_vs_time", "F2_replicas_vs_time_fixed", "F3_avg_cpu_vs_time_fixed"]
if hpa_time:      sections += ["H1_concurrency_vs_time_hpa", "H2_replicas_vs_time_hpa", "H3_cpu_vs_time_hpa"]
if phase_rt:      sections.append("H4_response_time_vs_time_hpa")

from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.image as mpimg

with PdfPages("results/all_graphs.pdf") as pdf:
    for name in sections:
        path = f"results/{name}.png"
        if os.path.exists(path):
            img = mpimg.imread(path)
            fig, ax = plt.subplots(figsize=(14, 5))
            ax.imshow(img)
            ax.axis('off')
            pdf.savefig(fig, bbox_inches='tight')
            plt.close(fig)

print("Saved results/all_graphs.pdf")
print("\nAll done. Files in results/:")
for name in sections:
    print(f"  {name}.png")
print("  all_graphs.pdf")
