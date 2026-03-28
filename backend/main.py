from fastapi import FastAPI
from routers import meeting, bot_media

app = FastAPI()

app.include_router(meeting.router)
app.include_router(bot_media.router)

@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}

