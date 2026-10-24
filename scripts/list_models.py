"""Print the models each configured API key can use (no key is ever printed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import config  # noqa: E402


def main() -> None:
    if config.env("GEMINI_API_KEY"):
        from google import genai
        try:
            client = genai.Client(api_key=config.env("GEMINI_API_KEY"))
            names = sorted(m.name for m in client.models.list())
            print("Gemini models:", *names, sep="\n  ")
        except Exception as e:  # noqa: BLE001
            print("Gemini list failed:", type(e).__name__)
    else:
        print("GEMINI_API_KEY not set")
    if config.env("GROQ_API_KEY"):
        from groq import Groq
        try:
            ms = Groq(api_key=config.env("GROQ_API_KEY")).models.list()
            print("Groq models:", *sorted(m.id for m in ms.data), sep="\n  ")
        except Exception as e:  # noqa: BLE001
            print("Groq list failed:", type(e).__name__)
    else:
        print("GROQ_API_KEY not set")


if __name__ == "__main__":
    main()
