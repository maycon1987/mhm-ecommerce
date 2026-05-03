from fastapi import APIRouter, Body
from app.database import supabase

router = APIRouter()

@router.get("/unidades")
def listar_unidades():
    data = supabase.table("unidades").select("*").execute()
    return data.data

@router.get("/produtos")
def listar_produtos():
    data = supabase.table("produtos").select("*").execute()
    return data.data

@router.post("/produtos")
def criar_produto(produto: dict = Body(...)):
    data = supabase.table("produtos").insert(produto).execute()
    return data.data
