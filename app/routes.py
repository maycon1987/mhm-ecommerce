
from fastapi import APIRouter
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
