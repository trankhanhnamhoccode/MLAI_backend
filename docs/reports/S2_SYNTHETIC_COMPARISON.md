# S2 model comparison -- SYNTHETIC, real quality NOT EVALUATED

Classification: CURRENT FACT for this reproducible mechanics report, no real-data
superiority/calibration claim. Generated 2026-10-07 by scripts.forecast_demo.synthetic_input:
Store UUID(int=1000), Products UUID(int=1001/1002), unit cup, Asia/Ho_Chi_Minh.
120 calendar days 2026-01-01..2026-04-30, 240 explicitly observed daily rows, no missing
or zero rows in this fixture. Quantity = 10 + 5*(day_index % 7) + floor(day_index/14)
+ 10*product_code. This intentionally simple calendar pattern is not representative
of real sales, inventory censoring or corrections.

Input fingerprint: `a1b54f6d6035efad2b33a1cf9d715a439612c8b8114a4c82f125f5adbc887a74`.
Fixed model/policy in ADR-015; no tuning. Five validation origins 2026-02-11..2026-03-11,
six later holdout origins 2026-03-18..2026-04-22, seven days apart. Paired observed
samples: 70 validation, 84 holdout (35/42 per Product). Missing targets=0, exclusions=0.
Selection LightGBM / VALIDATION_IMPROVEMENT comes only from validation mean pinball.
Final-fit artifact: `74f467112f3f9849e79b54e1eb05f0b84ca562352e1c1c32b4bc3b3d32241ae0`.

| Partition / family | n | MAE P50 | WAPE ratio | Mean pinball | Coverage [P25,P75] | Width | Raw/post crossings |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Validation LightGBM | 70 | 3.201456 | .094718 | 1.563283 | .400000 | 7.560960 | 16/0 |
| Validation baseline | 70 | 8.900000 | .263314 | 3.710714 | .571429 | 17.700000 | 0/0 |
| Holdout LightGBM | 84 | 3.340878 | .091531 | 1.620770 | .357143 | 8.051606 | 13/0 |
| Holdout baseline | 84 | 9.095238 | .249185 | 3.804563 | .523810 | 16.750000 | 0/0 |

Full precision individual P25/P50/P75 pinball, every horizon/Product/Product x horizon
and sample counts: [S2_SYNTHETIC_COMPARISON.json](S2_SYNTHETIC_COMPARISON.json).
Display rounding above has no selection/persistence effect. Nominal interval coverage
is .50; these small synthetic results do not establish calibration. Lower synthetic
loss is mechanics evidence only; **model better than baseline on real data: UNPROVEN**.
The final fitted artifact itself has no unseen real-data score.

Exact executed commands (repository-local venv, outputs in ignored runtime):

```powershell
.\.venv\Scripts\python.exe -m scripts.forecast_model synthetic --output runtime/s2_synthetic_input.json
.\.venv\Scripts\python.exe -m scripts.forecast_model backtest --input runtime/s2_synthetic_input.json --dataset-label SYNTHETIC --output runtime/s2_synthetic_comparison.json
.\.venv\Scripts\python.exe -m scripts.forecast_model train --input runtime/s2_synthetic_input.json --dataset-label SYNTHETIC --output runtime/s2_synthetic_artifact.json
.\.venv\Scripts\python.exe -m scripts.forecast_model infer --input runtime/s2_synthetic_input.json --artifact 74f467112f3f9849e79b54e1eb05f0b84ca562352e1c1c32b4bc3b3d32241ae0 --output runtime/s2_synthetic_predictions.json
```

These commands exited 0; they train/infer without DB access. Choose new output paths
to reproduce because overwrite is refused. No customer dataset exists in the repo.
To close quality: provide sufficiently long Store-local Product observed-sales history,
explicit zero/missing definitions, stable/captured units and correction availability
provenance; retain separate chronological validation/holdout, assess weak Products,
interval coverage/width and operating-relevant thresholds without holdout tuning.
