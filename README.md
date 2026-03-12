# Mi Fitness MCP

Отдельный MCP-сервер для `Mi Fitness`.

Подтверждённые данные:

- шаги
- калории
- пульс
- вес и состав тела

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e "."
```

## Команды

```bash
mi-fitness-mcp setup --mode mi_fitness_cloud --user-id "<userId>" --pass-token "<passToken>" --region ru
mi-fitness-mcp doctor
mi-fitness-mcp sync --start-date 2025-04-01 --end-date 2025-05-31
mi-fitness-mcp serve
```

## Настройка Claude Desktop

```json
{
  "mcpServers": {
    "mi-fitness": {
      "command": "mi-fitness-mcp",
      "args": ["serve"]
    }
  }
}
```
