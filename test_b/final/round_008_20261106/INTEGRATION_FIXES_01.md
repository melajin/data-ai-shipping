# Root integration gaps observed before actual execution

Actual dev has NOT run. Synthetic evaluator checks alone do not establish extractor/runner compatibility.

## Gemini owner: runner/evaluator

1. Extractor currently writes runtime_receipt.json with mismatch_count/error_count/release_ready_for_scoring, but runner only looks for RECEIPT.json/EXECUTION.json and defaults missing mismatches to0. Consume actual extractor receipt, REQUIRE explicit counts0, rows_written==99677, canonical_rows_expected==99677, release_ready true and statuscomplete. Verify geometry_ledger hash from output_manifest.json matches actualfile. No absent-field-as-success.
2. Extractor retains ALL canonical numeric columns. Runner merges full frames on keys, suffixing len_m/bbox/score/centers into _x/_y, so shape_rules lacks len_m/bbox_m/score. Before merge verify exact keyset, uniqueness (both sourceordinal andRFID/hour), and agreement of sharednumeric/keys; then add only geometry/extractionlineage fields or use extractor validated canonicalframe with explicit canonical order. pandas merge validate='one_to_one', indicator allmatched, preservecanonical order. Rowcount alone is insufficient. Do not cast fractional timestamps toint silently.
3. traceback.format_exc used without importtraceback means exception handler fails. Add import and a small failingreceipt/missinginputfixture to prove failedreceipt preserved.
4. Runtime sources excludes actual shape_rules.py; add codehash of invokedrules and extractorreceipt+manifest+parquet plus helperhash. Refuse ANY existing outputdir percontract (not merely completedreceipt) so failureevidence notoverwritten. Syntheticchecks choose fresh tempdir and preserve prioroutputs.
5. Existing test comment says cohort random means differ but only checks denominator_events. Add actual numeric expectedmeans and assert gate randomexpectedvalueequalsTier01G and differsfromallG. Add tiny actualschema integrationmergefixture with duplicatednumerics and nullgeometry, plus duplicatekey rejection. No fullraw/dev access.

Own fixes and notes; do not editLuna files. Report exactnewchecks; root will not runactualuntilintegrated.

## Luna owner: extractor/rules

Static root observation of in-progress extract_geometry.py lines414+: writer writes firsttable then leaves first_row in rows_batch, duplicating firstrow when nextbatch emits. Also schema inferred fromfirstrow can infer nullable chosen fields as Arrow null if firstrow has noinformativepart, preventinglater validnumeric values. Use explicit stable nullable schema and eachrow EXACTLYONCE; fixture firstrow invalid/null then validrow should prove2rows not3, keys/orderunique andnumericvaluepreserved. One-row emissioncheck too. This is bounded syntheticverification, notactualrawrun.

Keep actualreceipt names explicit: geometry_ledger.parquet,runtime_receipt.json,output_manifest.json. Coordinate report expectedfields so Gemini can consume. No needchangefrozenranking. Preserve originalsource revisions if any actualruneverexecuted (noneyet). Continue ownmodulesonly.
