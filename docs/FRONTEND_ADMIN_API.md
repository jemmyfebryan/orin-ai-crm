# Frontend Admin API Documentation

This document provides instructions for implementing the frontend settings panel to manage prompts and products via the admin API endpoints.

## Base URL

All endpoints are prefixed with `/admin`:
```
http://your-domain.com/admin
```

## Authentication

All admin endpoints require authentication. Ensure your frontend includes proper authentication headers with each request.

---

# Product Management Endpoints

## 1. Get All Products

Retrieve all active products from the database.

**Endpoint:** `GET /admin/products`

**Response:**
```json
{
  "success": true,
  "products": [
    {
      "id": 1,
      "name": "OBU M",
      "sku": "OBU-M",
      "category": "TANAM",
      "subcategory": "OBU",
      "vehicle_type": "motor listrik,mobil listrik",
      "description": "GPS Tracker dengan fitur pelacakan real-time...",
      "features": {
        "fitur_utama": ["Lacak real-time", "Riwayat perjalanan"],
        "bonus": "FREE Pelacak mini Orin Tag Android",
        "server": "ORIN LITE"
      },
      "price": "25rb/bulan",
      "installation_type": "pasang_technisi",
      "can_shutdown_engine": false,
      "is_realtime_tracking": true,
      "ecommerce_links": {
        "tokopedia": "https://...",
        "shopee": "https://..."
      },
      "images": [],
      "specifications": {},
      "compatibility": {},
      "is_active": true,
      "sort_order": 1
    }
  ],
  "count": 10
}
```

**Frontend Usage Example:**
```javascript
async function getProducts() {
  const response = await fetch('/admin/products', {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer YOUR_TOKEN'
    }
  });

  const data = await response.json();
  if (data.success) {
    return data.products;
  }
  throw new Error('Failed to fetch products');
}
```

---

## 2. Update Product

Update a specific product's information.

**Endpoint:** `PUT /admin/products/{product_id}`

**Request Body:**
```json
{
  "name": "OBU M Updated",
  "sku": "OBU-M",
  "category": "TANAM",
  "subcategory": "OBU",
  "vehicle_type": "motor listrik",
  "description": "Updated description...",
  "features": {
    "fitur_utama": ["Feature 1", "Feature 2"]
  },
  "price": "30rb/bulan",
  "installation_type": "pasang_technisi",
  "can_shutdown_engine": false,
  "is_realtime_tracking": true,
  "ecommerce_links": {
    "tokopedia": "https://..."
  },
  "images": ["image1.jpg", "image2.jpg"],
  "specifications": {},
  "compatibility": {},
  "is_active": true,
  "sort_order": 1
}
```

**Note:** Only include the fields you want to update. All fields are optional.

**Response:**
```json
{
  "success": true,
  "message": "Product 1 updated successfully",
  "product_id": 1
}
```

