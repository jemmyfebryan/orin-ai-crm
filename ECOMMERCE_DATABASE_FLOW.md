# E-commerce Flow - Database-Driven Products

## Summary of Changes

### Problem
- Previous implementation had **hardcoded** product information (TANAM, INSTAN types, descriptions, links)
- HANA_PERSONA contained hardcoded product knowledge
- Not scalable - needed code changes to update products
- Difficult to answer diverse product questions

### Solution
- Moved to **database-driven** product system
- LLM now fetches product data from `products` table
- Removed all hardcoded product information
- Agent can now answer any product question using database knowledge

---

## Changes Made

### 1. Product Tools (`product_tools.py`)

#### New Functions Added:

**`answer_product_question_from_db(question, customer_data)`**
```python
# Answers product questions using LLM with database product context
answer = await answer_product_question_from_db(
    question="Berapa harga GPS yang bisa matikan mesin?",
    customer_data={"name": "Budi", "vehicle_alias": "Avanza"}
)
```

**`recommend_products_from_db(category, vehicle_type, budget, features_needed)`**
```python
# Recommends products based on customer needs
products, explanation = await recommend_products_from_db(
    category="TANAM",
    vehicle_type="mobil",
    budget="<500rb",
    features_needed=["matikan mesin", "sadap suara"]
)
```

#### Updated Functions:

**`format_products_for_llm(products)`**
- Now handles price as String (not Integer)
- Properly formats features as arrays/lists
- Displays specifications separately from features
- Better structured output for LLM consumption

---

### 2. E-commerce Nodes (`ecommerce_nodes.py`)

#### Before (Hardcoded):
```python
HANA_PERSONA = """...
ATURAN PRODUK GPS MOBIL:
- Tipe TANAM: OBU F & OBU V (Tersembunyi, dipasang teknisi, lacak + matikan mesin).
- Tipe INSTAN: OBU D, T1, T (Bisa pasang sendiri tinggal colok OBD, hanya lacak).
..."""

def generate_ecommerce_link(product_type, vehicle_type, unit_qty):
    if product_type == "TANAM":
        link = """Untuk pembelian GPS tipe TANAM (OBU F & OBU V)..."""
    # More hardcoded links
```

#### After (Database-Driven):
```python
HANA_PERSONA = """...
INFORMASI PRODUK:
Kamu memiliki akses ke database produk lengkap. Gunakan informasi tersebut untuk menjawab
pertanyaan customer tentang:
- Fitur produk (lacak, matikan mesin, sadap suara, monitoring BBM, dll)
- Harga dan paket kuota
- Perbedaan tipe produk
- Link e-commerce untuk pembelian
..."""

async def node_ecommerce(state: AgentState):
    # Uses database to answer ANY product question
    answer = await answer_product_question_from_db(
        question=last_message,
        customer_data=data
    )
    return {"messages": [AIMessage(content=answer)]}
```

---

### 3. Profiling Nodes (`profiling_nodes.py`)

#### Removed Hardcoded Product Info:
```python
# BEFORE:
HANA_PERSONA = """...
ATURAN PRODUK GPS MOBIL:
- Tipe TANAM: OBU F & OBU V (Tersembunyi, dipasang teknisi, lacak + matikan mesin).
- Tipe INSTAN: OBU D, T1, T (Bisa pasang sendiri tinggal colok OBD, hanya lacak).
..."""

# AFTER:
HANA_PERSONA = """...
INFORMASI PRODUK:
Kamu memiliki akses ke database produk lengkap. Jika user tanya tentang produk GPS,
tanya kebutuhan mereka dulu (jenis kendaraan, preferensi fitur) baru berikan rekomendasi.
..."""
```

---

## How It Works Now

### Flow Diagram:
```
User Question
    ↓
node_ecommerce
    ↓
answer_product_question_from_db()
    ↓
Fetch all products from database
    ↓
Format products for LLM (structured)
    ↓
LLM generates answer using:
  - Product names & descriptions
  - Features (arrays)
  - Specifications
  - Prices (flexible format)
  - E-commerce links
    ↓
Natural response to customer
```

### Example Conversation:

**User:** "Halo kak, saya mau tanya GPS yang bisa matikan mesin buat mobil, harganya berapa?"

