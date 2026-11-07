from pathlib import Path
import re, json, hashlib, math
root = Path(__file__).resolve().parents[2]
report = root / 'docs/20261105_검증자료_PDF반영_기술진단_보강보고서.md'
text = report.read_text(encoding='utf-8')
links = re.findall(r'\]\(([^)]+)\)', text)
missing = [p for p in links if not p.startswith('http') and not (report.parent / p).exists()]
ram = json.loads((Path(__file__).parent / 'ram_snapshot.json').read_text(encoding='utf-8-sig'))
result = {
 'report_sha256': hashlib.sha256(report.read_bytes()).hexdigest(),
 'missing_relative_links': missing,
 'target_correct': math.ceil(.7 * 5897),
 'gap_from_3497': math.ceil(.7 * 5897) - 3497,
 'seed42_delta': 4/5897,
 'two_seed_mean_delta': 2/5897,
 'pdf_current_rows_sum': sum([1592,681,209,832]),
 'pdf_target_rows_sum': sum([1800,928,506,932]),
 'pdf_delta_rows_sum': sum([208,247,297,100]),
 'actual_support_sum': sum([2920,2016,835,126]),
 'actual_seed42_correct': sum([2519,764,123,85]),
 'actual_seed2026_correct': sum([2537,757,124,85]),
 'ram_free_gib': ram['FreePhysicalMemory']/1048576,
 'ram_os_visible_gib': ram['TotalVisibleMemorySize']/1048576,
 'note': 'Document arithmetic/link validation only; no data, model, or metrics rerun.'
}
(Path(__file__).parent / 'document_checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
