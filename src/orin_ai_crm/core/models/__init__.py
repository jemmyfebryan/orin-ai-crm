import random
from typing import Any, Dict, List

from src.orin_ai_crm.core.logger import get_logger

logger = get_logger(__name__)

class Node:
    """Base class for all n8n nodes."""
    def __init__(self, name: str):
        self.name = name
        self.input_data: Any = None

    def execute(self, input_data: Any) -> Any:
        raise NotImplementedError("Subclasses must implement execute()")
    
class Log(Node):
    def __init__(self, name: str, message: str, log_type: str = ""):
        super().__init__(name)
        self.log_type = log_type
        self.message = message
        
    def execute(self, input_data: Dict[str, Any]):
        if self.log_type == "info":
            logger.info(f"{self.message}")
        elif self.log_type == "error":
            logger.error(f"{self.message}")
        elif self.log_type == "warning":
            logger.warning(f"{self.message}")
        else:
            logger.info(f"[UNKNOWN] {self.message}")
            
class Pass(Node):
    def __init__(self, name: str, input_data: Any):
        super().__init__(name)
        self.input_data = input_data

    def execute(self, input_data: Any) -> Dict[str, Any]:
        return self.input_data
    
class Random(Node):
    def __init__(self, name: str, random_type: str, value: tuple):
        super().__init__(name)
        self.random_type = random_type
        self.value = value

    def execute(self, input_data: Any) -> Dict[str, Any]:
        return {"data": getattr(random, self.random_type)(*self.value)}

class HTTPRequestNode(Node):
    def __init__(self, name: str, url: str, method: str = "GET"):
        super().__init__(name)
        self.url = url
        self.method = method

    def execute(self, input_data: Any) -> Dict[str, Any]:
        # Simulating an API call
        print(f"[{self.name}] Calling {self.method} {self.url}...")
        return {"status": 200, "data": {"user_id": 123, "active": True}}

class Agent:
    """Manager to handle the connection between nodes."""
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Dict[str, str]] = []

    def add_node(self, node: Node):
        self.nodes[node.name] = node

    def add_edge(self, from_node: str, to_node: str, branch: str = "main"):
        self.edges.append({
            "from": from_node,
            "to": to_node,
            "branch": branch
        })

    def run(self, start_node_name: str, initial_data: Any, is_return: bool = False):
        current_node_name = start_node_name
        current_data = initial_data

        while current_node_name:
            node = self.nodes[current_node_name]
            result = node.execute(current_data)

            # If the result is a branch string (like 'true'/'false'), use it to find the next node
            branch = result if isinstance(result, str) else "main"
            
            # Find the next node in the sequence
            next_edge = next(
                (e for e in self.edges if e["from"] == current_node_name and e["branch"] == branch), 
                None
            )
            
            if next_edge:
                current_node_name = next_edge["to"]
                # Update data if the node returned a dictionary/data instead of just a branch
                if not isinstance(result, str):
                    current_data = result
            else:
                print(f"Workflow finished at {current_node_name}")
                break
        
        if is_return: return result