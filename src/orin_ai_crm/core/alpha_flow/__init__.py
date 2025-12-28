from typing import Any, Dict, List, Optional, Union, Callable
from dotenv import load_dotenv

from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI

from src.orin_ai_crm.core.alpha_flow.utils import get_state_schema
from src.orin_ai_crm.core.agents.nodes import LLMNode
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
    state_schema: str
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

registry.register("llm_node", create_llm_node)

# --- 3. The Flow Builder ---

class FlowBuilder:
    def __init__(self, schema: Dict[str, Any]):
        self.data = AlphaFlowSchema(**schema)
        self.state_class = get_state_schema(self.data.state_schema)
        self.workflow = StateGraph(self.state_class)

    def build(self):
        # Step 1: Add all Nodes, but skip START/END constants
        for node_cfg in self.data.nodes:
            # Check against both the string and the LangGraph constants
            if node_cfg.node_type not in [START, END, "start", "end"]:
                node_instance = registry.build(node_cfg.node_type, node_cfg.args)
                self.workflow.add_node(node_cfg.name, node_instance)
                logger.info(f"Registered node: {node_cfg.name}")

        # Step 2: Add all Edges
        for node_cfg in self.data.nodes:
            # Determine the source name
            if node_cfg.node_type in [START, "start"]:
                from_node = START
            else:
                from_node = node_cfg.name
            
            for target in node_cfg.to:
                # Determine the destination name
                if target.lower() in [END, "end"]:
                    to_node = END
                else:
                    to_node = target
                
                self.workflow.add_edge(from_node, to_node)
                logger.info(f"Added edge: {from_node} -> {to_node}")

        return self.workflow.compile()