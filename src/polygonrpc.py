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
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
TOKEN_ADDRESS = os.getenv("TOKEN_ADDRESS")
if not POLYGON_RPC_URL or not ETHERSCAN_API_KEY or not TOKEN_ADDRESS:
    raise ValueError("POLYGON_RPC_URL, ETHERSCAN_API_KEY, or TOKEN_ADDRESS not set in .env")

web3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(POLYGON_RPC_URL))

# Стандартный ABI ERC20
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

# Создаем экземпляр контракта
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
    """Получение списка держателей токена через Etherscan V2 API."""
    await asyncio.sleep(0.2)  # Задержка для rate limit
    async with aiohttp.ClientSession() as session:
        url = f"https://api.etherscan.io/v2/address/{TOKEN_ADDRESS}/tokentx?chainid=137&apikey={ETHERSCAN_API_KEY}"
        async with session.get(url) as response:
            if response.status != 200:
                raise ValueError(f"Etherscan V2 API error: HTTP {response.status}")
            try:
                data = await response.json()
            except Exception as e:
                raise ValueError(f"Etherscan V2 API error: Failed to parse JSON: {str(e)}")
            if data.get("status") != "success":
                raise ValueError(f"Etherscan V2 API error: {data.get('message', 'NOTOK')} - {data.get('error', 'No details provided')}")
            holders = set()
            for tx in data.get("data", {}).get("transactions", []):
                if "from" in tx:
                    holders.add(tx["from"])
                if "to" in tx:
                    holders.add(tx["to"])
            return list(holders)

async def get_last_transaction_date(address: str) -> str:
    """Получение даты последней транзакции для адреса через Etherscan V2 API."""
    await asyncio.sleep(0.2)  # Задержка для rate limit
    async with aiohttp.ClientSession() as session:
        url = f"https://api.etherscan.io/v2/address/{address}/tokentx?chainid=137&contractaddress={TOKEN_ADDRESS}&sort=desc&apikey={ETHERSCAN_API_KEY}"
        async with session.get(url) as response:
            if response.status != 200:
                raise ValueError(f"Etherscan V2 API error: HTTP {response.status}")
            try:
                data = await response.json()
            except Exception as e:
                raise ValueError(f"Etherscan V2 API error: Failed to parse JSON: {str(e)}")
            if data.get("status") != "success" or not data.get("data", {}).get("transactions"):
                return "No transactions found"
            timestamp = int(data["data"]["transactions"][0]["timeStamp"])
            return datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")

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
    