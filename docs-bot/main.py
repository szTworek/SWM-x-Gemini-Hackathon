from fastapi import FastAPI

from routers import meeting

app = FastAPI(title='docs-bot API')

app.include_router(meeting.router)


@app.get('/')
async def root():
    return {'message': 'docs-bot API is running'}
