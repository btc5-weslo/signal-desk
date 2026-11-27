import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "audits"))
import no_price_scan as s


def _write(tmp, rel, text):
    p = tmp / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text); return p


def test_inline_marker_ignored_in_product_code(tmp_path):
    _write(tmp_path, "app/page.tsx", 'const x = "See pricing"; // qa-allow-price: nope\n')
    assert s.main([str(tmp_path)], allow={}) == 1


def test_inline_marker_needs_reason_even_in_tests(tmp_path):
    _write(tmp_path, "tests/a.test.ts", '"See pricing", // qa-allow-price\n')
    assert s.main([str(tmp_path)], allow={}) == 1
    _write(tmp_path, "tests/a.test.ts", '"See pricing", // qa-allow-price: fixture\n')
    assert s.main([str(tmp_path)], allow={}) == 0


def test_allowlist_exact_line_only_and_stale_fails(tmp_path):
    f = _write(tmp_path, "app/x.py", '"""blocks pricing phrases"""\nlabel = "See pricing"\n')
    rel = s._rel(f)
    allow = {(rel, '"""blocks pricing phrases"""'): "docstring"}
    assert s.main([str(tmp_path)], allow=allow) == 1  # second line still caught
    f.write_text('"""blocks pricing phrases"""\n')
    assert s.main([str(tmp_path)], allow=allow) == 0
    f.write_text("nothing here\n")
    assert s.main([str(tmp_path)], allow=allow) == 1  # stale entry fails