**Frontend Usage Example:**
```javascript
async function updateProduct(productId, productData) {
  const response = await fetch(`/admin/products/${productId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer YOUR_TOKEN'
    },
    body: JSON.stringify(productData)
  });

  const data = await response.json();
  if (data.success) {
    return data;
  }
  throw new Error(data.message || 'Failed to update product');
}
```

---

## 3. Reset Products to Defaults

Reset all products in the database to the default values from the hardcoded Python file.

**⚠️ WARNING:** This will DELETE all existing products and replace them with defaults!

**Endpoint:** `POST /admin/products/reset`

**Response:**
```json
{
  "success": true,
  "message": "Berhasil reset products: 10 produk dibuat, 5 produk dihapus",
  "deleted": 5,
  "created": 10,
  "errors": []
}
```

**Frontend Usage Example:**
```javascript
async function resetProducts() {
  if (!confirm('Are you sure? This will delete all existing products!')) {
    return;
  }

  const response = await fetch('/admin/products/reset', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer YOUR_TOKEN'
    }
  });

  const data = await response.json();
  if (data.success) {
    alert(data.message);
    return data;
  }
  throw new Error(data.message || 'Failed to reset products');
}
```

---

## 4. Download Products as Python File

Download all current products from the database as a Python file. This is useful for updating the hardcoded `default_products.py` file with the latest database content.

**Endpoint:** `GET /admin/products/download`

**Response:** Python file download (`default_products.py`)

**Frontend Usage Example:**
```javascript
async function downloadProducts() {
  const response = await fetch('/admin/products/download', {
    method: 'GET',
    headers: {
      'Authorization': 'Bearer YOUR_TOKEN'
    }
  });

  if (response.ok) {
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'default_products.py';
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  } else {
    throw new Error('Failed to download products');
  }
}
```

**Usage Workflow:**
1. Make changes to products via the frontend (update endpoints)
2. Download the updated products as Python file
3. Replace the hardcoded file: `src/orin_ai_crm/core/agents/custom/hana_agent/default_products.py`
4. Commit the updated file to your repository

---

# Prompt Management Endpoints

## 1. Get All Prompts

Retrieve all active prompts from the database.

**Endpoint:** `GET /admin/prompts`

**Response:**
```json
{
  "success": true,
  "prompts": [
    {
      "prompt_key": "hana_base_agent",
      "prompt_name": "Hana Base Agent",
      "prompt_text": "Kamu adalah AI customer service...",
      "description": "Base system prompt for Hana agent",
      "prompt_type": "system",
      "is_active": true
    },
    {
      "prompt_key": "agent_name",
      "prompt_name": "Agent Name",
      "prompt_text": "Siorin",
      "description": "The name of the AI agent",
      "prompt_type": "config",
      "is_active": true
    }
  ],
  "count": 15
}
```

**Frontend Usage Example:**
```javascript
async function getPrompts() {
  const response = await fetch('/admin/prompts', {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer YOUR_TOKEN'
    }
  });

  const data = await response.json();
  if (data.success) {
    return data.prompts;
  }
  throw new Error('Failed to fetch prompts');
}
```

---

## 2. Update Prompt

Update a specific prompt's text.

**Endpoint:** `PUT /admin/prompts/{prompt_key}`

**Request Body:**
```json
{
  "prompt_text": "Updated prompt text here..."
}
```

**Response:**
```json
{
  "success": true,
  "message": "Prompt hana_base_agent updated successfully",
  "prompt_key": "hana_base_agent"
}
```

**Frontend Usage Example:**
```javascript
async function updatePrompt(promptKey, promptText) {
  const response = await fetch(`/admin/prompts/${promptKey}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer YOUR_TOKEN'
    },
    body: JSON.stringify({
      prompt_text: promptText
    })
  });

  const data = await response.json();
  if (data.success) {
    return data;
  }
  throw new Error(data.message || 'Failed to update prompt');
}
```

---

## 3. Reset Prompts to Defaults

Reset all prompts in the database to the default values from the hardcoded Python file.

**⚠️ WARNING:** This will DELETE all existing prompts and replace them with defaults!

**Endpoint:** `POST /admin/prompts/reset`

**Response:**
```json
{
  "success": true,
  "message": "Berhasil reset prompts: 15 prompt dibuat, 3 prompt dihapus",
  "deleted": 3,
  "created": 15,
  "errors": []
}
```

**Frontend Usage Example:**
```javascript
async function resetPrompts() {
  if (!confirm('Are you sure? This will delete all existing prompts!')) {
    return;
  }

  const response = await fetch('/admin/prompts/reset', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer YOUR_TOKEN'
    }
  });

  const data = await response.json();
  if (data.success) {
    alert(data.message);
    return data;
  }
  throw new Error(data.message || 'Failed to reset prompts');
}
```

---

## 4. Download Prompts as Python File

Download all current prompts from the database as a Python file. This is useful for updating the hardcoded `default_prompts.py` file with the latest database content.

**Endpoint:** `GET /admin/prompts/download`

**Response:** Python file download (`default_prompts.py`)

**Frontend Usage Example:**
```javascript
async function downloadPrompts() {
  const response = await fetch('/admin/prompts/download', {
    method: 'GET',
    headers: {
      'Authorization': 'Bearer YOUR_TOKEN'
    }
  });

  if (response.ok) {
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'default_prompts.py';
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  } else {
    throw new Error('Failed to download prompts');
  }
}
```

**Usage Workflow:**
1. Make changes to prompts via the frontend (update endpoints)
2. Download the updated prompts as Python file
3. Replace the hardcoded file: `src/orin_ai_crm/core/agents/custom/hana_agent/default_prompts.py`
4. Commit the updated file to your repository

---

# Recommended Frontend UI Structure

## Products Management Page

```javascript
function ProductsManagementPage() {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);

  // Load products on mount
  useEffect(() => {
    loadProducts();
  }, []);

  async function loadProducts() {
    try {
      const data = await getProducts();
      setProducts(data);
    } catch (error) {
      alert('Failed to load products: ' + error.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleUpdateProduct(productId, updatedData) {
    try {
      await updateProduct(productId, updatedData);
      alert('Product updated successfully!');
      loadProducts(); // Reload to show changes
    } catch (error) {
      alert('Failed to update product: ' + error.message);
    }
  }

  async function handleResetProducts() {
    try {
      const result = await resetProducts();
      alert(result.message);
      loadProducts(); // Reload to show reset products
    } catch (error) {
      alert('Failed to reset products: ' + error.message);
    }
  }

  async function handleDownloadProducts() {
    try {
      await downloadProducts();
      alert('Products downloaded! Update default_products.py with this file.');
    } catch (error) {
      alert('Failed to download products: ' + error.message);
    }
  }

  if (loading) return <div>Loading...</div>;

  return (
    <div>
      <h1>Products Management</h1>

      <div className="actions">
        <button onClick={handleDownloadProducts}>
          Download Products (Python File)
        </button>
        <button onClick={handleResetProducts} className="danger">
          Reset to Defaults
        </button>
      </div>

      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>SKU</th>
            <th>Category</th>
            <th>Price</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {products.map(product => (
            <tr key={product.id}>
              <td>{product.name}</td>
              <td>{product.sku}</td>
              <td>{product.category}</td>
              <td>{product.price}</td>
              <td>
                <button onClick={() => openEditModal(product)}>
                  Edit
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

## Prompts Management Page

```javascript
function PromptsManagementPage() {
  const [prompts, setPrompts] = useState([]);
  const [loading, setLoading] = useState(true);

  // Load prompts on mount
  useEffect(() => {
    loadPrompts();
  }, []);

  async function loadPrompts() {
    try {
      const data = await getPrompts();
      setPrompts(data);
    } catch (error) {
      alert('Failed to load prompts: ' + error.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleUpdatePrompt(promptKey, promptText) {
    try {
      await updatePrompt(promptKey, promptText);
      alert('Prompt updated successfully!');
      loadPrompts(); // Reload to show changes
    } catch (error) {
      alert('Failed to update prompt: ' + error.message);
    }
  }

  async function handleResetPrompts() {
    try {
      const result = await resetPrompts();
      alert(result.message);
      loadPrompts(); // Reload to show reset prompts
    } catch (error) {
      alert('Failed to reset prompts: ' + error.message);
    }
  }

  async function handleDownloadPrompts() {
    try {
      await downloadPrompts();
      alert('Prompts downloaded! Update default_prompts.py with this file.');
    } catch (error) {
      alert('Failed to download prompts: ' + error.message);
    }
  }

  if (loading) return <div>Loading...</div>;

  return (
    <div>
      <h1>Prompts Management</h1>

      <div className="actions">
        <button onClick={handleDownloadPrompts}>
          Download Prompts (Python File)
        </button>
        <button onClick={handleResetPrompts} className="danger">
          Reset to Defaults
        </button>
      </div>

      {prompts.map(prompt => (
        <div key={prompt.prompt_key} className="prompt-item">
          <h3>{prompt.prompt_name}</h3>
          <p className="prompt-key">Key: {prompt.prompt_key}</p>
          <p className="description">{prompt.description}</p>

          <textarea
            value={prompt.prompt_text}
            onChange={(e) => {
              const updated = prompts.map(p =>
                p.prompt_key === prompt.prompt_key
                  ? { ...p, prompt_text: e.target.value }
                  : p
              );
              setPrompts(updated);
            }}
            rows={10}
          />

          <button onClick={() => handleUpdatePrompt(prompt.prompt_key, prompt.prompt_text)}>
            Save Changes
          </button>
        </div>
      ))}
    </div>
  );
}
```

---

# Error Handling

All endpoints return consistent error responses:

```json
{
  "success": false,
  "message": "Error description here"
}
```

**HTTP Status Codes:**
- `200 OK` - Successful operation
- `404 Not Found` - Resource not found (e.g., product_id or prompt_key doesn't exist)
- `500 Internal Server Error` - Server error

Always check `success` field in the response and handle errors appropriately.

---

# Best Practices

1. **Always confirm before resetting**: Reset operations delete all existing data. Show a confirmation dialog.

2. **Refresh data after updates**: After updating or resetting, reload the data to show the latest state.

3. **Validate inputs**: Validate product/prompt data before sending to the API.

4. **Handle loading states**: Show loading indicators while fetching data or performing updates.

5. **Download before resetting**: Before resetting to defaults, consider downloading the current data as a backup.

6. **Update hardcoded files periodically**: After making changes via the frontend, download the Python files and commit them to your repository to keep defaults in sync.

7. **Use TypeScript**: If using TypeScript, create interfaces for the response types to ensure type safety.

---

# File Locations

**Hardcoded default files to update after downloading:**
- Products: `src/orin_ai_crm/core/agents/custom/hana_agent/default_products.py`
- Prompts: `src/orin_ai_crm/core/agents/custom/hana_agent/default_prompts.py`

**Backend endpoint implementation:**
- `src/orin_ai_crm/server/routes/admin.py`

**API schemas:**
- `src/orin_ai_crm/server/schemas/admin.py`

---

# Support

For issues or questions about these endpoints, please contact the backend development team.
