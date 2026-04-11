"""
Gradio demo for Structural Isomorphism Search Engine.

Usage:
    pip install gradio
    python demo/app.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import gradio as gr
from structural_isomorphism import StructuralSearch

# Global search engine instance (loaded once)
search = None


def initialize():
    """Load model and knowledge base."""
    global search
    if search is None:
        search = StructuralSearch()
    return search


def do_search(query: str, top_k: int) -> str:
    """Run structural search and format results as HTML."""
    engine = initialize()
    results = engine.query(query, top_k=int(top_k))

    if not results:
        return "<p style='color: #888;'>No results found. Check that knowledge base files exist in data/.</p>"

    html_parts = []
    for i, r in enumerate(results, 1):
        score_color = "#22c55e" if r["score"] > 0.7 else "#eab308" if r["score"] > 0.4 else "#ef4444"
        html_parts.append(f"""
        <div style="border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div>
                    <span style="font-weight: 700; font-size: 1.1em;">#{i} {r['name']}</span>
                    <span style="background: #f3f4f6; padding: 2px 8px; border-radius: 4px; margin-left: 8px; font-size: 0.9em;">{r['domain']}</span>
                    <span style="background: #f3f4f6; padding: 2px 8px; border-radius: 4px; margin-left: 4px; font-size: 0.85em; color: #6b7280;">Type {r['type_id']}</span>
                </div>
                <span style="color: {score_color}; font-weight: 700; font-size: 1.1em;">{r['score']:.3f}</span>
            </div>
            <p style="color: #374151; margin: 0; line-height: 1.6;">{r['description']}</p>
        </div>
        """)

    return "\n".join(html_parts)


EXAMPLES = [
    ["两个市场参与者互相等待对方先行动，导致谁也不动"],
    ["一个系统在受到小扰动后能自动回到原来的状态"],
    ["产品刚上市时增长缓慢，然后突然爆发式增长，最后趋于饱和"],
    ["每个人都做出对自己最优的选择，但合起来的结果对所有人都不好"],
    ["温度只需要微小变化，整个系统就突然从一种状态变成另一种状态"],
]

DESCRIPTION = """
# Structural Isomorphism Search Engine

Discover hidden cross-domain structural connections. Describe any phenomenon in natural language,
and the engine will find structurally similar phenomena from completely different domains.

The model recognizes **structural patterns** (feedback loops, phase transitions, cascade effects, etc.)
rather than surface-level keyword matches.
"""

with gr.Blocks(
    title="Structural Isomorphism Search",
    theme=gr.themes.Soft(),
) as demo:
    gr.Markdown(DESCRIPTION)

    with gr.Row():
        with gr.Column(scale=3):
            query_input = gr.Textbox(
                label="Describe a phenomenon",
                placeholder="e.g., A thermostat detects temperature below setpoint, turns on heating...",
                lines=3,
            )
        with gr.Column(scale=1):
            top_k_slider = gr.Slider(
                minimum=1, maximum=20, value=10, step=1,
                label="Number of results",
            )
            search_btn = gr.Button("Search", variant="primary", size="lg")

    gr.Examples(
        examples=EXAMPLES,
        inputs=query_input,
    )

    results_output = gr.HTML(label="Results")

    search_btn.click(
        fn=do_search,
        inputs=[query_input, top_k_slider],
        outputs=results_output,
    )
    query_input.submit(
        fn=do_search,
        inputs=[query_input, top_k_slider],
        outputs=results_output,
    )


if __name__ == "__main__":
    demo.launch(share=False)
