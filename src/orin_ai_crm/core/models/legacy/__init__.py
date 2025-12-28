import random
from typing import Any, Dict, List

from src.orin_ai_crm.core.logger import get_logger

logger = get_logger(__name__)


class AgentEnvironment:
    """
    Simulates the n8n 'Global' environment.
    Holds shared clients and variables.
    """
    def __init__(self, env_vars: dict = None):
        self.variables = env_vars or {}
        self.clients = {}  # Store initialized LLM, SQL, or Redis clients here

    def set_client(self, key: str, client_instance: Any):
        self.clients[key] = client_instance

    def get_variable(self, key: str):
        if key in self.variables.keys():
            return self.variables.get(key)
        else:
            logger.error(f"No key {key} in environment variables.")
            return None

class Node:
    """Base class for all n8n nodes."""
    def __init__(self, name: str):
        self.name = name
        self.input_data: Any = None
        self.async_node = False

    def execute(self, input_data: Any, env: AgentEnvironment = None) -> Any:
        raise NotImplementedError("Subclasses must implement execute()")
    
class LogNode(Node):
    def __init__(self, name: str, message: str, log_type: str = "", pass_data: bool = False):
        super().__init__(name)
        self.log_type = log_type
        self.message = message
        self.pass_data = pass_data
        
    def execute(self, input_data: Dict[str, Any]):
        if self.log_type == "info":
            logger.info(f"{self.message}")
        elif self.log_type == "error":
            logger.error(f"{self.message}")
        elif self.log_type == "warning":
            logger.warning(f"{self.message}")
        else:
            logger.info(f"[UNKNOWN] {self.message}")
        return input_data if self.pass_data else None
            
class PassNode(Node):
    def __init__(self, name: str):
        super().__init__(name)

    def execute(self, input_data: Any) -> Dict[str, Any]:
        return input_data
    
class RandomNode(Node):
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

    async def run(self, start_node_name: str, initial_data: Any, is_return: bool = False):
        logger.info(f"Workflow start at {start_node_name}")
                
        current_node_name = start_node_name
        current_data = initial_data

        while current_node_name:
            node = self.nodes[current_node_name]
            
            result = await node.execute(current_data) if node.async_node else node.execute(current_data)

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
                if isinstance(result, str):
                    logger.error(f"No branch found for '{result}' from node '{current_node_name}'.")
                    logger.warning("String result from a node will always recognized as a branch name")
                else:
                    logger.info(f"Workflow finished at {current_node_name}")
                break
        
        return result if is_return else None

# Environment Models
class GetEnvironmentVarNode(Node):
    def __init__(self, name: str, key: str, env: AgentEnvironment):
        super().__init__(name)
        self.key = key
        self.env = env
        
    def execute(self, input_data: Any):
        # Instead of initializing a new connection, use the one from the environment
        value = self.env.get_variable(self.key)
        if isinstance(input_data, Dict):
            new_data = input_data | {self.key: value}
        else:
            new_data = input_data
            logger.warning(f"input_data is {type(input_data)}, not a Dict, return the original instead")
        return new_data

class SQLNode(Node):
    def execute(self, input_data: Any, env: AgentEnvironment):
        # Instead of initializing a new connection, use the one from the environment
        db = env.clients.get("db_client")
        print(f"[{self.name}] Querying database using shared client...")
        # db.execute("SELECT...") 
        return {"status": "success"}