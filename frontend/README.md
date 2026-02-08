# Frontend

## Генерация типов из OpenAPI
- Команда: `npm run gen:api` (использует `OPENAPI_URL` или по умолчанию `http://backend:8000/openapi.json`).
- Сгенерированные типы лежат в `src/types/api.d.ts`. CI проверяет, что после генерации нет непроизведённых изменений (`git diff --exit-code`).
- Перед PR запускайте `npm run gen:api && npm run typecheck && npm run build`.

## Сборка
- В Dockerfile builder стадии выполняется `npm run gen:api && npm run typecheck && npm run build`. Если типы устарели или есть TS-ошибки, сборка упадёт.
- Node версия закреплена в `.nvmrc` и `package.json` (`>=20 <21`).
