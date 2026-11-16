"""Wires the agents into a LangGraph state machine.

parse_cv → analyze_job → score_fit → human_review (pause) → tailor_cv → write_cover_letter → critic
                                                               ↑                                 │
                                                               └──────── retry (max 2) ──────────┘
"""

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.graph import nodes
from app.graph.state import HireMateState

# Node order, also used by the UI to draw the graph.
NODE_ORDER = [
    "parse_cv",
    "analyze_job",
    "score_fit",
    "human_review",
    "tailor_cv",
    "write_cover_letter",
    "critic",
]


def build_graph(checkpointer=None):
    graph = StateGraph(HireMateState)
    graph.add_node("parse_cv", nodes.parse_cv)
    graph.add_node("analyze_job", nodes.analyze_job)
    graph.add_node("score_fit", nodes.score_fit)
    graph.add_node("human_review", nodes.human_review)
    graph.add_node("tailor_cv", nodes.tailor_cv)
    graph.add_node("write_cover_letter", nodes.write_cover_letter)
    graph.add_node("critic", nodes.critic)

    graph.add_edge(START, "parse_cv")
    graph.add_edge("parse_cv", "analyze_job")
    graph.add_edge("analyze_job", "score_fit")
    graph.add_edge("score_fit", "human_review")
    graph.add_edge("human_review", "tailor_cv")
    graph.add_edge("tailor_cv", "write_cover_letter")
    graph.add_edge("write_cover_letter", "critic")
    graph.add_conditional_edges(
        "critic", nodes.route_after_critic, {"retry": "tailor_cv", "end": END}
    )

    # The checkpointer saves state at the human-review pause so we can resume later.
    return graph.compile(checkpointer=checkpointer or InMemorySaver())
