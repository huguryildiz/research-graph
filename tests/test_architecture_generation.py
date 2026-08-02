import importlib.util
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_architecture_contracts.py"
HTML = ROOT / "architecture.html"


def _generator():
    spec = importlib.util.spec_from_file_location("architecture_generator", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_architecture_contract_data_is_fresh():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_generator_changes_only_the_marked_data_block():
    generator = _generator()
    current = HTML.read_text(encoding="utf-8")
    begin = current.index(generator.BEGIN) + len(generator.BEGIN)
    end = current.index(generator.END, begin)
    stale = current[:begin] + "\nconst ARTIFACTS=[];\nconst CONTRACTS=[];\n" + current[end:]
    rendered = generator.render_html(stale)

    assert rendered[:begin] == current[:begin]
    assert rendered[rendered.index(generator.END):] == current[current.index(generator.END):]
    assert rendered == current


def test_every_gate_criterion_has_one_canonical_source():
    generator = _generator()
    kit = generator.load_kit(ROOT, assignment="assignment.example.yaml")
    assert all(gate.criterion for gate in kit.gates.values())
    generated = generator.generated_data()
    for gate in kit.gates.values():
        assert generator._js(gate.criterion) in generated
