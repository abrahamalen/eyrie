from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.sources.tasks import TasksSource

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class NewTask(BaseModel):
    text: str


def _tasks(request: Request) -> TasksSource:
    source = request.app.state.registry.get("tasks")
    if source is None:
        raise HTTPException(404, "Tasks source is disabled")
    if not source.available().available:
        raise HTTPException(409, source.available().reason)
    return source


@router.get("")
def list_tasks(request: Request):
    return _tasks(request).items()


@router.post("")
def add_task(body: NewTask, request: Request):
    return _tasks(request).add(body.text)


@router.post("/{index}/toggle")
def toggle_task(index: int, request: Request):
    return _tasks(request).toggle(index)


@router.delete("/{index}")
def delete_task(index: int, request: Request):
    return _tasks(request).delete(index)
