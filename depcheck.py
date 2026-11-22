import importlib, sys
mods = ['fastapi','sqlalchemy','pandas','numpy','redis','sqlglot','jwt','bcrypt','httpx','stripe','arq','langchain_openai','langchain_core','pydantic_settings','playwright','email_validator','multipart']
for m in mods:
    try:
        importlib.import_module(m); print(f"{m}: OK")
    except Exception as e:
        print(f"{m}: MISSING ({type(e).__name__}: {e})")
print("python", sys.version.split()[0])
