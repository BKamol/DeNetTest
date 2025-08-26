from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from polygonrpc import get_balance, get_balance_batch, get_top, get_top_with_transactions, get_token_info

app = FastAPI()

# Модель для запроса балансов нескольких адресов
class AddressList(BaseModel):
    addresses: List[str]

# Модель для информации о токене
class TokenInfo(BaseModel):
    symbol: str
    name: str
    totalSupply: float

# Уровень A: GET /get_balance
@app.get("/get_balance")
async def api_get_balance(address: str):
    try:
        balance = await get_balance(address)
        return {"balance": balance}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching balance: {str(e)}")

# Уровень B: POST /get_balance_batch
@app.post("/get_balance_batch")
async def api_get_balance_batch(address_list: AddressList):
    try:
        balances = await get_balance_batch(address_list.addresses)
        return {"balances": balances}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching balances: {str(e)}")

# Уровень C: GET /get_top
@app.get("/get_top")
async def api_get_top(n: int):
    try:
        top = await get_top(n)
        return {"top": [{"address": addr, "balance": bal} for addr, bal in top]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching top addresses: {str(e)}")

# Уровень D: GET /get_top_with_transactions
@app.get("/get_top_with_transactions")
async def api_get_top_with_transactions(n: int):
    try:
        top = await get_top_with_transactions(n)
        return {"top": [{"address": addr, "balance": bal, "last_transaction_date": date} for addr, bal, date in top]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching top addresses with transactions: {str(e)}")

# Уровень E: GET /get_token_info
@app.get("/get_token_info", response_model=TokenInfo)
async def api_get_token_info():
    try:
        token_info = await get_token_info()
        return token_info
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching token info: {str(e)}")
