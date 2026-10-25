from ai_engine import SokokaliAI
from config import APP_NAME
from sports_engine import predict_match


def main() -> None:
    bot = SokokaliAI()
    print(f"{APP_NAME.upper()} AI SYSTEM STARTED")
    print("Commands: prediction, demo, exit")
    while True:
        try:
            message = input("Viewer: ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{APP_NAME}: Kwaheri!")
            break
        if message.lower() == "exit":
            print(f"{APP_NAME}: Kwaheri!")
            break
        if message.lower() == "demo":
            result = predict_match(1.6, 1.1)
            print(f"{APP_NAME}: DEMO ONLY — Home {result.home_win:.1%}, Draw {result.draw:.1%}, Away {result.away_win:.1%}")
            continue
        print(f"{APP_NAME}: {bot.respond(message)}")


if __name__ == "__main__":
    main()
