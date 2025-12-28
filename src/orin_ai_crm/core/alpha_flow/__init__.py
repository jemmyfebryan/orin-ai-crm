from typing import Any, Dict, List, Optional, Union, Callable
from dotenv import load_dotenv

from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI

from src.orin_ai_crm.core.alpha_flow.utils import get_state_schema
from src.orin_ai_crm.core.agents.nodes import LLMNode, ConditionalNode
from src.orin_ai_crm.core.logger import get_logger

load_dotenv()

logger = get_logger(__name__)


# --- 1. Enhanced Models ---

class NodeConfig(BaseModel):
    name: str
    node_type: str = Field(alias="node")
    args: Dict[str, Any] = {}
    to: List[str] = [] # Use names for references to support loops
    # Add support for conditional routing
    conditional_to: Optional[Dict[str, str]] = None 

class AlphaFlowSchema(BaseModel):
    flow_id: str
    state_schema: str = "no_schema"
    nodes: List[NodeConfig] # Linear list is easier to manage than nested for complex graphs

# --- 2. Node Registry ---

class NodeRegistry:
    def __init__(self):
        self._registry = {}

    def register(self, type_name: str, constructor: Callable):
        self._registry[type_name] = constructor

    def build(self, type_name: str, args: Dict[str, Any]):
        if type_name not in self._registry:
            raise ValueError(f"Node type {type_name} not registered.")
        return self._registry[type_name](**args)

# Initialize Registry
registry = NodeRegistry()

# Example: Registering the LLM Node
def create_llm_node(**kwargs):
    # We can inject global config here or take it from kwargs
    llm = ChatOpenAI(model_name="gpt-4.1-nano", temperature=0)
    return LLMNode(llm=llm, **kwargs)

def create_conditional_node(**kwargs):
    return ConditionalNode(**kwargs)

registry.register("llm_node", create_llm_node)
registry.register("conditional_node", create_conditional_node)

conditional_nodes = []

# --- 3. The Flow Builder ---

class FlowBuilder:
    def __init__(self, schema: Dict[str, Any]):
        self.data = AlphaFlowSchema(**schema)
        self.state_class = get_state_schema(self.data.state_schema)
        self.workflow = StateGraph(self.state_class)

    def build(self):
        # Create a lookup for quick access to node configs
        node_lookup = {n.name: n for n in self.data.nodes}
        
        # Step 1: Add standard nodes only
        for node_cfg in self.data.nodes:
            if node_cfg.node_type not in [START, END, "start", "end", "conditional_node"]:
                node_instance = registry.build(node_cfg.node_type, node_cfg.args)
                self.workflow.add_node(node_cfg.name, node_instance)
                logger.info(f"Registered standard node: {node_cfg.name}")
        # Step 2: Add Edges & Conditional Routing
        for node_cfg in self.data.nodes:
            from_node = START if node_cfg.node_type in [START, "start"] else node_cfg.name
            
            # If this is a router node itself, we skip (handled by the node pointing TO it)
            if node_cfg.node_type == "conditional_node":
                continue

            for target_name in node_cfg.to:
                target_cfg = node_lookup.get(target_name)

                # Case A: The target is a Conditional Router
                if target_cfg and target_cfg.node_type == "conditional_node":
                    # Build the router function
                    router_instance = registry.build("conditional_node", target_cfg.args)
                    
                    # Create the path map (mapping output names to actual nodes/END)
                    # We grab all possible 'output_node' values from rules + default_node
                    path_map = {
                        rule["output_node"]: (END if rule["output_node"].lower() == "end" else rule["output_node"])
                        for rule in target_cfg.args.get("rules", [])
                    }
                    default = target_cfg.args.get("default_node", END)
                    path_map[default] = END if default.lower() == "end" else default

                    self.workflow.add_conditional_edges(
                        from_node,
                        router_instance, # The __call__ method of your ConditionalNode class
                        path_map
                    )
                    logger.info(f"Added conditional edge from {from_node} via {target_name}")

                # Case B: Standard Edge
                else:
                    to_node = END if target_name.lower() in [END, "end"] else target_name
                    self.workflow.add_edge(from_node, to_node)
                    logger.info(f"Added standard edge: {from_node} -> {to_node}")

        return self.workflow.compile()