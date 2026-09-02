"""日报渲染：Markdown（人读）+ JSON（机读/存档）。"""
from __future__ import annotations

import json

from jinja2 import Template

from ..models.report import StructuredReport

_MD_TEMPLATE = Template(
    r"""### {{ r.headline }}
- **事件 ID**：`{{ r.event_id }}` ({{ r.category }} / 来源数 {{ r.raw_article_count }})
- **核验事实**：
{% for f in r.verified_facts %}
  - {{ f.text }} {% if f.single_source_claim %}【单方声称】{% endif %} `conf={{ f.confidence }}` — {{ f.quote_spans[0].source_name }}
{% endfor %}
- **观点分歧**：
  - {{ r.perspectives_divergence.left_leaning_focus }}
  - {{ r.perspectives_divergence.right_leaning_focus }}
  - {{ r.perspectives_divergence.blindspot_warning }}
- **背景数据**：{% if r.background_data.key_stat %}{{ r.background_data.key_stat }}{% else %}（未匹配 OWID/Pew 宏观基准，待接入数据源）{% endif %}
- **来源**：{% for s in r.sources %}[{{ s.name }}]({{ s.url }}) `{{ s.bias.value }}` {% endfor %}
    """
)


def render_markdown(r: StructuredReport) -> str:
    return _MD_TEMPLATE.render(r=r).strip()


def render_json(r: StructuredReport) -> str:
    return json.dumps(r.to_render_dict(), ensure_ascii=False, indent=2)


def render_daily_markdown(reports: list[StructuredReport], report_date: str) -> str:
    header = f"# 中立客观日报 · {report_date}\n\n"
    body = "\n\n".join(render_markdown(r) for r in reports)
    footer = "\n\n> 生成引擎：规则/确定性；每条事实均带引文接地；无共分母证据的事件已剔除。"
    return header + body + footer