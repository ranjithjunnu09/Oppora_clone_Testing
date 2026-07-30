import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
api_key = os.environ.get("ANTHROPIC_API_KEY")

print("=" * 60)
print("  TESTING BENCHMARK CONSOLE COMPATIBILITY LAYER WITH YOUR MODELS")
print("=" * 60)

# Connect via OpenAI compatibility layer
client = OpenAI(
    api_key=api_key,
    base_url="https://api.anthropic.com/v1/",
    default_headers={"anthropic-version": "2023-06-01"},
)

# Available models on your account
models_to_test = ["claude-sonnet-5", "claude-haiku-4-5-20251001", "claude-opus-5"]

for m in models_to_test:
    print(f"\nTesting OpenAI Compat Layer with model: '{m}'...")
    try:
        res = client.chat.completions.create(
            model=m,
            max_tokens=30,
            messages=[{"role": "user", "content": "Hi! Say hello!"}],
        )
        print(f"🎉 SUCCESS! Response from {m}:")
        print(f"   {res.choices[0].message.content}")
        if hasattr(res, "usage") and res.usage:
            u = res.usage
            print(f"   📊 Usage: prompt_tokens={u.prompt_tokens}, completion_tokens={u.completion_tokens}")
    except Exception as e:
        print(f"❌ Error with '{m}': {e}")

print("=" * 60)
