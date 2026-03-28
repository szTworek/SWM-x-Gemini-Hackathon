from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import meeting
from routers import config

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex="chrome-extension://.*", # Zezwala na każdą wtyczkę Chrome
    allow_origins=["*"], # Fallback dla testów z localhost
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meeting.router)
app.include_router(config.router)
@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}
