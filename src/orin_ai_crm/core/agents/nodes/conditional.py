import operator
from typing import Any, Dict, List, Callable, Optional, Union

# Registry for simple logical comparisons
EVALUATORS: Dict[str, Callable[[Any, Any], bool]] = {
    "is_equal": operator.eq,
    "not_equal": operator.ne,
    "contains": lambda container, item: item in container,
    "greater_than": operator.gt,
    "less_than": operator.lt,
}

def resolve_state_path(state: Dict, path: str) -> Any:
    """
    Allows accessing nested state via dot notation (e.g., 'customer.status')
    or list indices (e.g., 'messages.-1.content')
    """
    parts = path.split(".")
    current = state
    try:
        for part in parts:
            if isinstance(current, list):
                # Handle negative indices for messages
                current = current[int(part)]
            else:
                current = current.get(part)
        return current
    except (IndexError, ValueError, AttributeError, TypeError):
        return None