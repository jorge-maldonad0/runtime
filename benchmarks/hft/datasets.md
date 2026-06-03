# HFT Benchmark Datasets

## Overview
Synthetic limit order book (LOB) dataset generated via a Hawkes process arrival
model with a book-state machine. Three seeds produce independent, reproducible
1B-event datasets.

## Fields

| Field | Type | Unit | Description |
|---|---|---|---|
| ts_ns | int64 | nanoseconds | Event timestamp from Hawkes arrival process |
| symbol_id | int32 | - | Synthetic symbol index (0–99) |
| side | int8 | - | 0 = bid, 1 = ask |
| price | int64 | ticks | Mid-price random walk ± 1 tick per trade |
| size | int32 | lots | Order size, uniform [1, 1000] |
| type | int8 | - | 0 = add, 1 = cancel, 2 = trade |

## Hawkes Process Parameters

| Parameter | Value | Description |
|---|---|---|
| mu | 100.0 | Baseline arrival rate (events/sec) |
| alpha | 0.6 | Excitation magnitude per event |
| beta | 0.8 | Decay rate |

## Seed Protocol
- Seeds {42, 43, 44} produce independent, byte-for-byte reproducible datasets
- Same seed + same binary = identical output
- Seeds are passed as CLI argument: `hft_gen <n_events> <seed> <out_path>`

## Storage Format
- Parquet, row-group size 500,000 rows (~128 MiB uncompressed)
- Compression: zstd level 1
- Location: `$GITM_DATA_ROOT/datasets/hft/hft_1b_seed{42,43,44}/part0.parquet`

## Scale
- 1,000,000,000 events per seed
- ~7.3 GB compressed per seed
- ~22 GB total across 3 seeds

## Generation
```bash
cd benchmarks/hft/generator/build
./hft_gen 1000000000 42 $GITM_DATA_ROOT/datasets/hft/hft_1b_seed42/part0.parquet
./hft_gen 1000000000 43 $GITM_DATA_ROOT/datasets/hft/hft_1b_seed43/part0.parquet
./hft_gen 1000000000 44 $GITM_DATA_ROOT/datasets/hft/hft_1b_seed44/part0.parquet
```
