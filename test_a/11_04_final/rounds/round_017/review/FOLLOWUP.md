# Round017 follow-up

The one allowed `smoke_01` attempt is consumed by its preserved execution claim. Do not retry or reuse that run ID/map. In a fresh, separately planned model-zero repair attempt:

1. Make the minimal PowerShell correction in `Save-WrapperReceipt`: change the bareword `claimed=true` to `claimed=$true`. Keep the prior frozen files unchanged; create a new source freeze, manifest, ACK, and independent approval map.
2. Independently check the frozen hashes, then run one same-map smoke → mock → saved-audit sequence. Before advancing modes, require the wrapper receipt to be completed, the Python mode receipt to be completed, the outer OS exit to be `0`, and the approved map hash to match. Stop and preserve evidence on any failure; no retry.
3. Keep model execution, checkpoint access, `.pt` deserialization, actual data, F1, and hardware at zero for this repair attempt. The Round018 full-estimator M4-a gate remains closed until a future source-approved model-zero sequence completes successfully and a new plan sets current RAM, peak estimate, and time cap.

The failed smoke is a PowerShell command-expression issue. The preceding parser check returned zero errors because `true` is a valid command-shaped token in that context; static syntax acceptance did not establish execution success.
