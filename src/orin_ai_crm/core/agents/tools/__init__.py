"""
AI Agent Tools Package
"""

from src.orin_ai_crm.core.agents.tools.customer_tools import (
    get_or_create_customer,
    update_customer_profile,
    get_chat_history,
    save_message_to_db
)

from src.orin_ai_crm.core.agents.tools.meeting_tools import (
    get_pending_meeting,
    create_meeting,
    update_meeting,
    extract_meeting_info,
    book_or_update_meeting,
    MeetingInfo
)

from src.orin_ai_crm.core.agents.tools.product_tools import (
    get_pending_inquiry,
    create_product_inquiry,
    update_product_inquiry,
    extract_product_type,
    generate_ecommerce_link,
    ProductInfo,
    # Product query tools
    get_all_active_products,
    get_products_by_category,
    get_products_by_vehicle_type,
    search_products,
    format_products_for_llm,
    answer_product_question,
    recommend_products,
    # Ecommerce product management tools
    get_ecommerce_product,
    reset_products_to_default,
    initialize_default_products_if_empty,
    load_default_products_from_json,
    get_default_products_json_path
)

__all__ = [
    # Customer Tools
    "get_or_create_customer",
    "update_customer_profile",
    "get_chat_history",
    "save_message_to_db",

    # Meeting Tools
    "get_pending_meeting",
    "create_meeting",
    "update_meeting",
    "extract_meeting_info",
    "book_or_update_meeting",
    "MeetingInfo",

    # Product Tools
    "get_pending_inquiry",
    "create_product_inquiry",
    "update_product_inquiry",
    "extract_product_type",
    "generate_ecommerce_link",
    "ProductInfo",

    # Product Query Tools
    "get_all_active_products",
    "get_products_by_category",
    "get_products_by_vehicle_type",
    "search_products",
    "format_products_for_llm",
    "answer_product_question",
    "recommend_products",

    # Ecommerce Product Management Tools
    "get_ecommerce_product",
    "reset_products_to_default",
    "initialize_default_products_if_empty",
    "load_default_products_from_json",
    "get_default_products_json_path",
]
