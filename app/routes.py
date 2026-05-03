from fastapi import APIRouter, Body
from app.database import supabase

router = APIRouter()


# 🔥 STATUS
@router.get("/")
def home():
    return {"status": "online"}


# 📍 LISTAR UNIDADES
@router.get("/unidades")
def listar_unidades():
    data = supabase.table("unidades").select("*").execute()
    return data.data


# 📦 LISTAR PRODUTOS (com filtro por unidade)
@router.get("/produtos")
def listar_produtos(unidade_id: str = None):
    query = supabase.table("produtos").select("*")

    if unidade_id:
        query = query.eq("unidade_id", unidade_id)

    data = query.execute()
    return data.data


# ➕ CRIAR PRODUTO
@router.post("/produtos")
def criar_produto(produto: dict = Body(...)):
    data = supabase.table("produtos").insert(produto).execute()
    return data.data
