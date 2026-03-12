"""CLI for Mi Fitness MCP."""

import argparse
import asyncio
import sys

from mi_fitness_mcp.adapters.mi_fitness_cloud import MiFitnessCloudAdapter
from mi_fitness_mcp.auth import load_mi_fitness_token, save_mi_fitness_token
from mi_fitness_mcp.config import Config, get_config_path, load_config, save_config
from mi_fitness_mcp.server import main as server_main
from mi_fitness_mcp.storage import Database
from mi_fitness_mcp.services.sync_service import SyncService


PROGRAM_NAME = "mi-fitness-mcp"


async def _check_adapter_health(adapter) -> tuple[bool, list[str], str | None]:
    connected = await adapter.connect()
    region = getattr(adapter, "region", None)
    data_types = adapter.get_available_data_types() if connected else []
    if hasattr(adapter, "close"):
        await adapter.close()
    return connected, data_types, region


def cmd_setup(args):
    if args.mode == "mi_fitness_cloud" and args.user_id and args.pass_token:
        save_mi_fitness_token(args.user_id, args.pass_token)
        config = Config(mode="mi_fitness_cloud", region=args.region or "ru")
        save_config(config)
        print("✅ Конфигурация сохранена (mi_fitness_cloud)")
        print(f"   User ID: {args.user_id}")
        print(f"   Region: {config.region}")
        return

    print(f"{PROGRAM_NAME} - Setup Wizard")
    print("=" * 50)
    print()
    user_id = input("Mi Fitness user_id: ").strip()
    pass_token = input("Mi Fitness passToken: ").strip()
    region = input("Region [ru]: ").strip() or "ru"
    if not user_id or not pass_token:
        print("❌ Требуются user_id и passToken")
        sys.exit(1)
    save_mi_fitness_token(user_id, pass_token)
    config = Config(mode="mi_fitness_cloud", region=region)
    save_config(config)
    print("✅ Mi Fitness конфигурация сохранена!")


def cmd_doctor(args):
    print(f"{PROGRAM_NAME} - Doctor")
    print("=" * 50)
    print()
    config_path = get_config_path()
    print(f"Конфигурация: {config_path}")

    if not config_path.exists():
        print("❌ Конфигурация не найдена")
        print(f"   Запустите: {PROGRAM_NAME} setup")
        sys.exit(1)

    try:
        config = load_config()
        print("✅ Конфигурация загружена")
        print(f"   Режим: {config.mode}")
        user_id, pass_token = load_mi_fitness_token()
        if user_id and pass_token:
            print("✅ Mi Fitness credentials найдены")
            print(f"   User ID: {user_id}")
            print(f"   Region: {config.region}")
            adapter = MiFitnessCloudAdapter(user_id=user_id, pass_token=pass_token, region=config.region)
            connected, data_types, region = asyncio.run(_check_adapter_health(adapter))
            print(f"   Подключение: {'✅' if connected else '❌'}")
            if connected:
                print(f"   Определённый регион: {region}")
                print(f"   Типы данных: {', '.join(data_types)}")
        else:
            print("❌ Mi Fitness credentials не найдены")
            print(f"   Запустите: {PROGRAM_NAME} setup")

        print()
        print(f"База данных: {config.database_path}")
        if config.database_path.exists():
            Database(config.database_path)
            print("✅ База данных доступна")
        else:
            print("ℹ️  База данных будет создана при первом запуске")
    except Exception as e:
        print(f"❌ Ошибка загрузки конфигурации: {e}")
        sys.exit(1)


async def cmd_sync_async(args):
    print(f"{PROGRAM_NAME} - Sync")
    print("=" * 50)
    print()

    try:
        config = load_config()
    except Exception as e:
        print(f"❌ Ошибка загрузки конфигурации: {e}")
        sys.exit(1)

    if config.mode == "not_configured":
        print("❌ Сервер не настроен")
        print(f"   Запустите: {PROGRAM_NAME} setup")
        sys.exit(1)

    user_id, pass_token = load_mi_fitness_token()
    if not user_id or not pass_token:
        print("❌ Mi Fitness credentials не найдены")
        print(f"   Запустите: {PROGRAM_NAME} setup")
        sys.exit(1)

    db = Database(config.database_path)
    adapter = MiFitnessCloudAdapter(user_id=user_id, pass_token=pass_token, region=config.region)
    if not await adapter.connect():
        print("❌ Не удалось подключиться к Mi Fitness API")
        sys.exit(1)

    sync_service = SyncService(adapter, db)
    data_types = [args.type] if args.type else adapter.get_available_data_types()
    print(f"Синхронизация {len(data_types)} типов данных...")
    print()
    for data_type in data_types:
        try:
            result = await sync_service.sync_data_type(
                data_type=data_type,
                start_date=args.start_date,
                end_date=args.end_date,
            )
            print(f"✅ {data_type}: {result['added']} добавлено, {result['updated']} обновлено")
        except Exception as e:
            print(f"❌ {data_type}: {e}")

    print()
    print("Синхронизация завершена!")


def cmd_sync(args):
    asyncio.run(cmd_sync_async(args))


def main():
    parser = argparse.ArgumentParser(prog=PROGRAM_NAME, description="MCP server for Mi Fitness data")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    subparsers.add_parser("serve", help="Run MCP server")

    setup_parser = subparsers.add_parser("setup", help="Configure the server")
    setup_parser.add_argument("--mode", choices=["mi_fitness_cloud"], help="Setup mode")
    setup_parser.add_argument("--user-id", help="Mi Fitness user ID")
    setup_parser.add_argument("--pass-token", help="Mi Fitness passToken")
    setup_parser.add_argument("--region", help="Cloud region")

    subparsers.add_parser("doctor", help="Check configuration and diagnose issues")

    sync_parser = subparsers.add_parser("sync", help="Sync data from source")
    sync_parser.add_argument("--type", choices=["daily_activity", "body_measurements", "heart_rate"], help="Type of data to sync")
    sync_parser.add_argument("--start-date", help="Start date (YYYY-MM-DD)")
    sync_parser.add_argument("--end-date", help="End date (YYYY-MM-DD)")

    args = parser.parse_args()
    if args.command == "serve" or args.command is None:
        asyncio.run(server_main())
    elif args.command == "setup":
        cmd_setup(args)
    elif args.command == "doctor":
        cmd_doctor(args)
    elif args.command == "sync":
        cmd_sync(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
