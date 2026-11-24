"""Cross-boundary contract: the card's actual prompt must reach the advice route."""
import re
from pathlib import Path

import pytest
from api.assistant import routing

@pytest.mark.parametrize('stage',['出苗展叶期','现蕾开花期','果实成熟期','生育后期','采收及休眠期'])
def test_frontend_agronomy_prompt_does_not_require_point_coordinates(stage):
    source=Path(__file__).resolve().parents[2]/'frontend/src/assistant/agronomy.ts'
    template=re.search(r'return `([^`]+)`',source.read_text('utf-8')).group(1)
    question=template.replace('${stage}',stage)
    assert routing.plan(question)['mode']=='mixed'
    assert '外部湿度不是棚内湿度' in question
    assert '棚内温度为模型估算' in question
