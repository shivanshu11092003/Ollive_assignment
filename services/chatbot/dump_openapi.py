import json
import os
import sys

# Add project root to path so we can import services
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.chatbot.main import app

def dump_schema():
    print("Extracting FastAPI OpenAPI schema...")
    schema = app.openapi()
    
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "openapi.json"
    )
    
    with open(output_path, "w") as f:
        json.dump(schema, f, indent=2)
        
    print(f"OpenAPI schema successfully written to: {output_path}")

if __name__ == "__main__":
    dump_schema()
