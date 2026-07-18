import sys
print("Python:", sys.executable)
try:
    from app.main import app
    print("FastAPI app loaded:", app.title)
    routes = [r.path for r in app.routes if hasattr(r, 'path')]
    for r in sorted(routes):
        if 'pivot' in r.lower():
            print(' ROUTE:', r)
except Exception as e:
    import traceback
    traceback.print_exc()
