"""The prompt must teach complete examples accepted by the unchanged output contract."""
import json
import re
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[1] / 'skills/cahy-kn2-tom-tat'
SCHEMA = json.loads((ROOT / 'references/s2_tom_tat.schema.json').read_text(encoding='utf-8'))
EXAMPLES = [json.loads(block) for block in re.findall(r'```json\s*\n([\s\S]*?)\n```', (ROOT / 'SKILL.md').read_text(encoding='utf-8'))]


@pytest.mark.parametrize('example', EXAMPLES)
def test_prompt_examples_are_complete_short_summaries(example):
    Draft202012Validator({'$ref': '#/$defs/tom_tat_ngan', '$defs': SCHEMA['$defs']}).validate(example)
    assert len(example['trich_yeu'].split()) <= 40
    assert sum(len(idea.split()) for idea in example['y_chinh']) <= 150


def test_examples_cover_both_legal_and_nonlegal_output_shapes():
    assert any('qppl' in example for example in EXAMPLES)
    ordinary = [example for example in EXAMPLES if example.get('so_ky_hieu') is None]
    assert ordinary and all('qppl' not in example for example in ordinary)
