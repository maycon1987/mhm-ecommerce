from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
import os

# =========================
# CONFIG SUPABASE
# =========================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# APP
# =========================
app = FastAPI()

# =========================
# MODELOS
# =========================
class CalcularPrecoRequest(BaseModel):
    produto_id: str
    quantidade: int


# =========================
# HEALTH CHECK
# =========================
@app.get("/")
def home():
    return {"status": "ok", "app": "ecommerce-api"}


# =========================
# LISTAR PRODUTOS (leve)
# =========================
@app.get("/produtos")
def listar_produtos(unidade_id: str = None):
    query = supabase.table("produtos").select("id, nome, slug, imagem_url")

    if unidade_id:
        query = query.eq("unidade_id", unidade_id)

    response = query.execute()

    return response.data


# =========================
# DETALHE DO PRODUTO (SEO)
# =========================
@app.get("/produto/{slug}")
def detalhe_produto(slug: str):
    produto_resp = (
        supabase
        .table("produtos")
        .select("*")
        .eq("slug", slug)
        .single()
        .execute()
    )

    produto = produto_resp.data

    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    precos_resp = (
        supabase
        .table("produto_precos")
        .select("*")
        .eq("produto_id", produto["id"])
        .order("quantidade_minima")
        .execute()
    )

    return {
        "produto": produto,
        "precos": precos_resp.data
    }


# =========================
# CALCULAR PREÇO AUTOMÁTICO
# =========================
@app.post("/calcular-preco")
def calcular_preco(dados: CalcularPrecoRequest):
    produto_id = dados.produto_id
    quantidade = dados.quantidade

    if quantidade <= 0:
        raise HTTPException(status_code=400, detail="Quantidade inválida")

    # Busca produto
    produto_resp = (
        supabase
        .table("produtos")
        .select("id, nome")
        .eq("id", produto_id)
        .single()
        .execute()
    )

    produto = produto_resp.data

    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    # Busca melhor faixa de preço
    precos_resp = (
        supabase
        .table("produto_precos")
        .select("*")
        .eq("produto_id", produto_id)
        .lte("quantidade_minima", quantidade)
        .order("quantidade_minima", desc=True)
        .limit(1)
        .execute()
    )

    precos = precos_resp.data

    if not precos:
        raise HTTPException(status_code=404, detail="Preço não encontrado")

    preco_aplicado = precos[0]

    preco_unitario = float(preco_aplicado["preco_unitario"])
    subtotal = preco_unitario * quantidade

    return {
        "produto_id": produto_id,
        "produto": produto["nome"],
        "quantidade": quantidade,
        "preco_unitario": preco_unitario,
        "faixa_aplicada": preco_aplicado["quantidade_minima"],
        "tipo": preco_aplicado.get("tipo"),
        "subtotal": subtotal
    }
