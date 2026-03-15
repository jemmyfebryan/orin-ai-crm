
# --- ENDPOINT UTAMA (OLD - Intent Classification Architecture) ---
# @app.post("/chat", response_model=ChatResponse)
# async def chat_endpoint(req: ChatRequest):
#     """
#     Legacy endpoint using intent classification architecture.
#     Use /chat-agent for the new agentic architecture with 30+ tools.
#     """
#     try:
#         # 1. Build identifier dict
#         identifier = {
#             "phone_number": req.phone_number,
#             "lid_number": req.lid_number
#         }

#         # 3. Build history list untuk LangGraph
#         is_new_chat = req.is_new_chat

#         # 2. Get or create customer (returns detached object)
#         customer = await get_or_create_customer(
#             identifier=identifier,
#             contact_name=req.contact_name,
#             is_onboarded=(not is_new_chat),
#         )
#         customer_id = customer.id

#         # If not new chat, try to fetch data from DB
#         # If there is no chat history in DB but the request is not a new chat
#         history = []
#         if not is_new_chat:
#             history_rows = await get_chat_history(customer_id)
#             for row in history_rows:
#                 if row.message_role == "user":
#                     history.append(HumanMessage(content=row.content))
#                 else:
#                     history.append(AIMessage(content=row.content))

#         # 5. Load customer data from database
#         customer_data = {}
#         if customer.id:
#             customer_data["id"] = customer_id
#         if customer.name:
#             customer_data["name"] = customer.name
#         if customer.domicile:
#             customer_data["domicile"] = customer.domicile
#         if customer.vehicle_id:
#             customer_data["vehicle_id"] = customer.vehicle_id
#         if customer.vehicle_alias:
#             customer_data["vehicle_alias"] = customer.vehicle_alias
#         if customer.unit_qty:
#             customer_data["unit_qty"] = customer.unit_qty
#         if customer.is_onboarded:
#             customer_data["is_onboarded"] = customer.is_onboarded
#         customer_data["is_b2b"] = customer.is_b2b if customer.is_b2b else False

#         logger.info(f"Customer data: {customer_data}")

#         # Check if form was already submitted (we have complete data)
#         is_data_filled = (
#             customer_data.get("domicile") or
#             customer_data.get("vehicle_alias") or
#             customer_data.get("unit_qty", 0) > 0
#         )
#         if is_data_filled:
#             logger.info(f"Customer has complete data - form_submitted=True")
#         customer_data["is_filled"] = is_data_filled

#         # Determine if we should send the form
#         # If customer is not onboarded (is_new_chat=True), send_form=True
#         send_form = not customer.is_onboarded if customer.is_onboarded is not None else is_new_chat
#         logger.info(f"send_form determined as: {send_form} (is_onboarded={customer.is_onboarded}, is_new_chat={is_new_chat})")

#         # 7. Simpan pesan baru dari user ke Database
#         await save_message_to_db(customer_id, "user", req.message)

#         # 8. Susun State untuk LangGraph
#         # Tambahkan pesan terbaru ke dalam history
#         current_messages = history + [HumanMessage(content=req.message)]

#         initial_state = {
#             "messages": current_messages,
#             "phone_number": req.phone_number,
#             "lid_number": req.lid_number,
#             "contact_name": req.contact_name,
#             "customer_id": customer_id,
#             "step": "start",
#             "route": "UNASSIGNED",
#             "customer_data": customer_data,
#             "send_form": send_form,
#             # "awaiting_form": awaiting_form,
#             # "form_submitted": form_submitted
#         }

#         # 9. Jalankan AI Workflow (LangGraph)
#         # Quality check is now handled within the workflow graph
#         final_state = await hana_bot.ainvoke(initial_state)

#         # logger.info(f"FINAL STATE:\n{final_state}")

#         # 10. Ambil balasan terakhir dari AI
#         last_message = final_state["messages"][-1]
#         ai_reply = last_message.content

#         # 11. Simpan balasan AI ke Database
#         await save_message_to_db(customer_id, "ai", ai_reply)

#         return ChatResponse(
#             customer_id=customer_id,
#             phone_number=req.phone_number,
#             lid_number=req.lid_number,
#             reply=ai_reply,
#             route=final_state.get("route", "UNASSIGNED"),
#             step=final_state.get("step", "unknown")
#         )

#     except ValueError as ve:
#         # Validation error
#         raise HTTPException(status_code=400, detail=str(ve))
#     except Exception as e:
#         print(f"Error: {str(e)}")
#         import traceback
#         traceback.print_exc()
#         raise HTTPException(status_code=500, detail="Terjadi kesalahan pada server AI.")

