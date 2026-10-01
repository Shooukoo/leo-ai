from betito_bot.llm.groq_client import build_client
from betito_bot.orchestrator.router import Orchestrator


def main():
    client = build_client()
    orchestrator = Orchestrator(client)

    print("Agente de IA")
    while True:
        user_text = input("Tú: ").strip()
        if not user_text:
            continue
        if user_text.lower() in ("exit", "salir"):
            break

        assistant_text = orchestrator.handle(user_text)
        print(f"Asistente: {assistant_text}")


if __name__ == "__main__":
    main()
