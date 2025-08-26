import os
from typing import List, Tuple, Dict
from web3 import Web3, AsyncWeb3
import aiohttp
import asyncio
from dotenv import load_dotenv
from datetime import datetime


load_dotenv()

# Настройка Web3 для Polygon
POLYGON_RPC_URL = os.getenv("POLYGON_RPC_URL")
POLYGONSCAN_API_KEY = os.getenv("POLYGONSCAN_API_KEY")
if not POLYGON_RPC_URL or not POLYGONSCAN_API_KEY:
    raise ValueError("POLYGON_RPC_URL or POLYGONSCAN_API_KEY not set in .env")

web3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(POLYGON_RPC_URL))


TOKEN_ADDRESS = os.getenv("TOKEN_ADDRESS")
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"}
        ],
        "name": "Transfer",
        "type": "event"
    }
]


contract = web3.eth.contract(address=Web3.to_checksum_address(TOKEN_ADDRESS), abi=ERC20_ABI)

# Кэш для decimals
_decimals_cache = None

async def get_decimals() -> int:
    """Получение decimals токена с кэшированием."""
    global _decimals_cache
    if _decimals_cache is None:
        _decimals_cache = await contract.functions.decimals().call()
    return _decimals_cache

async def get_balance(address: str) -> float:
    """Получение баланса одного адреса."""
    if not web3.is_address(address):
        raise ValueError("Invalid address")
    balance = await contract.functions.balanceOf(Web3.to_checksum_address(address)).call()
    decimals = await get_decimals()
    return balance / (10 ** decimals)

async def get_balance_batch(addresses: List[str]) -> List[float]:
    """Получение балансов нескольких адресов."""
    decimals = await get_decimals()
    tasks = [contract.functions.balanceOf(Web3.to_checksum_address(addr)).call() for addr in addresses]
    balances = await asyncio.gather(*tasks, return_exceptions=True)
    return [balance / (10 ** decimals) if isinstance(balance, int) else 0 for balance in balances]

async def get_token_holders() -> List[str]:
    """Получение списка держателей токена через PolygonScan API."""
    async with aiohttp.ClientSession() as session:
        url = f"https://api.polygonscan.com/api?module=token&action=tokenholderlist&contractaddress={TOKEN_ADDRESS}&apikey={POLYGONSCAN_API_KEY}"
        async with session.get(url) as response:
            data = await response.json()
            if data["status"] == "1":
                return [holder["address"] for holder in data["result"]]
            else:
                raise ValueError(f"PolygonScan API error: {data['message']}")

async def get_last_transaction_date(address: str) -> str:
    """Получение даты последней транзакции для адреса через PolygonScan API."""
    async with aiohttp.ClientSession() as session:
        url = f"https://api.polygonscan.com/api?module=account&action=tokentx&contractaddress={TOKEN_ADDRESS}&address={address}&sort=desc&apikey={POLYGONSCAN_API_KEY}"
        async with session.get(url) as response:
            data = await response.json()
            if data["status"] == "1" and data["result"]:
                # Получаем timestamp последней транзакции
                timestamp = int(data["result"][0]["timeStamp"])
                return datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
            return "No transactions found"

async def get_top(n: int) -> List[Tuple[str, float]]:
    """Получение топ-N адресов по балансам."""
    holders = await get_token_holders()
    holders = holders[:n]
    balances = await get_balance_batch(holders)
    address_balance_pairs = [(addr, bal) for addr, bal in zip(holders, balances) if bal > 0]
    address_balance_pairs.sort(key=lambda x: x[1], reverse=True)
    return address_balance_pairs[:n]

async def get_top_with_transactions(n: int) -> List[Tuple[str, float, str]]:
    """Получение топ-N адресов с датами транзакций."""
    top = await get_top(n)
    # Асинхронно запрашиваем даты последних транзакций
    tasks = [get_last_transaction_date(addr) for addr, _ in top]
    dates = await asyncio.gather(*tasks, return_exceptions=True)
    return [(addr, bal, date if isinstance(date, str) else "Error") for (addr, bal), date in zip(top, dates)]

async def get_token_info() -> Dict:
    """Получение информации о токене."""
    name, symbol, total_supply, decimals = await asyncio.gather(
        contract.functions.name().call(),
        contract.functions.symbol().call(),
        contract.functions.totalSupply().call(),
        contract.functions.decimals().call()
    )
    return {
        "name": name,
        "symbol": symbol,
        "totalSupply": total_supply / (10 ** decimals),
        "decimals": decimals
    }
