"""Check the textbook's local navigation and document structure.

This checks documents, not a learner's mastery or real hardware behavior.
Run from any directory with: python path/to/check_book.py
"""

from pathlib import Path
import json
import re
from urllib.parse import unquote, urlsplit

BOOK = Path(__file__).resolve().parent.parent
CHAPTERS = [
    "01_problem_data", "02_math", "03_probability", "04_computing",
    "05_symbolic", "06_statistical_learning", "07_probabilistic_models",
    "08_neural_networks", "09_learning_paradigms", "10_generative",
    "11_reinforcement_control", "12_language_models", "13_multimodal",
    "14_structured_domains", "15_causality", "16_alternative_scientific",
    "17_systems", "18_evaluation",
    "19_fishing_data_geometry", "20_fishing_classification",
    "21_fishing_sequence_models", "22_fishing_anomaly",
    "23_fishing_environment", "24_fishing_virtual_units",
    "25_fishing_evaluation_system",
]
EXPECTED = ["모델 해석 목차.md", "90_solutions.md", "91_model_cases.md",
            "92_sources.md", "93_glossary.md", "94_fishing_solutions.md",
            "95_fishing_guide.md"]
EXPECTED += [f"chapters/{name}.md" for name in CHAPTERS]


def prose_only(text):
    lines, fence = [], None
    for line in text.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)[0]
            fence = token if fence is None else (None if token == fence else fence)
            continue
        if fence is None:
            lines.append(line)
    return "\n".join(lines), fence


def anchors(text):
    result, seen = set(), {}
    prose, _ = prose_only(text)
    for line in prose.splitlines():
        m = re.match(r"^#{1,6}\s+(.+?)(?:\s+#+)?$", line)
        if not m:
            continue
        title = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", m.group(1))
        title = re.sub(r"<[^>]+>", "", title)
        base = re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")
        count = seen.get(base, 0)
        seen[base] = count + 1
        result.add(base if count == 0 else f"{base}-{count}")
    return result


def main():
    errors, warnings, stats = [], [], []
    for rel in EXPECTED:
        if not (BOOK / rel).is_file():
            errors.append(f"Missing document: {rel}")
    texts = {}
    for path in BOOK.rglob("*.md"):
        try:
            texts[path.resolve()] = path.read_text(encoding="utf-8-sig")
        except UnicodeError as exc:
            errors.append(f"UTF-8 decoding failed: {path.relative_to(BOOK)}: {exc}")
    for path, text in texts.items():
        rel = str(path.relative_to(BOOK)).replace("\\", "/")
        prose, open_fence = prose_only(text)
        if open_fence:
            errors.append(f"Unclosed code fence: {rel}")
        if "\ufffd" in text:
            errors.append(f"Unicode replacement character: {rel}")
        if "最적화" in text:
            errors.append(f"Known mixed-script typo: {rel}")
        # A mathematical operator such as [R F(v)](x) is not a Markdown link.
        link_prose = re.sub(r"\$\$[\s\S]*?\$\$|(?<!\\)\$(?!\$)(?:\\.|[^$\\])*?(?<!\\)\$", "", prose)
        link_prose = re.sub(r"\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]", "", link_prose)
        link_prose = re.sub(r"`[^`\n]*`", "", link_prose)
        for m in re.finditer(r"(?<!!)\[[^\]\n]+\]\((<[^>]+>|[^)\s]+)(?:\s+\"[^\"]*\")?\)", link_prose):
            target = m.group(1).strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc:
                continue
            local = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
            if not local.exists() and local != (BOOK / "validation" / "structure_report.json").resolve():
                errors.append(f"Broken local link: {rel} -> {target}")
                continue
            if parsed.fragment and local.suffix == ".md":
                target_text = texts.get(local)
                if target_text is None:
                    target_text = local.read_text(encoding="utf-8-sig")
                if unquote(parsed.fragment).lower() not in anchors(target_text):
                    warnings.append(f"Check anchor: {rel} -> {target}")
        if path.parent.name == "chapters":
            number = int(path.name[:2])
            expected_ids = [f"M{number:02d}-Q{i}" for i in range(1, 4)]
            absent = [qid for qid in expected_ids if qid not in text]
            if absent:
                errors.append(f"Missing exercise IDs: {rel}: {absent}")
            if len(text) < 3000:
                warnings.append(f"Short chapter, review teaching depth: {rel}")
            stats.append({"chapter": rel, "characters": len(text),
                          "lines": len(text.splitlines()),
                          "headings": len(re.findall(r"^#{1,6} ", prose, re.M))})
    general_solutions = texts.get((BOOK / "90_solutions.md").resolve(), "")
    fishing_solutions = texts.get((BOOK / "94_fishing_solutions.md").resolve(), "")
    for number in (int(name[:2]) for name in CHAPTERS):
        solutions = general_solutions if number <= 18 else fishing_solutions
        for q in range(1, 4):
            qid = f"M{number:02d}-Q{q}"
            if qid not in solutions:
                errors.append(f"Missing solution: {qid}")
    report = {"scope": "Local document structure and navigation; no external URL or content proof",
              "markdown_documents": len(texts), "chapters": sorted(stats, key=lambda x: x["chapter"]),
              "errors": errors, "warnings": warnings}
    out = BOOK / "validation" / "structure_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"markdown_documents": len(texts), "chapters": len(stats),
                      "errors": errors, "warnings": warnings,
                      "report": str(out)}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
