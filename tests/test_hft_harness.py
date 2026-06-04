"""Tests for the HFT LOB harness pipeline (cuDF/CuPy on GPU; pandas fallback here).

The pipeline stages are backend-agnostic, so they are validated on pandas with
hand-computed expectations. The GPU path runs the identical code on cuDF.
"""

from __future__ import annotations

import json

import pytest

pd = pytest.importorskip("pandas", reason="pandas (bench extra) not installed")

from benchmarks.hft import harness  # noqa: E402


def _frame(rows):
    cols = ["ts_ns", "symbol_id", "side", "price", "size", "type"]
    return pd.DataFrame(rows, columns=cols)


def test_select_backend():
    kind, dflib, xp = harness.select_backend()
    # On a CPU box (no cuDF) we expect the pandas fallback; on a GPU box with
    # cuDF installed the harness correctly selects the GPU backend instead.
    try:
        import cudf  # noqa: F401

        assert kind == "gpu"
    except Exception:
        assert kind == "cpu"
        assert dflib is pd


def test_top_of_book_running_best_and_ffill():
    df = _frame([
        [1, 0, 0, 100, 10, 0],  # bid 100
        [2, 0, 1, 105, 5, 0],   # ask 105
        [3, 0, 0, 102, 8, 0],   # bid 102 (raises best bid)
        [4, 0, 1, 104, 6, 2],   # ask 104 (lowers best ask), trade
    ])
    out = harness.top_of_book(df, pd)
    assert list(out["best_bid"]) == [100, 100, 102, 102]
    # best_ask: NaN until first ask, then running min, ffilled
    bb = out["best_ask"].tolist()
    assert pd.isna(bb[0])
    assert bb[1:] == [105, 105, 104]


def test_microprice_size_weighted_formula():
    df = _frame([
        [1, 0, 0, 100, 10, 0],
        [2, 0, 1, 105, 5, 0],
        [3, 0, 0, 102, 8, 0],
    ])
    out = harness.top_of_book(df, pd)
    mp = harness.microprice(out)
    # row3: side=bid, bid_sz=8, ask_sz=0 -> mp = best_ask = 105
    assert mp.iloc[2] == pytest.approx(105.0)


def test_vwap_1s_tumbling_buckets():
    # two trades for symbol 0 in the same 1s bucket (ts < 1e9 ns)
    df = _frame([
        [10, 0, 1, 104, 6, 2],
        [20, 0, 0, 106, 4, 2],
        [1_000_000_010, 0, 1, 200, 1, 2],  # next 1s bucket
    ])
    out = harness.top_of_book(df, pd)
    vwap = harness.vwap_1s(out, pd)
    assert len(vwap) == 2  # two buckets
    # bucket 0 weighted: (104*6 + 106*4) / (6+4) = 104.8
    v = vwap.reset_index()
    bucket0 = v[v["_bucket"] == 0]["vwap"].iloc[0]
    assert bucket0 == pytest.approx(104.8)


def test_vwap_1s_empty_when_no_trades():
    df = _frame([[1, 0, 0, 100, 10, 0], [2, 0, 1, 105, 5, 0]])
    out = harness.top_of_book(df, pd)
    assert len(harness.vwap_1s(out, pd)) == 0


def test_run_pipeline_summary():
    df = _frame([
        [1, 0, 0, 100, 10, 0],
        [2, 0, 1, 105, 5, 2],
        [3, 1, 0, 50, 7, 0],
        [4, 1, 1, 55, 3, 2],
    ])
    summary = harness.run_pipeline(df, pd)
    assert summary["events"] == 4
    assert summary["vwap_buckets"] == 2  # one trade per symbol, same bucket


def test_harness_main_emits_contract(tmp_path, capsys, monkeypatch):
    from benchmarks.hft.generate import GenConfig, generate

    stage = tmp_path / "stage"
    generate(GenConfig(events=5_000, seed=42, events_per_file=5_000), stage / "hft_x_seed42")
    monkeypatch.setenv("GITM_BENCH_STAGE", str(stage))

    rc = harness.main(["--seed", "42", "--warm-seconds", "60"])
    assert rc == 0

    out = capsys.readouterr().out.strip().splitlines()
    payload = json.loads(out[-1])
    assert payload["metric_value"] > 0
    assert payload["gpu_name"]  # "cpu" on a CPU box, the GPU name on a GPU box
    assert payload["harness_commit"] == "cudf-lob-v1"


def test_harness_missing_seed_data_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("GITM_BENCH_STAGE", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        harness.main(["--seed", "99"])
