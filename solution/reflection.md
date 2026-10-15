# Reflection (≤1 page)

### Which fault types were hardest to catch, and why?

1. **Subtle statistical shifts near normal variance (`tier=subtle`)**:
   - Subtle distribution shifts in `data_batch` (e.g., slight mean amount deviations or slight volume drops/spikes) and subtle embedding drift / corpus staleness in `embedding_batch`.
   - **Why**: The generator deliberately injects subtle faults that lie within 1.0–2.5σ of baseline clean distributions. Because `ctx.baseline` represents calibrated $\mu \pm 3\sigma$ bounds, single-event thresholding cannot safely distinguish these perturbations from clean natural sampling noise without triggering false alarms. Under the scoring penalty of $-0.3 \times \text{FPR}$ versus $+0.5 \times \text{TPR}$, even a handful of false positives rapidly erodes net score. Achieving 0% FPR required maintaining disciplined 3σ thresholds, which intentionally accepts missing subtle single-point anomalies.

2. **Lineage graph anomalies (`lineage_run`)**:
   - Missing upstream dependencies (e.g., missing `raw.customers` in `dbt:stg_orders`).
   - **Why**: Lineage payloads only declare immediate inputs in `inputs`, but downstream models perform joins that require multi-table dependencies. Recognizing that `dbt:stg_orders` requires both `raw.orders` and `raw.customers` requires knowing the expected DAG topology invariant rather than reading local payload fields.

---

### What would you change about your cost/coverage tradeoff, if you had another pass?

1. **Stateful sequential anomaly detection (CUSUM / EWMA / SPRT)**:
   - Rather than stateless per-event thresholding, leverage `ctx.state` across consecutive batches to track cumulative sum (CUSUM) or exponentially weighted moving averages. A subtle +1.0σ shift in `feature_materialization` or `data_batch` that is indistinguishable from noise on a single sample becomes statistically undeniable ($p < 0.001$) across 3–4 consecutive batches. This would catch subtle-tier faults while retaining a 0% FPR.

2. **Dynamic / Tiered Inspection Budgeting**:
   - In our current defense, we executed a single metered call per event, consuming 300.0 credits out of the 320.0 private budget (0% overage penalty). If given tighter budgets (e.g. 150–200 credits), we would implement conditional inspection: run cheap 1.0-credit checks (`batch_profile`, `lineage_graph_slice`) unconditionally, while conditionally sampling or gating expensive 2.0-credit tools (`feature_drift`, `embedding_drift`) based on event priority, payload metadata, or periodic cadence.
