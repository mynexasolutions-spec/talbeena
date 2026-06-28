# FastAPI Conversion Progress

## ✅ Completed

### Phase 1: Foundation
- [x] `main.py` - FastAPI app factory with middleware, static files, templates
- [x] `dependencies.py` - User auth, cart, dependency injection
- [x] `requirements.txt` - Updated with FastAPI, Uvicorn, Pydantic
- [x] `routes/auth_api.py` - Login, signup, Google OAuth, logout, account

### Phase 2: In Progress - Routes to Convert

| Route File | Status | Priority |
|-----------|--------|----------|
| public.py | ⏳ TODO | HIGH |
| cart.py | ⏳ TODO | HIGH |
| checkout.py | ⏳ TODO | HIGH |
| blog.py | ⏳ TODO | MEDIUM |
| admin.py | ⏳ TODO | MEDIUM |
| bigship/routes.py | ⏳ TODO | MEDIUM |

---

## 🔄 How to Complete Routes

### Template for Converting Each Route:

**Old Flask:**
```python
from flask import Blueprint, render_template, request
bp = Blueprint("public", __name__)

@bp.route("/shop")
def shop():
    items = request.args.get("search")
    return render_template("shop.html", items=items)
```

**New FastAPI:**
```python
from fastapi import APIRouter, Request, Query
router = APIRouter()

@router.get("/shop")
async def shop(request: Request, search: str = Query("")):
    return request.app.state.templates.TemplateResponse(
        "shop.html",
        {"request": request, "items": items}
    )
```

### Key Conversions:

| Flask | FastAPI |
|-------|---------|
| `@bp.route("/path")` | `@router.get("/path")` |
| `request.args.get()` | `Query()` parameter |
| `request.form.get()` | `Form()` parameter |
| `render_template()` | `TemplateResponse()` |
| `session["user"]` | `request.session["user"]` |
| `redirect()` | `RedirectResponse()` |
| `flash()` | Context dict with error message |
| `abort(404)` | `raise HTTPException(status_code=404)` |
| `jsonify()` | Return dict (auto-JSON) |

---

## 📝 Remaining Routes to Convert

### 1. **public.py** → `routes/public_api.py`
Routes to convert:
- `GET /` (homepage)
- `GET /shop` (shop/filter)
- `GET /product/<id>` (product detail)
- `GET /category/<slug>` (redirect)
- `GET /brand/<slug>` (redirect)
- `GET /about, /privacy-policy, /terms, /refund-policy, /shipping-policy` (static pages)
- `GET /contact, POST /contact` (contact form)
- `GET /blog/<slug>` (blog post)
- `POST /submit-review` (review submission)

**Key Functions to Call:**
- `get_homepage_products()` - Cached
- `get_products()` - With filters
- `get_product_detail()` - Product info
- `get_categories()` - For sidebar
- `get_brands()` - For filters
- `get_blog_posts()` - Blog listings

### 2. **cart.py** → `routes/cart_api.py`
Routes to convert:
- `GET /cart` (view cart)
- `POST /cart/add` (add item)
- `POST /cart/ajax_update` (update qty)
- `POST /cart/ajax_remove` (remove item)

**Key Changes:**
- AJAX calls return JSON (same logic)
- Session handling for cart
- Price refresh from database

### 3. **checkout.py** → `routes/checkout_api.py`
Routes to convert:
- `GET /checkout` (checkout form)
- `POST /checkout` (process order)
- `POST /razorpay/create_order` (Razorpay)
- `GET /order/<id>/success` (success page)
- `GET /order/<id>` (order detail)
- `POST /apply_coupon` (coupon validation)

**Key Changes:**
- Keep Razorpay integration as-is
- Session-based cart
- Database order creation
- Bigship shipment creation

### 4. **blog.py** → `routes/blog_api.py`
Routes to convert:
- `GET /blog` (listings)
- `GET /blog/<slug>` (post detail)
- `POST /blog/<id>/comment` (comments)

### 5. **admin.py** → `routes/admin_api.py`
Routes to convert:
- `GET /admin` (dashboard)
- CRUD for products, categories, orders, settings
- Upload handling
- Bulk operations

**Key: Use `require_admin` dependency**

### 6. **bigship/routes.py** → `bigship/routes_api.py`
Routes to convert:
- `GET /bigship/...` (Bigship operations)
- `POST /bigship/...` (order booking)

---

## 🎯 Quick Conversion Checklist

For each route file:
1. [ ] Create new `routes/*_api.py` file
2. [ ] Copy route logic from Flask version
3. [ ] Change decorators: `@bp.route()` → `@router.get/post()`
4. [ ] Update parameters: `request.args/form` → `Query/Form()`
5. [ ] Update templates: `render_template()` → `TemplateResponse()`
6. [ ] Update redirects: `redirect()` → `RedirectResponse()`
7. [ ] Update sessions: keep `request.session` same
8. [ ] Update JSON: return dict instead of `jsonify()`
9. [ ] Add router to `main.py`: `app.include_router(router)`
10. [ ] Test each route

---

## 🚀 Testing After Conversion

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run FastAPI server:
   ```bash
   python main.py
   ```
   or
   ```bash
   uvicorn main:app --reload
   ```

3. Test routes:
   - Homepage: http://localhost:5001/
   - Shop: http://localhost:5001/shop
   - Auth: http://localhost:5001/auth/login
   - Checkout: http://localhost:5001/checkout

4. Check FastAPI docs: http://localhost:5001/docs

---

## 📋 Database & Static Files (No Changes)

- ✅ `db.py` - Works as-is with FastAPI
- ✅ `queries.py` - Works as-is
- ✅ `helpers.py` - Works as-is
- ✅ `/static` - Mounted in `main.py`
- ✅ `/templates` - Jinja2 configured in `main.py`

---

## ⚠️ Important Notes

1. **Sessions**: FastAPI uses SessionMiddleware (already in main.py)
2. **CSRF**: Currently disabled (can add back with middleware)
3. **Database**: pg connection pool stays the same
4. **Caching**: TTL cache decorator works unchanged
5. **Integrations**: Razorpay, Bigship, Google OAuth all compatible

---

## Next Steps

1. Complete `routes/public_api.py` (highest priority)
2. Complete `routes/cart_api.py`
3. Complete `routes/checkout_api.py`
4. Complete remaining routes
5. Update EC2 deployment (change gunicorn command to uvicorn)
6. Test full flow end-to-end
7. Deploy

---

## Command to Run on EC2 After Conversion

**Old Flask:**
```bash
gunicorn --workers 1 --bind 127.0.0.1:8004 wsgi:app
```

**New FastAPI:**
```bash
gunicorn --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 127.0.0.1:8004 main:app
```

---

## File Structure (New)

```
talbeena/
├── main.py                 # FastAPI app (replaces app.py)
├── dependencies.py         # Dependency injection
├── db.py                   # Database (unchanged)
├── queries.py              # Queries (unchanged)
├── helpers.py              # Utilities (unchanged)
├── routes/
│   ├── auth_api.py         # ✅ Auth routes
│   ├── public_api.py       # ⏳ Public routes
│   ├── cart_api.py         # ⏳ Cart routes
│   ├── checkout_api.py     # ⏳ Checkout routes
│   ├── blog_api.py         # ⏳ Blog routes
│   └── admin_api.py        # ⏳ Admin routes
├── bigship/
│   ├── client.py           # (unchanged)
│   └── routes_api.py       # ⏳ Bigship routes
├── templates/              # (unchanged)
├── static/                 # (unchanged)
└── requirements.txt        # Updated
```
