from src.orin_ai_crm.core.models.states import CRMState

def get_state_schema(name: str):
    mapping = {"crm_state": CRMState}
    return mapping.get(name, CRMState)