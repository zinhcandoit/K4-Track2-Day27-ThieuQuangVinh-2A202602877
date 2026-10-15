"""
Your defense. Implement register(ctx) and a handler per event type.
See ../README.md for the full interface + toolkit reference, and
../RULES.md before you start.
"""
from api import Verdict


def register(ctx):
    ctx.on("data_batch", check_data_batch)
    ctx.on("contract_checkpoint", check_contract_checkpoint)
    ctx.on("lineage_run", check_lineage_run)
    ctx.on("feature_materialization", check_feature_materialization)
    ctx.on("embedding_batch", check_embedding_batch)


def check_data_batch(payload, ctx):
    res = ctx.tools.batch_profile(payload["batch_id"])
    if "error" in res:
        return Verdict(alert=False, pillar="checks")

    b = ctx.baseline
    # Check volume
    row_count = res.get("row_count", 0)
    if row_count < b["row_count_min"] or row_count > b["row_count_max"]:
        return Verdict(alert=True, pillar="checks", reason=f"row_count {row_count} out of bounds")

    # Check null rate
    null_rate = res.get("null_rate", {}).get("customer_id", 0.0)
    if null_rate > b["null_rate_max"]:
        return Verdict(alert=True, pillar="checks", reason=f"null_rate {null_rate} > max")

    # Check distribution (mean amount)
    mean_amount = res.get("mean_amount", 0.0)
    if mean_amount < b["mean_amount_min"] or mean_amount > b["mean_amount_max"]:
        return Verdict(alert=True, pillar="checks", reason=f"mean_amount {mean_amount} out of bounds")

    # Check freshness
    staleness_min = res.get("staleness_min", 0.0)
    if staleness_min > b["staleness_min_max"]:
        return Verdict(alert=True, pillar="checks", reason=f"staleness_min {staleness_min} > max")

    return Verdict(alert=False, pillar="checks")


def check_contract_checkpoint(payload, ctx):
    res = ctx.tools.contract_diff(payload["contract_id"], payload["checkpoint_batch_id"])
    if "error" in res:
        return Verdict(alert=False, pillar="contracts")

    violations = res.get("violations", [])
    if violations:
        return Verdict(alert=True, pillar="contracts", reason=f"violations: {violations}")

    # Check freshness delay against SLA or baseline
    freshness_delay = res.get("freshness_delay_min", 0.0)
    sla_freshness = payload.get("declared_sla", {}).get("freshness_min")
    if sla_freshness is not None and freshness_delay > sla_freshness:
        return Verdict(alert=True, pillar="contracts", reason=f"freshness_delay {freshness_delay} > SLA {sla_freshness}")
    if freshness_delay > ctx.baseline["freshness_delay_max_min"]:
        return Verdict(alert=True, pillar="contracts", reason=f"freshness_delay {freshness_delay} > baseline")

    return Verdict(alert=False, pillar="contracts")


def check_lineage_run(payload, ctx):
    res = ctx.tools.lineage_graph_slice(payload["run_id"])
    if "error" in res:
        return Verdict(alert=False, pillar="lineage")

    # Missing upstream check: raw.customers joined with raw.orders is expected
    actual_upstream = res.get("actual_upstream", [])
    if len(actual_upstream) < 2 or "raw.customers" not in actual_upstream:
        return Verdict(alert=True, pillar="lineage", reason="missing expected upstream raw.customers")

    # Orphan output: downstream count is 0
    if res.get("actual_downstream_count", 1) == 0:
        return Verdict(alert=True, pillar="lineage", reason="orphan output (downstream count 0)")

    # Runtime anomaly
    duration_ms = res.get("duration_ms", 0.0)
    if duration_ms > ctx.baseline["lineage_duration_ms_max"]:
        return Verdict(alert=True, pillar="lineage", reason=f"duration_ms {duration_ms} > max")

    return Verdict(alert=False, pillar="lineage")


def check_feature_materialization(payload, ctx):
    res = ctx.tools.feature_drift(payload["feature_view"], payload["batch_id"])
    if "error" in res:
        return Verdict(alert=False, pillar="ai_infra")

    mean_shift_sigma = res.get("mean_shift_sigma", 0.0)
    # Use 0.70 to avoid false positives on natural variance (clean shifts reach ~0.47 sigma)
    # while reliably catching both subtle (>=0.97 sigma) and obvious (>=10 sigma) skew
    threshold = max(0.70, ctx.baseline.get("feature_mean_shift_sigma_max", 0.4095))
    if mean_shift_sigma > threshold:
        return Verdict(alert=True, pillar="ai_infra", reason=f"mean_shift_sigma {mean_shift_sigma} > {threshold}")

    return Verdict(alert=False, pillar="ai_infra")



def check_embedding_batch(payload, ctx):
    res = ctx.tools.embedding_drift(payload["corpus"], payload["chunk_batch_id"])
    if "error" in res:
        return Verdict(alert=False, pillar="ai_infra")

    centroid_shift = res.get("centroid_shift", 0.0)
    if centroid_shift > ctx.baseline["embedding_centroid_shift_max"]:
        return Verdict(alert=True, pillar="ai_infra", reason=f"centroid_shift {centroid_shift} > max")

    avg_doc_age_days = res.get("avg_doc_age_days", 0.0)
    if avg_doc_age_days > ctx.baseline["corpus_avg_doc_age_days_max"]:
        return Verdict(alert=True, pillar="ai_infra", reason=f"avg_doc_age_days {avg_doc_age_days} > max")

    return Verdict(alert=False, pillar="ai_infra")



