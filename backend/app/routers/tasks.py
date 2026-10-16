from fastapi import APIRouter
from pydantic import BaseModel

from app.services import tasks as tasks_service

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class NewTask(BaseModel):
    text: str


@router.get("")
def list_tasks():
    return tasks_service.list_tasks()


@router.post("")
def add_task(body: NewTask):
    return tasks_service.add_task(body.text)


@router.post("/{index}/toggle")
def toggle_task(index: int):
    return tasks_service.toggle_task(index)


@router.delete("/{index}")
def delete_task(index: int):
    return tasks_service.delete_task(index)
