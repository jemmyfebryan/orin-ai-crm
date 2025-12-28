from langgraph.graph import StateGraph, START, END

def create():
    workflow = StateGraph()
    
    workflow.add_node(START)
    workflow.add_node(END)