from fastapi import FastAPI
import uvicorn
from threading import Thread

app = FastAPI()

@app.get("/")
async def home():
    return {"status": "Bot is running"}

# TOTO JSME PŘIDALI PRO UPTIMEROBOT:
@app.head("/")
async def head_home():
    return None

def run():
    uvicorn.run(app, host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()