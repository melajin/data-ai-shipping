# Time key interface clarification — source clock, no timezone conversion

Luna asked msg_0f83c88685c7 whether raw date/hour are UTC. Root inspected actual upstream source instead of assigning a timezone.

`29-30일 모델 심층 분석/분석 결과/tools/run_remeasure_20261031.py` lines699–701 defines:

```python
dt64 = pd.to_datetime(pd.Series(part_dt).astype(str), format="%Y%m%d")
return dt64.values.astype("datetime64[h]").astype(np.int64) + rfid_time.astype(np.int64)
```

Archived `round_008_linkage_audit_20261105/rescore_evaluate.py` lines73–74 calls that function. Round8 MUST reproduce that timezone-naive source-clock hour index. Do not localize or convert to/from UTC/KST. Epoch-hour is the numeric representation of source date/hour, not proof of actual timezone. The actual timezone remains unconfirmed. Validate exact date, integer hour0..23, cache raw date/hour, RFID and canonical ts independently. This clarification preserves existing timestamps and event evaluation; it does not shift records.
