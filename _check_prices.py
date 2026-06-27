from db import query
rows = query("SELECT pv.id, pv.name, pv.price, pv.sale_price, p.name AS product_name FROM product_variations pv JOIN products p ON p.id = pv.product_id")
seen = set()
for r in rows:
    pid = r['product_name']
    if pid not in seen:
        seen.add(pid)
        if any(v['price'] == 0 or v['price'] is None for v in rows if v['product_name'] == pid):
            print(f"Product: {pid}")
            for v in rows:
                if v['product_name'] == pid:
                    print(f"  Var {v['id']}: name={v['name']}, price={v['price']}, sale_price={v['sale_price']}")
