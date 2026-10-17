from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.sources.tasks import Conflict, NotFound, TasksSource

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class NewTask(BaseModel):
    text: str


class TaskPatch(BaseModel):
    done: bool | None = None
    text: str | None = None


def _tasks(request: Request) -> TasksSource:
    source = request.app.state.registry.get("tasks")
    if source is None:
        raise HTTPException(404, "Tasks source is disabled")
    if not source.available().available:
        raise HTTPException(409, source.available().reason)
    return source


def _run(source: TasksSource, fn):
    try:
        return fn()
    except Conflict:
        # Hand back the current state so the client can refresh without another round trip.
        return JSONResponse(
            {"detail": "Tasks file changed since you loaded it", "current": source.snapshot()},
            status_code=409,
        )
    except NotFound:
        return JSONResponse(
            {"detail": "Task not found; it may have been edited elsewhere", "current": source.snapshot()},
            status_code=404,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("")
def list_tasks(request: Request):
    return _tasks(request).snapshot()


@router.post("")
def add_task(body: NewTask, request: Request, if_match: str = Header()):
    source = _tasks(request)
    return _run(source, lambda: source.add(body.text, if_match))


@router.patch("/{task_id}")
def update_task(task_id: str, body: TaskPatch, request: Request, if_match: str = Header()):
    source = _tasks(request)
    return _run(source, lambda: source.update(task_id, if_match, done=body.done, text=body.text))


@router.delete("/{task_id}")
def delete_task(task_id: str, request: Request, if_match: str = Header()):
    source = _tasks(request)
    return _run(source, lambda: source.delete(task_id, if_match))