**System:**
1. Fetches all products from `products` table
2. Formats them for LLM:
   ```
   PRODUK TERSEDIA:
   1. OBU V (OBU-V)
      Kategori: TANAM - OBU
      Harga: 25rb/bulan (perpanjangan setelah 1 bulan pertama)
      Description: GPS Tracker dengan fitur matikan mesin jarak jauh dan sadap suara.
      Fitur Utama: Lacak real-time, Matikan mesin jarak jauh, Sadap suara
      Specifications:
      • Kuota Awal: Gratis 1 bulan
      • Garansi: Seumur hidup
      Link Beli:
      • Tokopedia: https://...
      • Shopee: https://...
   ```
3. LLM generates response:
   ```
   Halo kak! 👋 Untuk GPS yang bisa matikan mesin buat mobil, kakak bisa cek OBU V ya!

   OBU V itu GPS tracker dengan fitur:
   ✅ Matikan mesin jarak jauh
   ✅ Sadap suara
   ✅ Lacak real-time
   ✅ Riwayat perjalanan

   Harganya 25rb/bulan (perpanjangan setelah gratis 1 bulan pertama).

   Kakak bisa order di:
   🛒 Tokopedia: [link]
   🛒 Shopee: [link]

   Ada pertanyaan lain tentang produknya kak? 😊
   ```

---

## Benefits

| Before | After |
|--------|-------|
| ❌ Hardcoded product info | ✅ Database-driven products |
| ❌ Fixed TANAM/INSTAN types | ✅ Flexible categories (TANAM, INSTAN, KAMERA, AKSESORIS) |
| ❌ Fixed price format | ✅ Flexible pricing ("25rb/bulan", "600rb/tahun") |
| ❌ Hard to update products | ✅ Update via JSON or database |
| ❌ Limited product knowledge | ✅ Can answer ANY product question |
| ❌ Hardcoded links | ✅ Dynamic links from database |

---

## Product Database Structure

### Modular Fields:
```json
{
  "name": "OBU V",
  "sku": "OBU-V",
  "category": "TANAM",
  "subcategory": "OBU",
  "description": "GPS Tracker dengan fitur matikan mesin...",
  "features": {
    "fitur_utama": ["Lacak real-time", "Matikan mesin", "Sadap suara"],
    "server": "ORIN LITE"
  },
  "price": "25rb/bulan (perpanjangan setelah 1 bulan pertama)",
  "specifications": {
    "kuota_awal": "Gratis 1 bulan",
    "garansi": "Seumur hidup",
    "komponen": ["Sim Card"]
  },
  "ecommerce_links": {
    "tokopedia": "https://...",
    "shopee": "https://..."
  },
  "installation_type": "pasang_technisi",
  "can_shutdown_engine": true
}
```

---

## Exported Functions

### New Exports in `__init__.py`:
```python
from src.orin_ai_crm.core.agents.tools import (
    # ... existing exports ...
    # Product Recommendation & Q&A Tools (with database)
    "recommend_products_from_db",
    "answer_product_question_from_db",
)
```

---

## API Endpoints

### Reset Products to Defaults:
```bash
POST /reset-products
```
- Deletes all existing products
- Inserts products from `default_products.json`

---

## Files Modified

1. **`product_tools.py`**
   - Added `answer_product_question_from_db()`
   - Added `recommend_products_from_db()`
   - Updated `format_products_for_llm()` for modular structure

2. **`ecommerce_nodes.py`**
   - Removed hardcoded product info
   - Removed `generate_ecommerce_link()` usage
   - Now uses `answer_product_question_from_db()`

3. **`profiling_nodes.py`**
   - Removed hardcoded TANAM/INSTAN from HANA_PERSONA
   - Updated to reference database products

4. **`database.py`**
   - Changed `price` from Integer to String(100)

5. **`default_products.json`**
   - Restructured as array of objects
   - Modular fields (features, specifications, price as string)

---

## Testing

To test the new flow:

1. **Reset products to defaults:**
   ```bash
   curl -X POST http://localhost:8000/reset-products
   ```

2. **Send product question via chat:**
   ```bash
   curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{
       "phone_number": "62812345678",
       "message": "Berapa harga GPS yang bisa matikan mesin?"
     }'
   ```

3. **Check response:**
   - Should include product info from database
   - Should include relevant features
   - Should include pricing
   - Should include e-commerce links

---

## Future Enhancements

Possible improvements:
1. Add product variants (unit only vs with quota)
2. Add stock availability
3. Add product comparison feature
4. Add bulk pricing for B2B
5. Add product recommendation based on vehicle type from VPS DB
6. Add product images from database
