# Stack concept map

Rough equivalents for a .NET and Angular developer. Use as a starting point. Always say
where the match is loose.

## Backend: ASP.NET Core and EF Core to FastAPI, Pydantic, SQLAlchemy

| New idea | Closest familiar idea | Where it differs |
| --- | --- | --- |
| FastAPI route function | Controller action or minimal API endpoint | Type hints on parameters drive validation and docs |
| `Depends(...)` | Constructor injection and `[Authorize]` filters | Resolved per request in the function signature, not in a container at startup |
| Pydantic model | DTO plus FluentValidation | Validation and serialization live in the same class |
| SQLAlchemy model | EF Core entity | Session and queries are explicit, with no change tracker magic |
| Session | `DbContext` | You manage lifetime through a dependency |
| Alembic migration | EF Core migration | Autogenerate misses things, so read every migration |
| Repository and service layers | Same pattern | Convention here, enforced by AGENTS.md, not by the framework |
| `pytest` fixture | xUnit fixture and test setup | Injected by argument name |
| OpenAPI schema | Swagger | It is the source for the generated TypeScript types |
| `async def` and `await` | `async Task` and `await` | Mixing blocking calls into async code stalls the server |
| Virtual environment | Per-project NuGet restore | Dependencies are installed into an isolated folder |

## Frontend: Angular to Next.js and React

| New idea | Closest familiar idea | Where it differs |
| --- | --- | --- |
| React component | Angular component | A function that returns UI. No separate template and class files |
| Props | `@Input()` | Plain function arguments |
| `useState` | Component field or signal | Updating state re-runs the component function |
| `useEffect` | `ngOnInit` and `ngOnChanges` | Runs after render and depends on a dependency list. Easy to misuse |
| Custom hook | Injectable service | Reusable stateful logic, called inside components |
| Server component | No direct match | Renders on the server and cannot use state or browser APIs |
| Client component (`"use client"`) | Normal Angular component | Runs in the browser |
| Route folders in `app/` | Angular router config | The folder structure is the route table |
| Form libraries and validation | Reactive forms | Schema-based validation is common |
| shadcn/ui component | Angular Material component | Source code copied into your repo, so you own and can edit it |
| Tailwind classes | Component CSS | Styling in the markup, with utility classes |
